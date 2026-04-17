import pandas as pd
import numpy as np
import json
import joblib
import os
import time
from datetime import datetime, timezone

BASELINES_PATH = "baselines.json"
LIVE_CSV = "live_sensor_feed.csv"
ALERT_LOG = "anomaly_log.csv"
SENSORS = ["temperature_C", "vibration_mm_s", "rpm", "current_A"]
Z_THRESHOLD = 3.0
POLL_INTERVAL_SEC = 2.0

with open(BASELINES_PATH) as f:
    baselines = json.load(f)

models = {}
for machine_id in baselines:
    path = f"model_{machine_id}.pkl"
    if os.path.isfile(path):
        models[machine_id] = joblib.load(path)
    else:
        print(f"WARNING: {path} not found — ML check disabled for {machine_id}")

alert_columns = [
    "detected_at", "machine_id", "timestamp", "sensor",
    "value", "mean", "std", "z_score",
    "stat_alert", "ml_alert", "severity",
]

if not os.path.isfile(ALERT_LOG):
    pd.DataFrame(columns=alert_columns).to_csv(ALERT_LOG, index=False)

last_processed_index = 0

def z_score(value, mean, std):
    if std == 0:
        return 0.0
    return abs((value - mean) / std)

def severity(z):
    if z >= 5.0:
        return "CRITICAL"
    if z >= 4.0:
        return "HIGH"
    if z >= Z_THRESHOLD:
        return "MEDIUM"
    return "LOW"

def ml_predict(machine_id, row_values):
    if machine_id not in models:
        return False
    X = np.array(row_values).reshape(1, -1)
    pred = models[machine_id].predict(X)
    return int(pred[0]) == -1

def process_new_rows(df):
    global last_processed_index
    new_rows = df.iloc[last_processed_index:]
    if new_rows.empty:
        return

    alerts = []
    for _, row in new_rows.iterrows():
        mid = row["machine_id"]
        if mid not in baselines:
            continue
        b = baselines[mid]
        sensor_values = [float(row[s]) for s in SENSORS]

        ml_flag = ml_predict(mid, sensor_values)

        for i, sensor in enumerate(SENSORS):
            val = sensor_values[i]
            mean = b[sensor]["mean"]
            std = b[sensor]["std"]
            z = z_score(val, mean, std)
            stat_flag = z >= Z_THRESHOLD

            if stat_flag or ml_flag:
                alerts.append({
                    "detected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                    "machine_id": mid,
                    "timestamp": row["timestamp"],
                    "sensor": sensor,
                    "value": round(val, 4),
                    "mean": round(mean, 4),
                    "std": round(std, 4),
                    "z_score": round(z, 4),
                    "stat_alert": stat_flag,
                    "ml_alert": ml_flag,
                    "severity": severity(z),
                })

    last_processed_index += len(new_rows)

    if alerts:
        alert_df = pd.DataFrame(alerts, columns=alert_columns)
        alert_df.to_csv(ALERT_LOG, mode="a", header=False, index=False)
        for _, a in alert_df.iterrows():
            print(
                f"  [{a['severity']:8s}] {a['machine_id']}  {a['sensor']:18s} "
                f"val={a['value']:8.3f}  z={a['z_score']:6.2f}  "
                f"stat={'Y' if a['stat_alert'] else 'N'}  ml={'Y' if a['ml_alert'] else 'N'}  "
                f"@ {a['timestamp']}"
            )

print(f"Anomaly detector running — watching {LIVE_CSV}  (Ctrl+C to stop)")
print(f"Z-score threshold: {Z_THRESHOLD}   Alert log: {ALERT_LOG}\n")

try:
    while True:
        if os.path.isfile(LIVE_CSV):
            df = pd.read_csv(LIVE_CSV)
            process_new_rows(df)
        else:
            print(f"Waiting for {LIVE_CSV} ...")
        time.sleep(POLL_INTERVAL_SEC)
except KeyboardInterrupt:
    print(f"\nStopped. Processed {last_processed_index} rows total.")
    summary = pd.read_csv(ALERT_LOG)
    print(f"Total alerts logged: {len(summary)}")
    if not summary.empty:
        print("\nAlerts by machine and severity:")
        print(summary.groupby(["machine_id", "severity"]).size().to_string())
