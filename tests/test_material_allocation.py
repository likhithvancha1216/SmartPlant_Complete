import pandas as pd

from smartplant.scheduler import consume_materials

OPERATION_START = pd.Timestamp("2026-11-20")


def create_lots(records):
    lots = pd.DataFrame(records)
    lots["available_at"] = pd.to_datetime(lots["available_at"])
    lots["expiry_date"] = pd.to_datetime(
        lots["expiry_date"], errors="coerce"
    )
    return lots


def test_successful_material_allocation():
    lots = create_lots([
        {"lot_id": "L1", "material_id": "M1", "quantity_on_hand": 4,
         "available_at": "2026-11-15", "expiry_date": "2027-02-14"},
        {"lot_id": "L2", "material_id": "M1", "quantity_on_hand": 6,
         "available_at": "2026-11-16", "expiry_date": "2027-02-14"}
    ])
    requirements = pd.DataFrame([
        {"operation_id": "OP1", "material_id": "M1",
         "required_quantity": 8}
    ])
    balances = {"L1": 4.0, "L2": 6.0}

    result = consume_materials(
        "OP1", OPERATION_START, requirements, lots, balances
    )

    assert result is True
    assert balances == {"L1": 0, "L2": 2}


def test_insufficient_stock_does_not_partially_deduct():
    lots = create_lots([
        {"lot_id": "L1", "material_id": "M1", "quantity_on_hand": 10,
         "available_at": "2026-11-15", "expiry_date": "2027-02-14"},
        {"lot_id": "L2", "material_id": "M2", "quantity_on_hand": 2,
         "available_at": "2026-11-15", "expiry_date": "2027-02-14"}
    ])
    requirements = pd.DataFrame([
        {"operation_id": "OP1", "material_id": "M1",
         "required_quantity": 5},
        {"operation_id": "OP1", "material_id": "M2",
         "required_quantity": 3}
    ])
    balances = {"L1": 10.0, "L2": 2.0}
    original = balances.copy()

    result = consume_materials(
        "OP1", OPERATION_START, requirements, lots, balances
    )

    assert result is False
    assert balances == original


def test_expired_inventory_is_not_consumed():
    lots = create_lots([
        {"lot_id": "L1", "material_id": "M1", "quantity_on_hand": 10,
         "available_at": "2026-11-15", "expiry_date": "2026-11-19"}
    ])
    requirements = pd.DataFrame([
        {"operation_id": "OP1", "material_id": "M1",
         "required_quantity": 5}
    ])
    balances = {"L1": 10.0}

    result = consume_materials(
        "OP1", OPERATION_START, requirements, lots, balances
    )

    assert result is False
    assert balances["L1"] == 10


def test_future_inventory_is_not_consumed():
    lots = create_lots([
        {"lot_id": "L1", "material_id": "M1", "quantity_on_hand": 10,
         "available_at": "2026-11-25", "expiry_date": "2027-02-14"}
    ])
    requirements = pd.DataFrame([
        {"operation_id": "OP1", "material_id": "M1",
         "required_quantity": 5}
    ])
    balances = {"L1": 10.0}

    result = consume_materials(
        "OP1", OPERATION_START, requirements, lots, balances
    )

    assert result is False
    assert balances["L1"] == 10


def test_duplicate_material_requirements_are_grouped():
    lots = create_lots([
        {"lot_id": "L1", "material_id": "M1", "quantity_on_hand": 4,
         "available_at": "2026-11-15", "expiry_date": "2027-02-14"}
    ])
    requirements = pd.DataFrame([
        {"operation_id": "OP1", "material_id": "M1",
         "required_quantity": 2},
        {"operation_id": "OP1", "material_id": "M1",
         "required_quantity": 3}
    ])
    balances = {"L1": 4.0}

    result = consume_materials(
        "OP1", OPERATION_START, requirements, lots, balances
    )

    assert result is False
    assert balances["L1"] == 4