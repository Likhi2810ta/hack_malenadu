import requests
import pandas as pd
import json
import joblib
from sklearn.ensemble import IsolationForest

BASE_URL = "http://localhost:3000"
MACHINE_IDS = ["CNC_01", "CNC_02", "PUMP_03", "CONVEYOR_04"]
SENSORS = ["temperature_C", "vibration_mm_s", "rpm", "current_A"]

print("Fetching history from live server...\n")

all_frames = []
for mid in MACHINE_IDS:
    resp = requests.get(f"{BASE_URL}/history/{mid}", timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    readings = payload.get("readings", payload) if isinstance(payload, dict) else payload
    df = pd.DataFrame(readings)
    df["machine_id"] = mid
    all_frames.append(df)
    print(f"  {mid}: {len(df)} rows  |  "
          f"rpm {df['rpm'].mean():.0f}±{df['rpm'].std():.0f}  "
          f"temp {df['temperature_C'].mean():.1f}±{df['temperature_C'].std():.1f}  "
          f"current {df['current_A'].mean():.2f}±{df['current_A'].std():.2f}")

full = pd.concat(all_frames, ignore_index=True)

baselines = {}
for mid, grp in full.groupby("machine_id"):
    baselines[mid] = {}
    for s in SENSORS:
        col = grp[s].dropna()
        baselines[mid][s] = {
            "mean": round(float(col.mean()), 4),
            "std":  round(float(col.std()),  4),
            "min":  round(float(col.min()),  4),
            "max":  round(float(col.max()),  4),
        }

with open("baselines.json", "w") as f:
    json.dump(baselines, f, indent=2)
print("\nSaved baselines.json")

for mid, grp in full.groupby("machine_id"):
    running = grp[grp["status"] == "running"] if "status" in grp.columns else grp
    X = running[SENSORS].dropna().values
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X)
    fname = f"model_{mid}.pkl"
    joblib.dump(model, fname)
    print(f"Saved {fname}  (trained on {len(X)} rows)")

print("\nDone — restart Streamlit to load new baselines.")
