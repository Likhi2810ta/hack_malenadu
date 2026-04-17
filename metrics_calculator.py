import sys
import io
import pandas as pd
import numpy as np
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

LOG_FILE = "predictions_log.csv"

df = pd.read_csv(LOG_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp", "machine_id", "actual_fault", "predicted_fault"])
df = df.sort_values("timestamp").reset_index(drop=True)

if df.empty:
    print("No data yet — run the monitoring app first to collect readings.")
    sys.exit(0)

print(f"\n{'='*60}")
print(f"  PREDICTIVE MAINTENANCE — MODEL EVALUATION REPORT")
print(f"  Log period : {df['timestamp'].min()} to {df['timestamp'].max()}")
print(f"  Total rows : {len(df)}")
print(f"{'='*60}\n")

# ── Helper ─────────────────────────────────────────────────────────────────────
def classification_metrics(y_true, y_pred, label=""):
    TP = int(((y_true == 1) & (y_pred == 1)).sum())
    TN = int(((y_true == 0) & (y_pred == 0)).sum())
    FP = int(((y_true == 0) & (y_pred == 1)).sum())
    FN = int(((y_true == 1) & (y_pred == 0)).sum())

    precision  = TP / (TP + FP) if (TP + FP) > 0 else 0.0
    recall     = TP / (TP + FN) if (TP + FN) > 0 else 0.0
    f1         = (2 * precision * recall / (precision + recall)
                  if (precision + recall) > 0 else 0.0)
    accuracy   = (TP + TN) / (TP + TN + FP + FN) if (TP+TN+FP+FN) > 0 else 0.0
    fpr        = FP / (FP + TN) if (FP + TN) > 0 else 0.0
    mcc_denom  = ((TP+FP)*(TP+FN)*(TN+FP)*(TN+FN)) ** 0.5
    mcc        = ((TP*TN - FP*FN) / mcc_denom) if mcc_denom > 0 else 0.0

    print(f"  {label}")
    print(f"    Confusion Matrix  →  TP={TP}  TN={TN}  FP={FP}  FN={FN}")
    print(f"    Accuracy          →  {accuracy*100:.1f}%")
    print(f"    Precision         →  {precision*100:.1f}%")
    print(f"    Recall (Sens.)    →  {recall*100:.1f}%")
    print(f"    F1 Score          →  {f1*100:.1f}%")
    print(f"    False Positive Rate→ {fpr*100:.1f}%")
    print(f"    MCC               →  {mcc:.3f}")
    print()
    return dict(TP=TP, TN=TN, FP=FP, FN=FN,
                precision=precision, recall=recall, f1=f1,
                accuracy=accuracy, fpr=fpr, mcc=mcc)

# ── 1. OVERALL METRICS ─────────────────────────────────────────────────────────
print("── 1. OVERALL METRICS (all machines combined) ─────────────────")
classification_metrics(df["actual_fault"], df["predicted_fault"], "All machines")

# ── 2. PER-MACHINE METRICS ────────────────────────────────────────────────────
print("── 2. PER-MACHINE METRICS ──────────────────────────────────────")
summary_rows = []
for mid, grp in df.groupby("machine_id"):
    m = classification_metrics(grp["actual_fault"], grp["predicted_fault"], mid)
    m["machine_id"] = mid
    m["rows"] = len(grp)
    summary_rows.append(m)

summary_df = pd.DataFrame(summary_rows).set_index("machine_id")
print("\n  Summary table:")
print(summary_df[["rows","TP","FP","FN","TN",
                   "accuracy","precision","recall","f1","fpr","mcc"]]
      .rename(columns={"accuracy":"Acc","precision":"Prec",
                       "recall":"Rec","fpr":"FPR"})
      .map(lambda x: f"{x*100:.1f}%" if isinstance(x, float) else x)
      .to_string())
print()

# ── 3. DETECTION LATENCY ──────────────────────────────────────────────────────
print("── 3. DETECTION LATENCY (seconds before server flagged WARNING/FAULT) ──")
latencies = []
for mid, grp in df.groupby("machine_id"):
    grp = grp.reset_index(drop=True)
    in_fault_block = False
    fault_start_idx = None
    for i, row in grp.iterrows():
        if row["actual_fault"] == 1 and not in_fault_block:
            in_fault_block = True
            fault_start_idx = i
            # Find earliest row in this block where WE predicted fault
            block = grp[grp.index >= i]
            we_flagged = block[block["predicted_fault"] == 1]
            if len(we_flagged) > 0:
                # Find if we predicted BEFORE the fault block started
                pre_block = grp[(grp.index < i) & (grp["predicted_fault"] == 1)]
                last_pre = pre_block.tail(1)
                if len(last_pre) > 0:
                    t_server = grp.loc[fault_start_idx, "timestamp"]
                    t_us     = last_pre.iloc[0]["timestamp"]
                    latency  = (t_server - t_us).total_seconds()
                    latencies.append((mid, round(latency, 1), "Early ✅"))
                else:
                    first_we = we_flagged.iloc[0]
                    t_server = grp.loc[fault_start_idx, "timestamp"]
                    latency  = (first_we["timestamp"] - t_server).total_seconds()
                    latencies.append((mid, round(latency, 1), "Late ⚠️"))
            else:
                latencies.append((mid, None, "Missed ❌"))
        elif row["actual_fault"] == 0:
            in_fault_block = False

if latencies:
    lat_df = pd.DataFrame(latencies, columns=["Machine", "Latency_sec", "Status"])
    print(lat_df.to_string(index=False))
else:
    print("  No fault events recorded yet. Run longer to capture fault cycles.")
print()

# ── 4. RISK DISTRIBUTION ──────────────────────────────────────────────────────
print("── 4. RISK SCORE DISTRIBUTION PER MACHINE ─────────────────────")
risk_stats = (df.groupby("machine_id")["risk_pct"]
              .agg(["mean","std","min","max"])
              .round(1))
print(risk_stats.to_string())
print()

# ── 5. FALSE POSITIVE DETAIL ─────────────────────────────────────────────────
print("── 5. FALSE POSITIVES (we said HIGH, server said RUNNING) ──────")
fp_df = df[(df["predicted_fault"] == 1) & (df["actual_fault"] == 0)]
if fp_df.empty:
    print("  None — no false positives recorded.")
else:
    print(fp_df.groupby("machine_id")[["risk_pct","polyfit_score"]].mean().round(1).to_string())
print()

# ── 6. POLYFIT + ISOLATION FOREST CONTRIBUTION ────────────────────────────────
print("── 6. DETECTION METHOD CONTRIBUTION ────────────────────────────")
fault_rows = df[df["actual_fault"] == 1]
if len(fault_rows) > 0:
    if_contrib = fault_rows["if_anomaly"].mean() * 100
    pf_contrib = (fault_rows["polyfit_score"] >= 60).mean() * 100
    print(f"  On TRUE fault rows:")
    print(f"    IsolationForest flagged  : {if_contrib:.1f}% of the time")
    print(f"    Polyfit severity ≥60%    : {pf_contrib:.1f}% of the time")
else:
    print("  No fault rows yet.")
print()

print(f"{'='*60}")
print(f"  Report generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}\n")
