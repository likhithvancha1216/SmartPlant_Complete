"""Check shared-tool capacity on an already exported schedule."""
import pandas as pd
from smartplant.generator import generate_data
from smartplant.validation import validate_schedule

if __name__ == "__main__":
    data = generate_data()
    schedule = pd.read_csv("data/operation_schedule.csv")
    errors = [e for e in validate_schedule(data, schedule) if "tool capacity" in e]
    print("SHARED TOOL CAPACITY VALIDATION:", "PASS" if not errors else "FAIL")
    for error in errors: print(" -", error)
    if errors: raise SystemExit(1)
