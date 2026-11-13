
import pandas as pd
from smartplant.generator import generate_data
from smartplant.validation import validate_schedule


def load_test_data():
    data = generate_data()
    schedule = pd.read_csv("data/operation_schedule.csv")

    for column in ["setup_start", "operation_start", "operation_finish"]:
        schedule[column] = pd.to_datetime(schedule[column])

    return data, schedule


def test_detects_machine_overlap():
    data, schedule = load_test_data()

    for machine_id, rows in schedule.groupby("machine_id"):
        rows = rows.sort_values("operation_start")

        if len(rows) >= 2:
            first = rows.index[0]
            second = rows.index[1]

            schedule.loc[second, "setup_start"] = schedule.loc[first, "operation_start"]
            schedule.loc[second, "operation_start"] = schedule.loc[first, "operation_start"]
            schedule.loc[second, "operation_finish"] = (
                schedule.loc[second, "operation_start"]
                + pd.Timedelta(minutes=float(schedule.loc[second, "duration_minutes"]))
            )

            errors = validate_schedule(data, schedule)
            assert any("overlap" in str(e).lower() for e in errors)
            return

    assert False, "Could not find two operations on the same machine"


def test_detects_precedence_violation():
    data, schedule = load_test_data()

    for order_id, rows in schedule.groupby("order_id"):
        rows = rows.sort_values("sequence")

        if len(rows) >= 2:
            previous = rows.index[0]
            following = rows.index[1]

            schedule.loc[following, "setup_start"] = schedule.loc[previous, "setup_start"]
            schedule.loc[following, "operation_start"] = schedule.loc[previous, "setup_start"]
            schedule.loc[following, "operation_finish"] = (
                schedule.loc[following, "operation_start"]
                + pd.Timedelta(minutes=float(schedule.loc[following, "duration_minutes"]))
            )

            errors = validate_schedule(data, schedule)
            assert any("precedence" in str(e).lower() for e in errors)
            return

    assert False, "Could not find an order with multiple operations"


def test_detects_outside_shift():
    data, schedule = load_test_data()

    index = schedule.index[0]
    schedule.loc[index, "setup_start"] = pd.Timestamp("2026-11-17 02:00:00")
    schedule.loc[index, "operation_start"] = pd.Timestamp("2026-11-17 02:00:00")
    schedule.loc[index, "operation_finish"] = (
        schedule.loc[index, "operation_start"]
        + pd.Timedelta(minutes=float(schedule.loc[index, "duration_minutes"]))
    )

    errors = validate_schedule(data, schedule)
    assert any("shift" in str(e).lower() for e in errors)


def test_detects_material_before_availability():
    data, schedule = load_test_data()

    index = schedule.index[0]
    operation_id = schedule.loc[index, "operation_id"]

    requirements = data["material_requirements"]
    required = requirements[requirements["operation_id"] == operation_id]

    if required.empty:
        assert False, "Selected operation has no material requirement"

    material_id = required.iloc[0]["material_id"]

    lots = data["inventory_lots"]
    matching = lots[lots["material_id"] == material_id]

    if matching.empty:
        assert False, "No inventory lot found for required material"

    data["inventory_lots"].loc[matching.index, "available_at"] = (
        schedule.loc[index, "operation_start"] + pd.Timedelta(days=10)
    )

    errors = validate_schedule(data, schedule)
    assert any("material" in str(e).lower() for e in errors)


def test_detects_missing_changeover():
    data, schedule = load_test_data()

    products = data["products"]
    orders = data["production_orders"]

    order_families = orders.merge(
        products[["product_id", "family"]],
        on="product_id"
    ).set_index("order_id")["family"].to_dict()

    changeovers = data["changeover_matrix"]

    for machine_id, group in schedule.groupby("machine_id"):
        ordered = group.sort_values("setup_start")
        previous_family = None

        for index, row in ordered.iterrows():
            current_family = order_families.get(row["order_id"])

            if previous_family is not None:
                match = changeovers[
                    (changeovers["from_family"] == previous_family)
                    & (changeovers["to_family"] == current_family)
                ]

                if not match.empty and int(match.iloc[0]["changeover_minutes"]) > 0:
                    schedule.loc[index, "setup_start"] = row["operation_start"]

                    errors = validate_schedule(data, schedule)

                    assert any(
                        "changeover" in str(e).lower()
                        for e in errors
                    )
                    return

            previous_family = current_family

    assert False, "No positive-duration family transition was found"
