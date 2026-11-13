
import pandas as pd

import smartplant.generator as generator
from smartplant.generator import generate_data
from smartplant.scheduler import run_scheduler
from smartplant.validation import validate_schedule


def test_cumulative_inventory_shortage_is_detected(monkeypatch):
    # Generate a small dataset to keep the test fast.
    monkeypatch.setattr(generator, "ORDER_COUNT", 20)

    data = generate_data()
    schedule, _ = run_scheduler(data)

    # Select two valid scheduled operations.
    selected = schedule.head(2).copy()
    assert len(selected) == 2

    material_id = data["materials"].iloc[0]["material_id"]

    # Give the two operations a combined demand of 140 units.
    data["material_requirements"] = pd.DataFrame([
        {
            "requirement_id": "TEST-REQ-001",
            "operation_id": selected.iloc[0]["operation_id"],
            "material_id": material_id,
            "required_quantity": 70.0,
        },
        {
            "requirement_id": "TEST-REQ-002",
            "operation_id": selected.iloc[1]["operation_id"],
            "material_id": material_id,
            "required_quantity": 70.0,
        },
    ])

    # Only 100 units are available in total.
    earliest = pd.to_datetime(selected["operation_start"]).min()
    latest = pd.to_datetime(selected["operation_start"]).max()

    data["inventory_lots"] = pd.DataFrame([
        {
            "lot_id": "TEST-LOT-001",
            "material_id": material_id,
            "quantity_on_hand": 100.0,
            "available_at": earliest - pd.Timedelta(days=1),
            "expiry_date": latest + pd.Timedelta(days=1),
        }
    ])

    errors = validate_schedule(data, selected)

    # The validator must detect the cumulative shortage of 40 units.
    assert any(
        "cumulative material shortage" in error
        for error in errors
    )
