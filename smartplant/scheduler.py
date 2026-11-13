
"""
SmartPlant Scheduler
Initial production scheduling engine.

Features:
- Order priority sequencing
- Operation precedence
- Eligible machine assignment
- Machine shift calendars
- Machine downtime
- Sequence-dependent changeovers
- Inventory availability and consumption
- Exception reporting
"""

import pandas as pd


PRIORITY_ORDER = {
    "URGENT": 0,
    "HIGH": 1,
    "NORMAL": 2,
    "LOW": 3
}


def prepare_inventory(data):
    """Create a working copy of inventory balances."""

    lots = data["inventory_lots"].copy()

    lots["available_at"] = pd.to_datetime(lots["available_at"])
    lots["expiry_date"] = pd.to_datetime(
        lots["expiry_date"], errors="coerce"
    )

    balances = {}

    for _, lot in lots.iterrows():
        balances[lot["lot_id"]] = float(lot["quantity_on_hand"])

    return lots, balances




def get_material_ready_time(
    operation_id, requirements, lots, balances, earliest_time
):
    """Find the earliest time all materials can be supplied from valid lots."""

    operation_requirements = requirements[
        requirements["operation_id"] == operation_id
    ]

    if operation_requirements.empty:
        return earliest_time

    # Aggregate duplicate requirement rows for the same material so the
    # same inventory balance cannot be counted more than once.
    grouped_requirements = (
        operation_requirements.groupby("material_id")["required_quantity"]
        .sum()
    )

    candidate_times = {pd.Timestamp(earliest_time)}
    candidate_times.update(
        pd.Timestamp(value)
        for value in lots.loc[
            lots["available_at"] > earliest_time, "available_at"
        ].dropna().tolist()
    )

    for candidate_time in sorted(candidate_times):
        all_available = True

        for material_id, required_quantity in grouped_requirements.items():
            eligible_lots = lots[
                (lots["material_id"] == material_id)
                & (lots["available_at"] <= candidate_time)
                & (
                    lots["expiry_date"].isna()
                    | (lots["expiry_date"] >= candidate_time)
                )
            ]

            available_quantity = sum(
                balances[lot_id]
                for lot_id in eligible_lots["lot_id"]
            )

            if available_quantity + 0.000001 < float(required_quantity):
                all_available = False
                break

        if all_available:
            return candidate_time

    return None


def consume_materials(
    operation_id, operation_start,
    requirements, lots, balances
):
    """Atomically consume all required materials or make no deductions."""

    operation_requirements = requirements[
        requirements["operation_id"] == operation_id
    ]

    if operation_requirements.empty:
        return True

    grouped_requirements = (
        operation_requirements.groupby("material_id")["required_quantity"]
        .sum()
    )

    allocations = []

    # Phase 1: prepare every allocation without changing inventory balances.
    for material_id, required_quantity in grouped_requirements.items():
        remaining = float(required_quantity)

        eligible_lots = lots[
            (lots["material_id"] == material_id)
            & (lots["available_at"] <= operation_start)
            & (
                lots["expiry_date"].isna()
                | (lots["expiry_date"] >= operation_start)
            )
        ].sort_values(["expiry_date", "available_at"])

        for _, lot in eligible_lots.iterrows():
            lot_id = lot["lot_id"]
            available_quantity = balances[lot_id]

            if available_quantity <= 0:
                continue

            used = min(remaining, available_quantity)
            allocations.append((lot_id, used))
            remaining -= used

            if remaining <= 0.000001:
                break

        if remaining > 0.000001:
            return False

    # Phase 2: all materials are available, so commit the deductions.
    for lot_id, quantity in allocations:
        balances[lot_id] -= quantity

    return True


def _capacity_conflict_end(
    reservations,
    key_field,
    key_value,
    start,
    finish,
    required_quantity,
    capacity,
    quantity_field
):
    """
    Return the earliest reservation end if adding this operation
    would exceed capacity; otherwise return None.
    """

    relevant = [
        reservation
        for reservation in reservations
        if (
            reservation[key_field] == key_value
            and reservation["start"] < finish
            and reservation["finish"] > start
        )
    ]

    events = [(start, required_quantity, 1), (finish, -required_quantity, 0)]

    for reservation in relevant:
        overlap_start = max(start, reservation["start"])
        overlap_finish = min(finish, reservation["finish"])
        quantity = reservation[quantity_field]

        # End events sort before start events at the same timestamp.
        events.append((overlap_start, quantity, 1))
        events.append((overlap_finish, -quantity, 0))

    events.sort(key=lambda event: (event[0], event[2]))

    current_quantity = 0
    exceeded = False

    for _, quantity_change, _ in events:
        current_quantity += quantity_change
        if current_quantity > capacity:
            exceeded = True
            break

    if exceeded:
        future_ends = [
            reservation["finish"]
            for reservation in relevant
            if reservation["finish"] > start
        ]
        return min(future_ends) if future_ends else None

    return None


def find_machine_slot(
    machine_id,
    earliest_time,
    duration,
    changeover_minutes,
    calendars,
    downtime,
    labor_group,
    labor_required,
    labor_reservations,
    tool_requirements,
    tool_capacities,
    tool_reservations
):
    """Find a machine slot while respecting downtime, labor and shared tools."""

    machine_calendars = calendars[
        (calendars["machine_id"] == machine_id)
        & (calendars["shift_end"] >= earliest_time)
    ].sort_values("shift_start")

    machine_downtime = downtime[
        downtime["machine_id"] == machine_id
    ].sort_values("downtime_start")

    for _, shift in machine_calendars.iterrows():

        shift_start = pd.Timestamp(shift["shift_start"])
        shift_end = pd.Timestamp(shift["shift_end"])
        labor_capacity = int(shift["labor_capacity"])

        if labor_required > labor_capacity:
            continue

        candidate = max(earliest_time, shift_start)
        setup = pd.Timedelta(minutes=changeover_minutes)
        processing = pd.Timedelta(minutes=duration)

        while candidate + setup + processing <= shift_end:

            operation_start = candidate + setup
            operation_finish = operation_start + processing
            conflict_found = False

            # Machine downtime blocks both setup and processing.
            for _, outage in machine_downtime.iterrows():
                outage_start = pd.Timestamp(outage["downtime_start"])
                outage_end = pd.Timestamp(outage["downtime_end"])

                if candidate < outage_end and operation_finish > outage_start:
                    candidate = max(candidate, outage_end)
                    conflict_found = True
                    break

            if conflict_found:
                continue

            # Check labor capacity over the actual processing interval.
            labor_conflict_end = _capacity_conflict_end(
                labor_reservations,
                "labor_group",
                labor_group,
                operation_start,
                operation_finish,
                labor_required,
                labor_capacity,
                "workers"
            )

            if labor_conflict_end is not None:
                candidate = max(candidate, labor_conflict_end)
                continue

            # Every required shared tool pool must have enough free units.
            tool_conflict_end = None

            for requirement in tool_requirements:
                tool_id = requirement["tool_id"]
                required_quantity = requirement["required_quantity"]
                capacity = tool_capacities[tool_id]

                conflict_end = _capacity_conflict_end(
                    tool_reservations,
                    "tool_id",
                    tool_id,
                    operation_start,
                    operation_finish,
                    required_quantity,
                    capacity,
                    "quantity"
                )

                if conflict_end is not None:
                    if tool_conflict_end is None:
                        tool_conflict_end = conflict_end
                    else:
                        tool_conflict_end = min(tool_conflict_end, conflict_end)

            if tool_conflict_end is not None:
                candidate = max(candidate, tool_conflict_end)
                continue

            return {
                "setup_start": candidate,
                "operation_start": operation_start,
                "operation_finish": operation_finish
            }

    return None


def run_scheduler(data):

    orders = data["production_orders"].copy()
    operations = data["operations"].copy()

    eligible = data["eligible_machines"]
    calendars = data["machine_calendars"].copy()
    downtime = data["machine_downtime"].copy()

    requirements = data["material_requirements"]
    products = data["products"]
    machines = data["machines"]
    changeovers = data["changeover_matrix"]
    tools = data["tools"]
    operation_tool_requirements = data["operation_tool_requirements"]

    tool_capacities = {
        row["tool_id"]: int(row["quantity_available"])
        for _, row in tools.iterrows()
    }

    # Convert date fields into datetime values.
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    orders["due_date"] = pd.to_datetime(orders["due_date"])

    calendars["shift_start"] = pd.to_datetime(
        calendars["shift_start"]
    )
    calendars["shift_end"] = pd.to_datetime(
        calendars["shift_end"]
    )

    downtime["downtime_start"] = pd.to_datetime(
        downtime["downtime_start"]
    )
    downtime["downtime_end"] = pd.to_datetime(
        downtime["downtime_end"]
    )

    lots, balances = prepare_inventory(data)

    # Add product family information to orders.
    orders = orders.merge(
        products[["product_id", "family"]],
        on="product_id",
        how="left"
    )

    # Process urgent orders first, then due date.
    orders["priority_rank"] = orders["priority"].map(
        PRIORITY_ORDER
    ).fillna(99)

    orders = orders.sort_values(
        ["priority_rank", "due_date", "order_date"]
    )

    # Track the next available time and previous family
    # for each machine.
    machine_available = {}
    machine_last_family = {}
    labor_reservations = []
    tool_reservations = []

    schedule_records = []
    exception_records = []

    # Keep track of completed operations.
    completed_operations = {}

    for _, order in orders.iterrows():

        order_id = order["order_id"]
        order_start = order["order_date"]
        order_family = order["family"]

        order_operations = operations[
            operations["order_id"] == order_id
        ].sort_values("sequence")

        for _, operation in order_operations.iterrows():

            operation_id = operation["operation_id"]
            routing_operation_id = operation[
                "routing_operation_id"
            ]

            sequence = int(operation["sequence"])
            duration = float(operation["duration_minutes"])

            # Check operation precedence.
            if sequence > 1:

                previous_operations = order_operations[
                    order_operations["sequence"] == sequence - 1
                ]

                if previous_operations.empty:
                    exception_records.append({
                        "operation_id": operation_id,
                        "order_id": order_id,
                        "exception": "PREDECESSOR_NOT_FOUND"
                    })
                    continue

                previous_id = previous_operations.iloc[0][
                    "operation_id"
                ]

                if previous_id not in completed_operations:

                    exception_records.append({
                        "operation_id": operation_id,
                        "order_id": order_id,
                        "exception": "PREDECESSOR_NOT_SCHEDULED"
                    })
                    continue

                earliest_time = completed_operations[previous_id]

            else:
                earliest_time = order_start

            # Check material availability.
            material_ready = get_material_ready_time(
                operation_id,
                requirements,
                lots,
                balances,
                earliest_time
            )

            if material_ready is None:

                exception_records.append({
                    "operation_id": operation_id,
                    "order_id": order_id,
                    "exception": "INSUFFICIENT_MATERIAL_STOCK"
                })
                continue

            earliest_time = max(
                earliest_time,
                material_ready
            )

            # Load the shared tools required by this operation.
            operation_tools = operation_tool_requirements[
                operation_tool_requirements["operation_id"] == operation_id
            ]

            tool_requirements_for_operation = []
            invalid_tool_requirement = False

            for _, tool_requirement in operation_tools.iterrows():
                tool_id = tool_requirement["tool_id"]
                required_quantity = int(tool_requirement["required_quantity"])

                if (
                    tool_id not in tool_capacities
                    or required_quantity <= 0
                    or required_quantity > tool_capacities.get(tool_id, 0)
                ):
                    invalid_tool_requirement = True
                    break

                tool_requirements_for_operation.append({
                    "tool_id": tool_id,
                    "required_quantity": required_quantity
                })

            if invalid_tool_requirement or not tool_requirements_for_operation:
                exception_records.append({
                    "operation_id": operation_id,
                    "order_id": order_id,
                    "exception": "INVALID_OR_MISSING_TOOL_REQUIREMENT"
                })
                continue

            # Find eligible machines.
            eligible_ids = eligible[
                eligible["routing_operation_id"]
                == routing_operation_id
            ]["machine_id"].tolist()

            if not eligible_ids:

                exception_records.append({
                    "operation_id": operation_id,
                    "order_id": order_id,
                    "exception": "NO_ELIGIBLE_MACHINE"
                })
                continue

            candidates = []

            for machine_id in eligible_ids:

                machine = machines[
                    machines["machine_id"] == machine_id
                ]

                if machine.empty:
                    continue

                if machine.iloc[0]["lifecycle_state"] != "ACTIVE":
                    continue

                machine_ready = machine_available.get(
                    machine_id,
                    pd.Timestamp.min
                )

                candidate_earliest = max(
                    earliest_time,
                    machine_ready
                )

                previous_family = machine_last_family.get(
                    machine_id
                )

                changeover_minutes = 0

                if previous_family is not None:

                    match = changeovers[
                        (
                            changeovers["from_family"]
                            == previous_family
                        )
                        &
                        (
                            changeovers["to_family"]
                            == order_family
                        )
                    ]

                    if not match.empty:
                        changeover_minutes = int(
                            match.iloc[0]["changeover_minutes"]
                        )

                
                labor_group = machine.iloc[0]["labor_group"]

                slot = find_machine_slot(
                    machine_id,
                    candidate_earliest,
                    duration,
                    changeover_minutes,
                    calendars,
                    downtime,
                    labor_group,
                    int(operation["required_labor"]),
                    labor_reservations,
                    tool_requirements_for_operation,
                    tool_capacities,
                    tool_reservations
                )

                if slot is not None:

                    candidates.append({
                        "machine_id": machine_id,
                        "slot": slot,
                        "changeover_minutes": changeover_minutes
                    })

            if not candidates:

                exception_records.append({
                    "operation_id": operation_id,
                    "order_id": order_id,
                    "exception": "NO_AVAILABLE_MACHINE_SLOT"
                })
                continue

            # Select the machine with the earliest completion.
            best = min(
                candidates,
                key=lambda item: item["slot"]["operation_finish"]
            )

            machine_id = best["machine_id"]
            slot = best["slot"]

            operation_start = slot["operation_start"]
            operation_finish = slot["operation_finish"]

            # Deduct materials only if every requirement is fulfilled.
            materials_consumed = consume_materials(
                operation_id,
                operation_start,
                requirements,
                lots,
                balances
            )

            if not materials_consumed:
                exception_records.append({
                    "operation_id": operation_id,
                    "order_id": order_id,
                    "exception": "INSUFFICIENT_MATERIAL_STOCK"
                })
                continue

            # Update machine state.
            machine_available[machine_id] = operation_finish
            machine_last_family[machine_id] = order_family

            # Reserve workers for this operation.
            machine_labor_group = machines.loc[
                machines["machine_id"] == machine_id,
                "labor_group"
            ].iloc[0]

            labor_reservations.append({
                "labor_group": machine_labor_group,
                "start": operation_start,
                "finish": operation_finish,
                "workers": int(operation["required_labor"]),
                "operation_id": operation_id
            })

            # Reserve shared tool units for the full processing interval.
            for tool_requirement in tool_requirements_for_operation:
                tool_reservations.append({
                    "tool_id": tool_requirement["tool_id"],
                    "start": operation_start,
                    "finish": operation_finish,
                    "quantity": tool_requirement["required_quantity"],
                    "operation_id": operation_id
                })

            tool_ids_for_schedule = ";".join(
                requirement["tool_id"]
                for requirement in tool_requirements_for_operation
            )

            # Record completed scheduling dependency.
            completed_operations[operation_id] = operation_finish

            schedule_records.append({

                "schedule_id": f"SCH-{len(schedule_records) + 1:06d}",
                "operation_id": operation_id,
                "order_id": order_id,
                "machine_id": machine_id,
                "labor_group": machine_labor_group,
                "required_labor": int(operation["required_labor"]),
                "tool_ids": tool_ids_for_schedule,
                "tool_quantity_required": sum(
                    requirement["required_quantity"]
                    for requirement in tool_requirements_for_operation
                ),
                "sequence": sequence,
                "operation_type": operation["operation_type"],
                "priority": order["priority"],
                "due_date": order["due_date"],
                "setup_start": slot["setup_start"],
                "operation_start": operation_start,
                "operation_finish": operation_finish,
                "duration_minutes": duration,
                "changeover_minutes": best[
                    "changeover_minutes"
                ],
                "schedule_status": "SCHEDULED"
            })

    schedule_df = pd.DataFrame(schedule_records)
    exceptions_df = pd.DataFrame(
        exception_records,
        columns=["operation_id", "order_id", "exception"]
    )

    return schedule_df, exceptions_df


if __name__ == "__main__":

    from smartplant.generator import generate_data

    data = generate_data()

    schedule, exceptions = run_scheduler(data)

    print("\nSMARTPLANT SCHEDULING REPORT")
    print("---------------------------")

    print("Total operations:", len(data["operations"]))
    print("Scheduled operations:", len(schedule))
    print("Exceptions:", len(exceptions))

    import os
    os.makedirs("data", exist_ok=True)
    schedule.to_csv("data/operation_schedule.csv", index=False)
    exceptions.to_csv("data/scheduling_exceptions.csv", index=False)

    print("\nScheduling execution completed!")