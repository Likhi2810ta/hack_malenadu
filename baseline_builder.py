import pandas as pd
import json
import joblib
from sklearn.ensemble import IsolationForest

SENSORS = ["temperature_C", "vibration_mm_s", "rpm", "current_A"]
CSV_PATH = "sensor_history.csv"

df = pd.read_csv(CSV_PATH)
df["timestamp"] = pd.to_datetime(df["timestamp"])

baselines = {}

for machine_id, group in df.groupby("machine_id"):
    machine_stats = {}
    for sensor in SENSORS:
        col = group[sensor]
        machine_stats[sensor] = {
            "mean": round(float(col.mean()), 4),
            "std":  round(float(col.std()), 4),
            "min":  round(float(col.min()), 4),
            "max":  round(float(col.max()), 4),
        }
    baselines[machine_id] = machine_stats

with open("baselines.json", "w") as f:
    json.dump(baselines, f, indent=2)

print("Saved baselines.json")

_CONTAMINATION = {
    "CNC_01":       0.05,
    "CNC_02":       0.05,
    "PUMP_03":      0.10,  # raised from 0.05 — recover missed faults (75.8% recall)
    "CONVEYOR_04":  0.003, # lowered from 0.01 — still 20% FPR at 0.01
}

for machine_id, group in df.groupby("machine_id"):
    running = group[group["status"] == "running"]
    X = running[SENSORS].values

    model = IsolationForest(
        n_estimators=100,
        contamination=_CONTAMINATION.get(machine_id, 0.05),
        random_state=42,
    )
    model.fit(X)

    filename = f"model_{machine_id}.pkl"
    joblib.dump(model, filename)
    print(f"Saved {filename}  (trained on {len(X)} running rows)")
