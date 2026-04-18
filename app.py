# ──────────────────────────────────────────────────────────────────────────────
# 1. IMPORTS AND CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
import numpy as np
import json
import joblib
import os
import time
import math
import threading
import heapq
import requests
from collections import deque
from datetime import datetime, timezone

import sseclient

BASE_URL = "http://localhost:3000"
MACHINE_IDS = ["CNC_01", "CNC_02", "PUMP_03", "CONVEYOR_04"]
SENSORS = ["temperature_C", "vibration_mm_s", "rpm", "current_A"]
BUFFER_SIZE = 120
Z_DEFAULT_THRESHOLD = 3.0
ALERT_COOLDOWN_SEC = 60
RISK_ALERT_THRESHOLD = 65.0

# Per-machine initial Z-score thresholds (tuned from baseline analysis)
# Lower = more sensitive; higher = fewer FPs at cost of some recall
_INITIAL_Z_THRESHOLD = {
    "CNC_01":      2.7,   # lower — CNC_01 rarely faults, need early detection
    "CNC_02":      2.8,   # slightly sensitive — faults frequently
    "PUMP_03":     2.5,   # most sensitive — 736 FNs to recover
    "CONVEYOR_04": 3.3,   # higher guard — belt dynamics inflate Z on normal ops
}

# Minimum consecutive above-threshold readings before alert fires
# Key FP reduction: CNC_02 had 1172 FPs and CONVEYOR_04 had 848 FPs
# Requiring N consecutive readings ≈ FPs × (FP_rate)^(N-1) reduction
_MIN_BREACH_FOR_ALERT = {
    "CNC_01":      1,
    "CNC_02":      1,   # Normal max<84%; clean boundary at 84% threshold
    "CONVEYOR_04": 3,   # Sustained gate reduces FPs for noisy conveyor signal
    "PUMP_03":     1,   # Threshold=60%>normal_max(59%); breach=1 catches first-tick faults
}
RISK_MAINTENANCE_THRESHOLD = 85.0

# Maintenance scheduling — breach-count rules
# Format: (min_risk_pct, breaches_required, label)
# Evaluated top-to-bottom; first match wins.
MAINTENANCE_RULES = [
    (95.0, 1,  "CRITICAL"),      # ≥95% once  → immediate
    (85.0, 3,  "VERY HIGH"),     # ≥85% 3×    → urgent
    (70.0, 8,  "HIGH"),          # ≥70% 8×    → scheduled
]
MAINTENANCE_COOLDOWN_SEC = 300   # don't re-book same machine within 5 min

# Per-machine overrides — tuned from live evaluation (2026-04-18)
# CNC_01:      55  — rarely faults; threshold below max observed normal risk (52.1%)
# CNC_02:      84  — optimal by sweep: F1=88.4% at 84% vs 80.6% at 78% (too many FPs)
# CONVEYOR_04: 93  — FPs at 93-99%, breach_count=3 gate eliminates them
# PUMP_03:     60  — normal max=59%, threshold=60% gives 0 FPs; breach=1 catches first-ticks
_RISK_ALERT_THRESHOLD_OVERRIDE = {
    "CNC_01":      55.0,
    "CNC_02":      84.0,
    "CONVEYOR_04": 93.0,
    "PUMP_03":     60.0,
}

def _alert_threshold(machine_id: str) -> float:
    return _RISK_ALERT_THRESHOLD_OVERRIDE.get(machine_id, RISK_ALERT_THRESHOLD)
DATA_MISSING_TIMEOUT_SEC = 10
DATA_MISSING_RISK_PENALTY = 15


# ──────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL SHARED STATE
# Threads cannot access st.session_state (no ScriptRunContext).
# _STATE is a plain Python dict visible to all threads and all Streamlit reruns
# within the same server process.  Python's GIL makes simple dict/deque
# assignments safe enough for this use case.
# ──────────────────────────────────────────────────────────────────────────────
_STATE: dict = {}
_THREADS_STARTED = False
_STATE_LOCK = threading.Lock()


def _state_init():
    global _STATE
    if _STATE:
        return
    with _STATE_LOCK:
        if _STATE:
            return
        _STATE.update({
            "baselines":          {},
            "models":             {},
            "buffers":            {mid: deque(maxlen=BUFFER_SIZE) for mid in MACHINE_IDS},
            "connection_status":  {mid: "Connecting" for mid in MACHINE_IDS},
            "last_data_time":     {mid: 0.0 for mid in MACHINE_IDS},
            "learned_thresholds": {mid: _INITIAL_Z_THRESHOLD.get(mid, Z_DEFAULT_THRESHOLD) for mid in MACHINE_IDS},
            "alert_log":          [],
            "unconfirmed_alerts": {mid: None for mid in MACHINE_IDS},
            "last_alert_time":        {mid: 0.0 for mid in MACHINE_IDS},
            "breach_counts":          {mid: 0   for mid in MACHINE_IDS},
            "last_maintenance_time":  {mid: 0.0 for mid in MACHINE_IDS},
            "maintenance_log":    [],
            "maint_algo":        "Priority Queue (Urgency First)",
            "log_messages":       deque(maxlen=200),
            "priority_queue":     [],
            "render_tick":        0,
        })
        for mid in MACHINE_IDS:
            _STATE[f"risk_{mid}"]      = 0.0
            _STATE[f"features_{mid}"]  = None
            _STATE[f"etf_{mid}"]       = {s: float("inf") for s in SENSORS}
            _STATE[f"if_anomaly_{mid}"] = False
            # ADDED: polyfit confidence state
            _STATE[f"polyfit_{mid}"]   = {"score": 0.0, "slopes": {s: 0.0 for s in SENSORS}}


# ──────────────────────────────────────────────────────────────────────────────
# 2. SESSION STATE INITIALIZER  (UI-only wiring; real data lives in _STATE)
# ──────────────────────────────────────────────────────────────────────────────
def init_state():
    _state_init()
    # Nothing else needed; st.session_state is not used for shared data.


# ──────────────────────────────────────────────────────────────────────────────
# 3. BASELINE + MODEL LOADER
# ──────────────────────────────────────────────────────────────────────────────
def load_assets():
    if not _STATE["baselines"]:
        if os.path.isfile("baselines.json"):
            with open("baselines.json") as f:
                _STATE["baselines"] = json.load(f)
        else:
            bl = {}
            for mid in MACHINE_IDS:
                bl[mid] = {}
                for s in SENSORS:
                    v, n = SIM_DEFAULTS[mid][s], SIM_NOISE[s]
                    bl[mid][s] = {"mean": v, "std": n,
                                  "min": v - 3 * n, "max": v + 3 * n}
            _STATE["baselines"] = bl
            _STATE["log_messages"].append(
                "baselines.json not found — using simulation defaults."
            )

    if not _STATE["models"]:
        for mid in MACHINE_IDS:
            path = f"model_{mid}.pkl"
            if os.path.isfile(path):
                try:
                    _STATE["models"][mid] = joblib.load(path)
                except Exception as e:
                    _STATE["log_messages"].append(f"Model load error {mid}: {e}")
            else:
                _STATE["log_messages"].append(
                    f"{path} not found — ML detection disabled for {mid}."
                )


# ──────────────────────────────────────────────────────────────────────────────
# 4. SSE STREAM LISTENER THREAD
# ──────────────────────────────────────────────────────────────────────────────
def stream_worker(machine_id):
    backoff = 1

    while True:
        try:
            url = f"{BASE_URL}/stream/{machine_id}"
            resp = requests.get(
                url, stream=True, timeout=10,
                headers={"Accept": "text/event-stream"},
            )
            resp.raise_for_status()
            client = sseclient.SSEClient(resp)
            backoff = 1
            _STATE["connection_status"][machine_id] = "Live"
            _STATE["log_messages"].append(f"[{machine_id}] SSE stream connected.")

            for event in client.events():
                if event.data and event.data.strip():
                    try:
                        data = json.loads(event.data)
                        data.setdefault("machine_id", machine_id)
                        data.setdefault(
                            "timestamp",
                            datetime.now(timezone.utc).isoformat(),
                        )
                        data.setdefault("status", "running")
                        _STATE["buffers"][machine_id].append(data)
                        _STATE["last_data_time"][machine_id] = time.time()
                    except Exception:
                        pass

        except Exception as e:
            _STATE["connection_status"][machine_id] = "Disconnected"
            _STATE["log_messages"].append(
                f"[{machine_id}] Stream error: {type(e).__name__}. "
                f"Retry in {backoff}s."
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


# ──────────────────────────────────────────────────────────────────────────────
# 5. FEATURE ENGINEERING FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────
def compute_features(machine_id):
    buf = _STATE["buffers"][machine_id]
    bl = _STATE["baselines"]
    if not buf or machine_id not in bl:
        return None
    b = bl[machine_id]
    buf_list = list(buf)
    latest = buf_list[-1]

    z_scores = {}
    for s in SENSORS:
        val  = float(latest.get(s, b[s]["mean"]))
        mean = b[s]["mean"]
        # Floor: at least 3% of mean to prevent tight healthy distributions
        # (e.g. CONVEYOR_04 RPM std≈5) from producing explosive z-scores on
        # normal fluctuations.
        std  = max(b[s]["std"], abs(mean) * 0.03, 1e-3)
        z_scores[s] = abs((val - mean) / std)

    delta = {}
    for s in SENSORS:
        if len(buf_list) >= 6:
            delta[s] = round(
                float(buf_list[-1].get(s, b[s]["mean"]))
                - float(buf_list[-6].get(s, b[s]["mean"])),
                4,
            )
        else:
            delta[s] = 0.0

    rolling_mean, rolling_var = {}, {}
    window = buf_list[-30:] if len(buf_list) >= 30 else buf_list
    for s in SENSORS:
        vals = [float(r.get(s, b[s]["mean"])) for r in window]
        rolling_mean[s] = float(np.mean(vals))
        rolling_var[s]  = float(np.var(vals))

    return {
        "latest":       latest,
        "z_scores":     z_scores,
        "delta":        delta,
        "rolling_mean": rolling_mean,
        "rolling_var":  rolling_var,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6. HYBRID DETECTION + RISK SCORING FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────
def run_isolation_forest(machine_id, latest, delta):
    models = _STATE.get("models", {})
    if machine_id not in models:
        return False
    try:
        X = np.array([
            float(latest.get("temperature_C", 0)),
            float(latest.get("vibration_mm_s", 0)),
            float(latest.get("rpm", 0)),
            float(latest.get("current_A", 0)),
        ]).reshape(1, -1)
        return int(models[machine_id].predict(X)[0]) == -1
    except Exception:
        return False


def compute_etf(machine_id):
    buf = _STATE["buffers"][machine_id]
    bl  = _STATE["baselines"]
    if len(buf) < 30 or machine_id not in bl:
        return {s: float("inf") for s in SENSORS}
    b = bl[machine_id]
    buf_list = list(buf)
    etf = {}
    for s in SENSORS:
        threshold = b[s]["mean"] + 3.0 * b[s]["std"]
        vals = [float(r.get(s, b[s]["mean"])) for r in buf_list]
        x = np.arange(len(vals), dtype=float)
        try:
            coeffs = np.polyfit(x, vals, 1)
            slope, intercept = float(coeffs[0]), float(coeffs[1])
            if slope <= 1e-9:
                etf[s] = float("inf")
            else:
                projected = slope * len(vals) + intercept
                etf[s] = 0.0 if projected >= threshold else max(
                    0.0, (threshold - projected) / slope
                )
        except Exception:
            etf[s] = float("inf")
    return etf


# ADDED: Layer 4b — Polyfit Confidence Score
_MAX_SLOPE = {
    "temperature_C":  0.5,
    "vibration_mm_s": 0.05,
    "rpm":            2.0,
    "current_A":      0.1,
}
# Per-machine slope overrides — loosen where natural variance exceeds global defaults
# CONVEYOR_04 raised further: its normal belt dynamics produce high polyfit severity,
# contributing to the 848 FPs; loosening reduces trend_penalty on healthy rows
_MAX_SLOPE_OVERRIDE: dict[str, dict] = {
    "CONVEYOR_04": {
        "temperature_C":  0.8,   # was 0.5
        "vibration_mm_s": 0.22,  # was 0.12 — belt dynamics trigger false polyfit spikes
        "rpm":            6.0,   # was 4.0
        "current_A":      0.35,  # was 0.2
    },
    "CNC_02": {
        "temperature_C":  0.8,   # was 0.5 — CNC temperature drifts more
        "vibration_mm_s": 0.10,  # was 0.08 — further loosen; polyfit score 90.9 on FP rows
        "current_A":      0.18,  # was 0.15
    },
}

def compute_polyfit_confidence(machine_id):
    """Returns {"score": 0-100, "slopes": {sensor: float}, "severities": {sensor: float}}"""
    buf = _STATE["buffers"][machine_id]
    if len(buf) < 30:
        return {"score": 0.0,
                "slopes":     {s: 0.0 for s in SENSORS},
                "severities": {s: 0.0 for s in SENSORS}}

    buf_list = list(buf)[-30:]
    x = np.arange(30, dtype=float)
    slopes, severities = {}, {}
    machine_slopes = {**_MAX_SLOPE, **_MAX_SLOPE_OVERRIDE.get(machine_id, {})}

    for s in SENSORS:
        vals = [float(r.get(s, 0)) for r in buf_list]
        try:
            slope = float(np.polyfit(x, vals, 1)[0])
        except Exception:
            slope = 0.0
        slopes[s] = slope
        severities[s] = min(abs(slope) / machine_slopes[s] * 100.0, 100.0)

    score = max(severities.values())
    return {"score": round(score, 1), "slopes": slopes, "severities": severities}


def _sigmoid(x):
    x = max(-500.0, min(500.0, float(x)))
    return 1.0 / (1.0 + math.exp(-x))


def compute_risk(machine_id, features, if_anomaly, etf_dict):
    z_scores  = features["z_scores"]
    threshold = _STATE["learned_thresholds"].get(machine_id, Z_DEFAULT_THRESHOLD)
    max_z     = max(z_scores.values()) if z_scores else 0.0

    # Normalise to [-1, +1] range before sigmoid so score only clears
    # 70% when z genuinely exceeds the threshold, not on marginal readings.
    base_score = (max_z - threshold) / max(threshold, 1e-6)
    # IF corroboration gates — require minimum z before IF penalty applies
    # CONVEYOR_04: raised to 5.0 (was 3.0) — IF fires on normal readings, needs strong Z
    # CNC_02:      raised to 3.5 (was 2.0) — 30% FPR driven partly by spurious IF flags
    # Others in override dict: 2.5; CNC_01 (no override): 0 (allow IF to fire freely)
    _if_min_z_map = {"CONVEYOR_04": 5.0, "CNC_02": 3.5, "PUMP_03": 2.0}
    _if_min_z = _if_min_z_map.get(
        machine_id,
        2.5 if machine_id in _RISK_ALERT_THRESHOLD_OVERRIDE else 0.0,
    )
    isolation_penalty = 0.3 if (if_anomaly and max_z >= _if_min_z) else 0.0
    # CHANGED: Layer 5 — proportional trend_penalty using polyfit_score
    pf = _STATE.get(f"polyfit_{machine_id}", {})
    polyfit_score     = pf.get("score", 0.0) if pf else 0.0
    trend_penalty     = (polyfit_score / 100.0) * 0.2
    raw               = base_score + isolation_penalty + trend_penalty

    last_t       = _STATE["last_data_time"].get(machine_id, 0)
    data_missing = last_t > 0 and (time.time() - last_t) > DATA_MISSING_TIMEOUT_SEC
    if data_missing:
        raw += DATA_MISSING_RISK_PENALTY / 100.0
        _STATE["connection_status"][machine_id] = "Data Missing"

    risk_pct = max(0.0, min(100.0, _sigmoid(raw) * 100.0))
    return round(risk_pct, 2), data_missing


# ──────────────────────────────────────────────────────────────────────────────
# FAULT CLASSIFICATION + EXPLAINABILITY
# ──────────────────────────────────────────────────────────────────────────────
def _classify_fault(z_scores, delta):
    high_temp    = z_scores.get("temperature_C", 0) > 2.5
    high_vib     = z_scores.get("vibration_mm_s", 0) > 2.5
    high_current = z_scores.get("current_A", 0) > 2.5
    low_rpm      = z_scores.get("rpm", 0) > 2.5 and delta.get("rpm", 0.0) < 0
    count = sum([high_temp, high_vib, high_current, low_rpm])
    if count >= 3:       return "compound_fault"
    if high_vib and high_temp: return "bearing_wear"
    if high_current and low_rpm: return "motor_overload"
    if high_temp:        return "cooling_failure"
    if high_vib:         return "mechanical_imbalance"
    return "general_anomaly"


def _generate_explanation(machine_id, features, if_anomaly, etf_dict, risk_pct):
    z_scores   = features["z_scores"]
    delta      = features["delta"]
    latest     = features["latest"]
    b          = _STATE["baselines"][machine_id]
    fault_type = _classify_fault(z_scores, delta)

    finite = [v for v in etf_dict.values() if v != float("inf")]
    min_etf = min(finite) if finite else float("inf")
    if min_etf < 60:
        etf_str = "⏱️ Failure could occur within the next minute."
    elif min_etf < 300:
        etf_str = "⏱️ At this rate, failure is estimated within 5 minutes."
    elif min_etf < 600:
        etf_str = "⏱️ Trending toward failure within 10 minutes if unchecked."
    else:
        etf_str = ""

    templates = {
        "bearing_wear": (
            f"⚠️ {machine_id} needs attention — vibration has been steadily "
            f"climbing over the last 2 minutes and heat is building up. This "
            f"pattern usually means the bearings are under stress. If ignored, "
            f"this could lead to a full mechanical failure."
        ),
        "motor_overload": (
            f"⚠️ {machine_id} is showing signs of strain — the motor is drawing "
            f"more current than normal while the speed is dropping. The motor may "
            f"be overheating or working against a blockage. Recommend inspecting "
            f"immediately."
        ),
        "cooling_failure": (
            f"⚠️ {machine_id} is running hot — temperature has been rising "
            f"steadily and is now well above its normal range. The cooling system "
            f"may not be working properly. Left unchecked, this could damage "
            f"internal components."
        ),
        "mechanical_imbalance": (
            f"⚠️ {machine_id} is vibrating more than usual — this could be a "
            f"loose component, worn part, or something stuck in the mechanism. "
            f"Best to inspect before it causes further damage."
        ),
        "compound_fault": (
            f"🚨 {machine_id} — URGENT: Multiple warning signs detected at the "
            f"same time. Temperature, vibration, and current are all behaving "
            f"abnormally. This machine needs immediate human inspection — "
            f"do not wait."
        ),
        "general_anomaly": (
            f"⚠️ {machine_id} — Unusual sensor readings detected. Please inspect "
            f"the machine to verify normal operation."
        ),
    }

    part1 = templates.get(fault_type, templates["general_anomaly"])
    if etf_str:
        part1 += " " + etf_str

    max_sensor = max(z_scores, key=z_scores.get)
    max_val    = float(latest.get(max_sensor, b[max_sensor]["mean"]))
    bm         = b[max_sensor]["mean"]
    ratio      = round(max_val / bm, 1) if bm != 0 else 1.0

    sorted_s  = sorted(z_scores.items(), key=lambda kv: kv[1], reverse=True)
    delta_s   = sorted_s[1][0] if len(sorted_s) > 1 else sorted_s[0][0]
    dv        = delta.get(delta_s, 0.0)
    if_text   = (
        "Isolation Forest flagged this as anomalous."
        if if_anomaly
        else "Isolation Forest score: normal."
    )

    # CHANGED: Layer 6 — append Trend Severity to Part 2
    pf        = _STATE.get(f"polyfit_{machine_id}", {})
    pf_score  = pf.get("score", 0.0) if pf else 0.0
    pf_slopes = pf.get("slopes", {}) if pf else {}
    pf_sevs   = pf.get("severities", {}) if pf else {}
    worst_pf  = max(pf_sevs, key=pf_sevs.get) if pf_sevs else max_sensor
    w_slope   = pf_slopes.get(worst_pf, 0.0)
    w_dir     = "↑ Rising" if w_slope > 1e-6 else ("↓ Falling" if w_slope < -1e-6 else "→ Stable")

    part2 = (
        f"📊 Technical Detail: {max_sensor} is {ratio}x above normal baseline "
        f"and {delta_s} is changing at {dv:+.3f} units/sec. "
        f"{if_text} Fault Type: {fault_type.replace('_', ' ').title()}. "
        f"Risk Score: {risk_pct:.1f}% | "
        f"Trend Severity: {pf_score:.0f}% ({worst_pf} {w_dir})"
    )

    return part1, part2, fault_type


# ──────────────────────────────────────────────────────────────────────────────
# PREDICTION LOGGER — writes ground truth + predictions to predictions_log.csv
# ──────────────────────────────────────────────────────────────────────────────
import csv as _csv

_PRED_LOG = "predictions_log.csv"
_PRED_HEADER = ["timestamp", "machine_id", "server_status", "actual_fault",
                "risk_pct", "predicted_fault", "our_label",
                "if_anomaly", "polyfit_score"]
_PRED_HEADER_WRITTEN = False

def _log_prediction(machine_id, latest, risk_pct, if_anomaly, polyfit_score, breach_count=0):
    global _PRED_HEADER_WRITTEN
    server_status   = str(latest.get("status", "running")).lower()
    actual_fault    = 1 if server_status in ("warning", "fault") else 0
    min_breach      = _MIN_BREACH_FOR_ALERT.get(machine_id, 1)
    predicted_fault = 1 if (risk_pct >= _alert_threshold(machine_id) and breach_count >= min_breach) else 0
    our_label       = ("HIGH" if risk_pct >= 70 else
                       "MODERATE" if risk_pct >= 40 else "STABLE")
    row = [
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        machine_id, server_status, actual_fault,
        round(risk_pct, 2), predicted_fault, our_label,
        int(if_anomaly), round(polyfit_score, 1),
    ]
    try:
        write_header = not _PRED_HEADER_WRITTEN and not os.path.isfile(_PRED_LOG)
        with open(_PRED_LOG, "a", newline="") as f:
            w = _csv.writer(f)
            if write_header:
                w.writerow(_PRED_HEADER)
            w.writerow(row)
        _PRED_HEADER_WRITTEN = True
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# 7. AGENT DECISION FUNCTION
# ──────────────────────────────────────────────────────────────────────────────
def run_agent_loop():
    priority_queue = []

    for machine_id in MACHINE_IDS:
        if not _STATE["buffers"][machine_id]:
            continue

        features = compute_features(machine_id)
        if features is None:
            continue

        if_anomaly = run_isolation_forest(
            machine_id, features["latest"], features["delta"]
        )
        etf_dict     = compute_etf(machine_id)
        # ADDED: compute polyfit confidence before risk (risk reads it)
        pf_result    = compute_polyfit_confidence(machine_id)
        _STATE[f"polyfit_{machine_id}"] = pf_result
        risk_pct, _missing = compute_risk(machine_id, features, if_anomaly, etf_dict)

        heapq.heappush(priority_queue, (-risk_pct, machine_id))

        _STATE[f"risk_{machine_id}"]       = risk_pct
        _STATE[f"features_{machine_id}"]   = features
        _STATE[f"etf_{machine_id}"]        = etf_dict
        _STATE[f"if_anomaly_{machine_id}"] = if_anomaly

        now        = time.time()
        last_alert = _STATE["last_alert_time"].get(machine_id, 0.0)
        cooldown_ok = (now - last_alert) >= ALERT_COOLDOWN_SEC

        # ── Prediction counter — increments every tick risk is high ──────────
        # Counts model PREDICTIONS, not alert firings, so it is independent
        # of the 60-second alert cooldown.
        if risk_pct >= _alert_threshold(machine_id):
            _STATE["breach_counts"][machine_id] += 1
        else:
            _STATE["breach_counts"][machine_id] = 0
        prediction_count = _STATE["breach_counts"][machine_id]

        # ADDED: prediction logger — write one row per machine per tick
        # Uses breach_count so predicted_fault reflects the gate (not raw threshold)
        _log_prediction(machine_id, features["latest"], risk_pct,
                        if_anomaly, pf_result["score"], breach_count=prediction_count)

        # ── Maintenance scheduler (runs every tick, not gated by cooldown) ───
        maintenance_due   = False
        maintenance_level = ""
        for min_risk, required, level in MAINTENANCE_RULES:
            if risk_pct >= min_risk and prediction_count >= required:
                maintenance_due   = True
                maintenance_level = level
                break

        last_maint = _STATE["last_maintenance_time"].get(machine_id, 0.0)
        maint_cooldown_ok = (now - last_maint) >= MAINTENANCE_COOLDOWN_SEC

        if maintenance_due and maint_cooldown_ok:
            maint_payload = {
                "machine_id":        machine_id,
                "risk_score":        risk_pct,
                "reason":            "maintenance_scheduled",
                "timestamp":         datetime.now(timezone.utc).isoformat(),
                "maintenance_level": maintenance_level,
                "prediction_count":  prediction_count,
            }
            try:
                requests.post(
                    f"{BASE_URL}/schedule-maintenance",
                    json=maint_payload, timeout=3,
                )
                _STATE["last_maintenance_time"][machine_id] = now
                _fault_type   = _classify_fault(features["z_scores"], features["delta"])
                _worst_sensor = max(features["z_scores"], key=features["z_scores"].get)
                _worst_z      = round(features["z_scores"][_worst_sensor], 2)
                _STATE["maintenance_log"].append({
                    "machine_id":       machine_id,
                    "level":            maintenance_level,
                    "risk_pct":         round(risk_pct, 1),
                    "prediction_count": prediction_count,
                    "time":             datetime.now().strftime("%H:%M:%S"),
                    "timestamp_unix":   now,
                    "status":           "Scheduled",
                    "fault_type":       _fault_type,
                    "worst_sensor":     _worst_sensor,
                    "worst_z":          _worst_z,
                    "if_anomaly":       if_anomaly,
                    "polyfit_score":    round(pf_result["score"], 1),
                })
                _STATE["log_messages"].append(
                    f"[{machine_id}] 🔧 Maintenance scheduled — "
                    f"level={maintenance_level}  predictions={prediction_count}  "
                    f"risk={risk_pct:.1f}%"
                )
            except Exception as e:
                _STATE["log_messages"].append(
                    f"Maintenance POST failed ({machine_id}): {e}"
                )

        min_breach = _MIN_BREACH_FOR_ALERT.get(machine_id, 1)
        if risk_pct >= _alert_threshold(machine_id) and cooldown_ok and prediction_count >= min_breach:
            part1, part2, fault_type = _generate_explanation(
                machine_id, features, if_anomaly, etf_dict, risk_pct
            )
            payload = {
                "machine_id": machine_id,
                "risk_score": risk_pct,
                "reason":     fault_type,
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            }
            try:
                requests.post(f"{BASE_URL}/alert", json=payload, timeout=3)
            except Exception as e:
                _STATE["log_messages"].append(
                    f"Alert POST failed ({machine_id}): {e}"
                )

            alert_entry = {
                "machine_id":        machine_id,
                "time":              datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "risk_pct":          risk_pct,
                "human_explanation": part1,
                "technical_detail":  part2,
                "fault_type":        fault_type,
                "outcome":           "Pending",
                "timestamp_unix":    now,
            }
            _STATE["last_alert_time"][machine_id] = now
            _STATE["unconfirmed_alerts"][machine_id] = alert_entry
            _STATE["log_messages"].append(
                f"ALERT [{machine_id}] risk={risk_pct:.1f}% | fault={fault_type}"
            )
    _STATE["priority_queue"] = priority_queue


# ──────────────────────────────────────────────────────────────────────────────
# 8. STREAMLIT UI — CALLBACKS + RENDER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────
def _on_maint_ack(machine_id):
    log = _STATE.get("maintenance_log", [])
    for entry in reversed(log):
        if entry["machine_id"] == machine_id and entry.get("status") != "Acknowledged":
            entry["status"] = "Acknowledged"
            _STATE["log_messages"].append(
                f"[{machine_id}] Maintenance acknowledged by operator."
            )
            break


def _on_confirm(machine_id):
    alert = _STATE["unconfirmed_alerts"].get(machine_id)
    if alert:
        alert["outcome"] = "Confirmed"
        _STATE["alert_log"].append(dict(alert))
        _STATE["unconfirmed_alerts"][machine_id] = None
        # Lower Z threshold slightly — confirmed true positive means we can be
        # more aggressive; floor at 2.0 to prevent over-sensitisation
        old = _STATE["learned_thresholds"].get(machine_id, Z_DEFAULT_THRESHOLD)
        new = round(max(2.0, old - 0.1), 2)
        _STATE["learned_thresholds"][machine_id] = new
        _STATE["log_messages"].append(
            f"[{machine_id}] Fault confirmed — threshold tightened {old}σ → {new}σ"
        )


def _on_false_positive(machine_id):
    alert = _STATE["unconfirmed_alerts"].get(machine_id)
    if alert:
        alert["outcome"] = "False Positive"
        _STATE["alert_log"].append(dict(alert))
        _STATE["unconfirmed_alerts"][machine_id] = None
        old = _STATE["learned_thresholds"].get(machine_id, Z_DEFAULT_THRESHOLD)
        new = round(min(old + 0.15, 5.0), 2)   # cap at 5.0 — never go fully blind
        _STATE["learned_thresholds"][machine_id] = new
        _STATE["log_messages"].append(
            f"[{machine_id}] False positive — threshold relaxed {old}σ → {new}σ"
        )


def _etf_summary(etf_dict):
    finite = [v for v in etf_dict.values() if v != float("inf")]
    if not finite:
        return None, "stable"
    m = min(finite)
    if m < 60:   return m, "critical"
    if m < 300:  return m, "warning"
    return m, "normal"


def _render_machine_column(machine_id, col, tick):
    with col:
        conn = _STATE["connection_status"].get(machine_id, "Connecting")
        badge = (
            "🟢 Live"         if conn == "Live"         else
            "🟡 Data Missing" if conn == "Data Missing" else
            "🔴 Disconnected"
        )
        thr = _STATE["learned_thresholds"].get(machine_id, Z_DEFAULT_THRESHOLD)
        st.markdown(f"### {machine_id}")
        st.caption(f"{badge}  |  threshold: {thr:.2f}σ")

        features = _STATE.get(f"features_{machine_id}")
        if features and features.get("latest"):
            lat = features["latest"]
            mc1, mc2 = st.columns(2)
            with mc1:
                st.metric("🌡️ Temp °C",  f"{float(lat.get('temperature_C', 0)):.1f}")
                st.metric("🔄 RPM",       f"{float(lat.get('rpm', 0)):.0f}")
            with mc2:
                st.metric("📳 Vib mm/s", f"{float(lat.get('vibration_mm_s', 0)):.2f}")
                st.metric("⚡ Current A", f"{float(lat.get('current_A', 0)):.2f}")
        else:
            st.info("Waiting for first reading…")

        risk_pct = float(_STATE.get(f"risk_{machine_id}", 0.0))
        progress_val = min(max(risk_pct / 100.0, 0.0), 1.0)
        if risk_pct > 70:
            icon, label = "🔴", "HIGH RISK"
        elif risk_pct > 40:
            icon, label = "🟠", "MODERATE"
        else:
            icon, label = "🟢", "STABLE"
        st.markdown(f"**Risk: {icon} {risk_pct:.1f}% — {label}**")
        st.progress(progress_val)

        # ADDED: Layer 8 — Polyfit Confidence Score card + sensor trend table
        pf       = _STATE.get(f"polyfit_{machine_id}", {})
        pf_score = pf.get("score", 0.0) if pf else 0.0
        slopes   = pf.get("slopes",     {}) if pf else {}
        sevs     = pf.get("severities", {}) if pf else {}
        worst_s  = max(sevs, key=sevs.get) if sevs else SENSORS[0]
        w_sl     = slopes.get(worst_s, 0.0)
        w_dir    = "↑ Rising" if w_sl > 1e-6 else ("↓ Falling" if w_sl < -1e-6 else "→ Stable")

        if pf_score > 60:
            ts_icon, ts_color = "🔴", "red"
        elif pf_score > 30:
            ts_icon, ts_color = "🟠", "orange"
        else:
            ts_icon, ts_color = "🟢", "green"

        st.markdown(
            f"**📈 Trend Severity: {ts_icon} {pf_score:.0f}% — {w_dir}**"
        )
        st.progress(min(pf_score / 100.0, 1.0))

        rows = []
        for s in SENSORS:
            sl = slopes.get(s, 0.0)
            direction = "↑ Rising" if sl > 1e-6 else ("↓ Falling" if sl < -1e-6 else "→ Stable")
            rows.append({"Sensor": s, "Trend": direction})
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            height=180,
        )

        etf_dict = _STATE.get(f"etf_{machine_id}", {})
        etf_val, etf_state = _etf_summary(etf_dict)
        # Only show CRITICAL/WARNING ETF when risk is also elevated,
        # preventing noisy polyfit slopes from alarming on healthy machines.
        if etf_state == "critical" and risk_pct < 60:
            etf_state = "warning"
        if etf_state == "warning" and risk_pct < 55:
            etf_state = "normal"
        if etf_state == "stable":
            st.success("✅ Stable — No failure projected")
        elif etf_state == "critical":
            if etf_val == 0:
                st.error("🚨 Already in failure zone — CRITICAL")
            else:
                st.error(f"⏱️ ~{int(etf_val)}s to threshold — CRITICAL")
        elif etf_state == "warning":
            if etf_val == 0:
                st.warning("⚠️ At failure threshold — WARNING")
            else:
                st.warning(f"⏱️ ~{int(etf_val)}s to threshold — WARNING")
        else:
            if etf_val is not None and etf_val < 10:
                st.info("📉 Near threshold boundary — low current risk")
            else:
                st.info(f"⏱️ ~{int(etf_val)}s to threshold — low risk")

        unconfirmed = _STATE["unconfirmed_alerts"].get(machine_id)
        if unconfirmed:
            st.markdown("---")
            st.markdown(unconfirmed["human_explanation"])
            st.markdown("---")
            st.caption(unconfirmed["technical_detail"])
            bc1, bc2 = st.columns(2)
            with bc1:
                st.button(
                    "✅ Confirm",
                    key=f"confirm_{machine_id}_{tick}",
                    on_click=_on_confirm,
                    args=(machine_id,),
                    use_container_width=True,
                )
            with bc2:
                st.button(
                    "❌ False Positive",
                    key=f"fp_{machine_id}_{tick}",
                    on_click=_on_false_positive,
                    args=(machine_id,),
                    use_container_width=True,
                )


def _render_alert_log():
    st.markdown("---")
    st.subheader("📋 Alert Log")
    log = _STATE["alert_log"]
    if not log:
        st.info("No alerts logged yet.")
        return
    df = pd.DataFrame(log)
    display = ["machine_id", "time", "risk_pct",
               "human_explanation", "technical_detail", "outcome"]
    present = [c for c in display if c in df.columns]
    st.dataframe(
        df[present].rename(columns={
            "machine_id":        "Machine",
            "time":              "Time",
            "risk_pct":          "Risk %",
            "human_explanation": "Human Explanation",
            "technical_detail":  "Technical Detail",
            "outcome":           "Outcome",
        }),
        use_container_width=True,
        hide_index=True,
    )


_LEVEL_BADGE    = {"CRITICAL": "🔴", "VERY HIGH": "🟠", "HIGH": "🟡"}
_LEVEL_PRIORITY = {"CRITICAL": 1,    "VERY HIGH": 2,    "HIGH": 3}

_SENSOR_LABEL = {
    "temperature_C":  "temperature spiking",
    "vibration_mm_s": "abnormal vibration",
    "rpm":            "RPM deviation",
    "current_A":      "current overload",
}
_FAULT_DESC = {
    "bearing_wear":        "Bearing Wear — vibration and heat rising together",
    "motor_overload":      "Motor Overload — high current with dropping RPM",
    "cooling_failure":     "Cooling Failure — temperature climbing steadily",
    "mechanical_imbalance":"Mechanical Imbalance — unusual vibration pattern",
    "compound_fault":      "Compound Fault — multiple sensors anomalous simultaneously",
    "general_anomaly":     "General Anomaly — sensor readings outside normal range",
}

def _maintenance_reason(entry):
    level   = entry.get("level", "HIGH")
    fault   = _FAULT_DESC.get(entry.get("fault_type", ""), "Sensor anomaly detected")
    worst   = entry.get("worst_sensor", "")
    worst_z = entry.get("worst_z", 0)
    cnt     = entry.get("prediction_count", 0)
    risk    = entry.get("risk_pct", 0)
    pf      = entry.get("polyfit_score", 0)
    if_flag = entry.get("if_anomaly", False)

    urgency = {
        "CRITICAL":  "🚨 Immediate action required",
        "VERY HIGH": "⚠️ Urgent — intervene soon",
        "HIGH":      "🔔 Scheduled inspection needed",
    }.get(level, "")

    sensor_str = _SENSOR_LABEL.get(worst, worst)
    lines = [
        f"**Why:** {urgency}",
        f"**Fault pattern:** {fault}",
        f"**Primary indicator:** {sensor_str} (z={worst_z}σ above baseline)",
        f"**Confidence:** Risk stayed at {risk}% for {cnt} consecutive model predictions",
    ]
    if if_flag:
        lines.append("**IsolationForest:** independently flagged this reading as anomalous")
    if pf >= 50:
        lines.append(f"**Trend severity:** {pf}% — sensors trending sharply toward failure")
    return "\n\n".join(lines)


def _build_maintenance_queue(algorithm):
    """Return ordered list of latest unacknowledged maintenance entries."""
    log = _STATE.get("maintenance_log", [])
    latest = {}
    for entry in log:
        mid = entry["machine_id"]
        if entry.get("status") != "Acknowledged":
            latest[mid] = entry
    queue = list(latest.values())

    if algorithm == "Priority Queue (Urgency First)":
        queue.sort(key=lambda e: (
            _LEVEL_PRIORITY.get(e["level"], 9), -e["risk_pct"]
        ))
    elif algorithm == "FCFS (First Come First Served)":
        queue.sort(key=lambda e: e.get("timestamp_unix", 0))
    elif algorithm == "SJF (Shortest Job First)":
        # Lowest risk = least severe = quickest fix
        queue.sort(key=lambda e: e["risk_pct"])
    return queue


def _render_maintenance_dashboard(tick):
    st.markdown("---")
    st.subheader("🔧 Maintenance Scheduler")

    _ALGO_OPTIONS = [
        "Priority Queue (Urgency First)",
        "FCFS (First Come First Served)",
        "SJF (Shortest Job First)",
    ]
    _saved_algo = _STATE.get("maint_algo", _ALGO_OPTIONS[0])
    _saved_idx  = _ALGO_OPTIONS.index(_saved_algo) if _saved_algo in _ALGO_OPTIONS else 0
    algo = st.selectbox(
        "Scheduling Algorithm",
        _ALGO_OPTIONS,
        index=_saved_idx,
        key=f"maint_algo_{tick}",
        help=(
            "Priority Queue: most critical machines first.\n"
            "FCFS: machines scheduled earliest go first.\n"
            "SJF: quickest/least-severe jobs dispatched first."
        ),
    )
    _STATE["maint_algo"] = algo

    queue = _build_maintenance_queue(algo)

    if not queue:
        st.success("✅ No maintenance currently scheduled across all machines.")
    else:
        st.caption(f"**{len(queue)} machine(s) in queue** — ordered by: {algo}")
        for pos, entry in enumerate(queue, start=1):
            mid   = entry["machine_id"]
            badge = _LEVEL_BADGE.get(entry["level"], "⚪")
            live_risk = float(_STATE.get(f"risk_{mid}", 0.0))
            live_cnt  = _STATE["breach_counts"].get(mid, 0)

            with st.expander(
                f"#{pos}  {badge} {mid}  —  {entry['level']}  |  "
                f"Risk: {entry['risk_pct']}%  |  Scheduled: {entry['time']}",
                expanded=(pos == 1),
            ):
                st.markdown(_maintenance_reason(entry))
                st.caption(
                    f"Live now → risk: {live_risk:.1f}%  |  "
                    f"consecutive predictions: {live_cnt}"
                )
                st.button(
                    "✔ Acknowledge & Dispatch",
                    key=f"maint_ack_{mid}_{tick}",
                    on_click=_on_maint_ack,
                    args=(mid,),
                    use_container_width=True,
                )

    log = _STATE.get("maintenance_log", [])
    if log:
        with st.expander("📋 Full Maintenance History", expanded=False):
            history_cols = ["machine_id", "time", "level", "risk_pct",
                            "prediction_count", "fault_type", "worst_sensor",
                            "worst_z", "polyfit_score", "status"]
            df = pd.DataFrame(list(reversed(log[-50:])))
            present = [c for c in history_cols if c in df.columns]
            st.dataframe(
                df[present].rename(columns={
                    "machine_id":       "Machine",
                    "time":             "Time",
                    "level":            "Level",
                    "risk_pct":         "Risk %",
                    "prediction_count": "Predictions",
                    "fault_type":       "Fault Type",
                    "worst_sensor":     "Worst Sensor",
                    "worst_z":          "Z-score",
                    "polyfit_score":    "Trend %",
                    "status":           "Status",
                }),
                use_container_width=True,
                hide_index=True,
            )


def _maint_queue_fingerprint():
    """Changes only when entries are added or acknowledged."""
    log = _STATE.get("maintenance_log", [])
    return tuple((e["machine_id"], e.get("status", "")) for e in log)


def render_dashboard(placeholder, maint_placeholder):
    _STATE["render_tick"] += 1
    tick = _STATE["render_tick"]

    # ── Fast-update section (replaces every second) ───────────────────────────
    with placeholder.container():
        at_risk = sum(
            1 for mid in MACHINE_IDS
            if float(_STATE.get(f"risk_{mid}", 0.0)) >= _alert_threshold(mid)
        )
        if at_risk == 0:
            st.success("✅ All systems nominal")
        else:
            st.error(
                f"🚨 {at_risk} machine{'s' if at_risk > 1 else ''} at risk"
            )

        cols = st.columns(4)
        for i, machine_id in enumerate(MACHINE_IDS):
            _render_machine_column(machine_id, cols[i], tick)

        _render_alert_log()

        with st.expander("🔧 System Log", expanded=False):
            msgs = list(_STATE["log_messages"])
            if msgs:
                st.code("\n".join(reversed(msgs[-50:])), language=None)
            else:
                st.caption("No log messages yet.")

    # ── Maintenance section — only re-renders when queue changes ─────────────
    # Keeping it in its own stable placeholder prevents confirm/FP button
    # reruns from destroying and recreating the maintenance widgets.
    new_fp = _maint_queue_fingerprint()
    if _STATE.get("_maint_fp") != new_fp:
        _STATE["_maint_fp"] = new_fp
        with maint_placeholder.container():
            _render_maintenance_dashboard(tick)


# ──────────────────────────────────────────────────────────────────────────────
# 9. MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
def main():
    global _THREADS_STARTED

    st.set_page_config(
        page_title="Predictive Maintenance Agent",
        page_icon="🏭",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    init_state()
    load_assets()

    if not _THREADS_STARTED:
        for machine_id in MACHINE_IDS:
            t = threading.Thread(
                target=stream_worker, args=(machine_id,), daemon=True
            )
            t.start()
        _THREADS_STARTED = True

    st.title("🏭 Self-Evolving Predictive Maintenance Agent")
    st.caption(
        f"Monitoring: {' · '.join(MACHINE_IDS)}  |  API: {BASE_URL}"
    )

    placeholder       = st.empty()   # machine columns + alert log (1-sec updates)
    maint_placeholder = st.empty()   # maintenance scheduler (updates on queue change only)

    while True:
        run_agent_loop()
        render_dashboard(placeholder, maint_placeholder)
        time.sleep(1.0)


if __name__ == "__main__":
    main()
