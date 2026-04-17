import pandas as pd
import numpy as np
import json
import time
import csv
import os
from datetime import datetime, timezone

BASELINES_PATH = "baselines.json"
OUTPUT_CSV = "live_sensor_feed.csv"
INTERVAL_SEC = 1.0
FAULT_PROBABILITY = 0.04

MACHINES = ["CNC_01", "CNC_02", "PUMP_03", "CONVEYOR_04"]
SENSORS = ["temperature_C", "vibration_mm_s", "rpm", "current_A"]

with open(BASELINES_PATH) as f:
    baselines = json.load(f)

rng = np.random.default_rng(seed=None)

def normal_reading(machine_id):
    row = {}
    for sensor in SENSORS:
        b = baselines[machine_id][sensor]
        value = rng.normal(loc=b["mean"], scale=max(b["std"], 0.01))
        value = float(np.clip(value, b["min"] * 0.9, b["max"] * 1.1))
        row[sensor] = round(value, 3)
    return row

def fault_reading(machine_id):
    row = normal_reading(machine_id)
    fault_sensor = rng.choice(SENSORS)
    b = baselines[machine_id][fault_sensor]
    spike = b["mean"] + rng.uniform(3.5, 6.0) * b["std"]
    row[fault_sensor] = round(float(spike), 3)
    return row, fault_sensor

file_exists = os.path.isfile(OUTPUT_CSV)
csvfile = open(OUTPUT_CSV, "a", newline="")
writer = csv.DictWriter(
    csvfile,
    fieldnames=["machine_id", "timestamp", "temperature_C",
                 "vibration_mm_s", "rpm", "current_A", "status", "injected_fault"],
)
if not file_exists:
    writer.writeheader()
    csvfile.flush()

print(f"Streaming sensor data to {OUTPUT_CSV}  (Ctrl+C to stop)")
print(f"Fault injection probability: {FAULT_PROBABILITY * 100:.0f}% per reading\n")

try:
    tick = 0
    while True:
        tick += 1
        for machine_id in MACHINES:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            if rng.random() < FAULT_PROBABILITY:
                sensors, fault_sensor = fault_reading(machine_id)
                status = "fault"
                injected = fault_sensor
            else:
                sensors = normal_reading(machine_id)
                status = "running"
                injected = ""

            row = {"machine_id": machine_id, "timestamp": ts,
                   "status": status, "injected_fault": injected}
            row.update(sensors)
            writer.writerow(row)

        csvfile.flush()

        fault_rows = [r for r in [row] if r["status"] == "fault"]
        if fault_rows:
            for r in fault_rows:
                print(f"  [FAULT INJECTED] {r['machine_id']}  sensor={r['injected_fault']}  "
                      f"value={r[r['injected_fault']]}")

        if tick % 10 == 0:
            print(f"  tick={tick}  {datetime.now(timezone.utc).strftime('%H:%M:%S')}  "
                  f"{tick * len(MACHINES)} rows written")

        time.sleep(INTERVAL_SEC)

except KeyboardInterrupt:
    print(f"\nStopped. Total ticks: {tick}  rows written: {tick * len(MACHINES)}")
finally:
    csvfile.close()
