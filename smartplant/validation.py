"""Independent data and schedule validation for SmartPlant."""
import pandas as pd


def validate_data(data):
    errors = []
    pk_fields = {
        "products": "product_id", "machines": "machine_id", "routings": "routing_id",
        "routing_operations": "routing_operation_id", "materials": "material_id",
        "inventory_lots": "lot_id", "production_orders": "order_id",
        "operations": "operation_id", "tools": "tool_id"
    }
    for table, key in pk_fields.items():
        df = data[table]
        if df[key].isna().any() or df[key].duplicated().any():
            errors.append(f"{table}: null or duplicate primary key in {key}")
    checks = [
        ("routings", "product_id", "products", "product_id"),
        ("routing_operations", "routing_id", "routings", "routing_id"),
        ("eligible_machines", "routing_operation_id", "routing_operations", "routing_operation_id"),
        ("eligible_machines", "machine_id", "machines", "machine_id"),
        ("inventory_lots", "material_id", "materials", "material_id"),
        ("production_orders", "product_id", "products", "product_id"),
        ("production_orders", "routing_id", "routings", "routing_id"),
        ("operations", "order_id", "production_orders", "order_id"),
        ("operations", "routing_operation_id", "routing_operations", "routing_operation_id"),
        ("material_requirements", "operation_id", "operations", "operation_id"),
        ("material_requirements", "material_id", "materials", "material_id"),
        ("operation_tool_requirements", "operation_id", "operations", "operation_id"),
        ("operation_tool_requirements", "tool_id", "tools", "tool_id"),
    ]
    for child, fk, parent, pk in checks:
        bad = ~data[child][fk].isin(data[parent][pk])
        if bad.any(): errors.append(f"{child}.{fk}: {int(bad.sum())} invalid foreign keys")
    return errors


def validate_schedule(data, schedule):
    errors = []
    ops = data["operations"].set_index("operation_id")
    orders = data["production_orders"].set_index("order_id")
    machines = data["machines"].set_index("machine_id")
    eligible = data["eligible_machines"]
    calendars = data["machine_calendars"].copy()
    downtime = data["machine_downtime"].copy()
    for col in ["shift_start", "shift_end"]: calendars[col] = pd.to_datetime(calendars[col])
    for col in ["downtime_start", "downtime_end"]: downtime[col] = pd.to_datetime(downtime[col])
    s = schedule.copy()
    if s.empty:
        return ["schedule is empty"]
    for col in ["setup_start", "operation_start", "operation_finish"]: s[col] = pd.to_datetime(s[col])
    if s.operation_id.duplicated().any(): errors.append("an operation appears more than once in schedule")
    missing = set(ops.index) - set(s.operation_id)
    extra = set(s.operation_id) - set(ops.index)
    if missing: errors.append(f"{len(missing)} operations missing from schedule")
    if extra: errors.append(f"{len(extra)} unknown operations in schedule")
    # machine capacity, shift and downtime
    for machine_id, group in s.groupby("machine_id"):
        ordered = group.sort_values("setup_start")
        prev_finish = None
        for _, row in ordered.iterrows():
            if prev_finish is not None and row.setup_start < prev_finish:
                errors.append(f"machine overlap on {machine_id} at {row.operation_id}")
                break
            prev_finish = row.operation_finish
    for _, row in s.iterrows():
        op = ops.loc[row.operation_id]
        if row.machine_id not in set(eligible.loc[eligible.routing_operation_id == op.routing_operation_id, "machine_id"]):
            errors.append(f"ineligible machine for {row.operation_id}")
        if row.machine_id not in machines.index or machines.loc[row.machine_id, "lifecycle_state"] != "ACTIVE":
            errors.append(f"inactive or unknown machine for {row.operation_id}")
        actual = (row.operation_finish - row.operation_start).total_seconds()/60
        if abs(actual - float(op.duration_minutes)) > 0.01:
            errors.append(f"duration mismatch for {row.operation_id}")
        matching = calendars[(calendars.machine_id == row.machine_id) &
                             (calendars.shift_start <= row.setup_start) &
                             (calendars.shift_end >= row.operation_finish)]
        if matching.empty: errors.append(f"outside shift for {row.operation_id}")
        outages = downtime[(downtime.machine_id == row.machine_id) &
                           (downtime.downtime_start < row.operation_finish) &
                           (downtime.downtime_end > row.setup_start)]
        if not outages.empty: errors.append(f"downtime overlap for {row.operation_id}")
    
    # Changeover duration validation
    order_families = orders.reset_index().merge(
        data["products"][["product_id", "family"]],
        on="product_id",
        how="left"
    ).set_index("order_id")["family"].to_dict()

    changeovers = data["changeover_matrix"]

    # Validate changeover matrix completeness and uniqueness.
    families = set(data["products"]["family"].dropna().unique())

    expected_pairs = {
        (from_family, to_family)
        for from_family in families
        for to_family in families
    }

    actual_pairs = list(zip(
        changeovers["from_family"],
        changeovers["to_family"]
    ))

    actual_pair_set = set(actual_pairs)

    missing_pairs = expected_pairs - actual_pair_set

    if missing_pairs:
        errors.append(
            f"changeover matrix missing {len(missing_pairs)} transitions"
        )

    if changeovers.duplicated(
        subset=["from_family", "to_family"]
    ).any():
        errors.append("duplicate changeover matrix transitions")

    if (changeovers["changeover_minutes"] < 0).any():
        errors.append("negative changeover duration found")


    for machine_id, group in s.groupby("machine_id"):
        ordered = group.sort_values("setup_start")
        previous_family = None

        for _, row in ordered.iterrows():
            current_family = order_families.get(row.order_id)

            if previous_family is not None:
                match = changeovers[
                    (changeovers["from_family"] == previous_family) &
                    (changeovers["to_family"] == current_family)
                ]

                required_setup = (
                    int(match.iloc[0]["changeover_minutes"])
                    if not match.empty else 0
                )

                actual_setup = (
                    row.operation_start - row.setup_start
                ).total_seconds() / 60

                if actual_setup < required_setup:
                    errors.append(
                        f"changeover duration mismatch for {row.operation_id}"
                    )

            previous_family = current_family

    # precedence
    for order_id, group in s.groupby("order_id"):
        ordered = group.sort_values("sequence")
        previous_finish = None
        for _, row in ordered.iterrows():
            if previous_finish is not None and row.operation_start < previous_finish:
                errors.append(f"precedence violation for {row.operation_id}")
            previous_finish = row.operation_finish
    # labor capacity by labor group, using sweep-line events; capacity is 10 from calendar rows
    events = {}
    for _, row in s.iterrows():
        key = row.labor_group
        events.setdefault(key, []).extend([(row.operation_start, int(row.required_labor)),
                                           (row.operation_finish, -int(row.required_labor))])
    capacities = data["machine_calendars"].groupby("labor_group").labor_capacity.max().to_dict()
    for group, ev in events.items():
        current = 0
        for _, change in sorted(ev, key=lambda x: (x[0], x[1])):
            current += change
            if current > capacities.get(group, 0):
                errors.append(f"labor capacity exceeded for {group}")
                break
    
    # Independent shared-tool capacity validation
    tool_caps = (
        data["tools"]
        .set_index("tool_id")["quantity_available"]
        .to_dict()
    )

    tool_states = (
        data["tools"]
        .set_index("tool_id")["lifecycle_state"]
        .to_dict()
    )

    tool_requirements = data["operation_tool_requirements"].merge(
        s[["operation_id", "operation_start", "operation_finish"]],
        on="operation_id",
        how="inner"
    )

    tool_events = {}

    for _, requirement in tool_requirements.iterrows():

        tool_id = requirement["tool_id"]
        quantity = int(requirement["required_quantity"])

        if tool_id not in tool_caps:
            errors.append(f"unknown tool {tool_id}")
            continue

        if tool_states.get(tool_id) != "ACTIVE":
            errors.append(f"inactive tool {tool_id}")
            continue

        if quantity <= 0:
            errors.append(
                f"invalid tool quantity for {requirement['operation_id']}"
            )
            continue

        capacity = int(tool_caps[tool_id])

        if quantity > capacity:
            errors.append(
                f"tool requirement exceeds capacity for {tool_id}"
            )
            continue

        tool_events.setdefault(tool_id, []).extend([
            (requirement["operation_start"], quantity),
            (requirement["operation_finish"], -quantity)
        ])

    # Validate each tool pool independently.
    for tool_id, events in tool_events.items():

        current_quantity = 0

        # Process ending reservations before starting reservations
        # at the same timestamp.
        for _, quantity_change in sorted(
            events,
            key=lambda event: (event[0], event[1])
        ):

            current_quantity += quantity_change

            if current_quantity > int(tool_caps[tool_id]):
                errors.append(
                    f"tool capacity exceeded for {tool_id}"
                )
                break

            if current_quantity < 0:
                errors.append(
                    f"invalid tool reservation balance for {tool_id}"
                )
                break

    
    # Cumulative material inventory validation
    lots = data["inventory_lots"].copy()

    lots["available_at"] = pd.to_datetime(lots["available_at"])
    lots["expiry_date"] = pd.to_datetime(
        lots["expiry_date"], errors="coerce"
    )

    # Maintain an independent remaining balance for every inventory lot.
    balances = {
        row["lot_id"]: float(row["quantity_on_hand"])
        for _, row in lots.iterrows()
    }

    # Match material requirements with their scheduled operation times.
    scheduled_requirements = data["material_requirements"].merge(
        s[["operation_id", "operation_start"]],
        on="operation_id",
        how="inner"
    )

    scheduled_requirements["operation_start"] = pd.to_datetime(
        scheduled_requirements["operation_start"]
    )

    # Aggregate duplicate requirements for the same operation and material.
    scheduled_requirements = (
        scheduled_requirements.groupby(
            ["operation_id", "operation_start", "material_id"],
            as_index=False
        )["required_quantity"].sum()
    )

    # Process operations chronologically and deterministically.
    scheduled_requirements = scheduled_requirements.sort_values(
        ["operation_start", "operation_id", "material_id"]
    )

    for _, requirement in scheduled_requirements.iterrows():

        operation_id = requirement["operation_id"]
        material_id = requirement["material_id"]
        operation_start = requirement["operation_start"]
        required_quantity = float(requirement["required_quantity"])

        remaining = required_quantity

        # Only use lots available and unexpired at consumption time.
        eligible_lots = lots[
            (lots["material_id"] == material_id)
            & (lots["available_at"] <= operation_start)
            & (
                lots["expiry_date"].isna()
                | (lots["expiry_date"] >= operation_start)
            )
        ].sort_values(
            ["expiry_date", "available_at", "lot_id"]
        )

        # Prepare allocations without partially deducting inventory.
        allocations = []

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

        # If the complete requirement cannot be fulfilled,
        # report an error and do not deduct any inventory.
        if remaining > 0.000001:
            errors.append(
                f"cumulative material shortage for "
                f"{operation_id}, material {material_id}: "
                f"required {required_quantity}, "
                f"shortage {remaining:.4f}"
            )
            continue

        # Commit inventory deductions only after full allocation.
        for lot_id, quantity in allocations:
            balances[lot_id] -= quantity

    return errors
