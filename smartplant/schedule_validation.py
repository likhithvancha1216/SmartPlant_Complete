"""Run independent validation against the exported schedule."""
import pandas as pd
from smartplant.generator import generate_data
from smartplant.validation import validate_data, validate_schedule

if __name__ == "__main__":
    data = generate_data()
    schedule_path = "data/operation_schedule.csv"
    schedule = pd.read_csv(schedule_path)
    data_errors = validate_data(data)
    schedule_errors = validate_schedule(data, schedule)
    print("DATA VALIDATION:", "PASS" if not data_errors else "FAIL")
    print("SCHEDULE VALIDATION:", "PASS" if not schedule_errors else "FAIL")
    print("Scheduled operations:", len(schedule))
    for error in data_errors + schedule_errors:
        print(" -", error)
    if data_errors or schedule_errors:
        raise SystemExit(1)
