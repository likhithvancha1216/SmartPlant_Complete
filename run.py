"""Generate source data, schedule operations, validate, and export results."""
from pathlib import Path
import json, hashlib
import pandas as pd
from smartplant.generator import generate_data
from smartplant.scheduler import run_scheduler
from smartplant.validation import validate_data, validate_schedule
from smartplant.database import create_database
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

def main():
    data = generate_data()
    for name, frame in data.items():
        frame.to_csv(DATA_DIR / f"{name}.csv", index=False)
    data_errors = validate_data(data)
    schedule, exceptions = run_scheduler(data)
    schedule.to_csv(DATA_DIR / "operation_schedule.csv", index=False)
    exceptions.to_csv(DATA_DIR / "scheduling_exceptions.csv", index=False)
    schedule_errors = validate_schedule(data, schedule)
    # Event history records schedule decisions and exceptions separately from source tables.
    events = []
    for _, row in schedule.iterrows():
        events.append({"event_type":"OPERATION_SCHEDULED", "entity_id":row.operation_id,
                       "event_time":row.operation_start, "detail":f"Assigned {row.machine_id}; tools={row.tool_ids}"})
    for _, row in exceptions.iterrows():
        events.append({"event_type":"SCHEDULING_EXCEPTION", "entity_id":row.operation_id,
                       "event_time":"", "detail":row.exception})
    pd.DataFrame(events, columns=["event_type","entity_id","event_time","detail"]).to_csv(DATA_DIR/"event_history.csv", index=False)
    # Ground-truth catalog describes separate labelled negative fixtures; it never enters the scheduler.
    gt = pd.DataFrame([
      {"scenario_id":"GT-001","scenario":"MACHINE_OVERLAP","expected_detection":"machine overlap","description":"Two operations on the same machine have intersecting occupied intervals."},
      {"scenario_id":"GT-002","scenario":"PRECEDENCE_VIOLATION","expected_detection":"precedence violation","description":"A downstream operation starts before its predecessor finishes."},
      {"scenario_id":"GT-003","scenario":"MATERIAL_BEFORE_AVAILABILITY","expected_detection":"material unavailable at operation start","description":"An operation starts before its required inventory lot is available."},
      {"scenario_id":"GT-004","scenario":"OUTSIDE_SHIFT","expected_detection":"outside shift","description":"An operation is placed outside its machine shift calendar."},
      {"scenario_id":"GT-005","scenario":"CHANGEOVER_OMITTED","expected_detection":"changeover duration mismatch","description":"A family transition is scheduled without the required setup interval."}
    ])
    gt.to_csv(DATA_DIR/"ground_truth.csv", index=False)
    # Create relational SQLite database and SQL seed export.
    create_database()
    manifest = {"seed":20261022,"planning_days":60,"tables":{},"validation":{"data_errors":data_errors,"schedule_errors":schedule_errors},
                "counts":{"scheduled_operations":len(schedule),"exceptions":len(exceptions)}}
    for path in sorted(DATA_DIR.glob("*.csv")):
        raw=path.read_bytes(); manifest["tables"][path.name]={"rows":max(0, sum(1 for _ in path.open(encoding="utf-8"))-1),"sha256":hashlib.sha256(raw).hexdigest()}
    (DATA_DIR/"source_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print("\nSMARTPLANT PIPELINE REPORT")
    print("--------------------------")
    print("Source tables:", len(data))
    print("Scheduled operations:", len(schedule), "/", len(data["operations"]))
    print("Scheduling exceptions:", len(exceptions))
    print("Data validation:", "PASS" if not data_errors else f"FAIL ({len(data_errors)})")
    print("Schedule validation:", "PASS" if not schedule_errors else f"FAIL ({len(schedule_errors)})")
    for err in data_errors + schedule_errors: print(" -", err)
    print("Exports written to data/")
    if data_errors or schedule_errors or len(exceptions): raise SystemExit(1)

if __name__ == "__main__": main()
