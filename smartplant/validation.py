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
    # tool capacity
    tool_caps = data["tools"].set_index("tool_id").quantity_available.to_dict()
    tool_events = {}
    for _, row in s.iterrows():
        for tool_id in str(row.tool_ids).split(";"):
            if not tool_id: continue
            qty = int(row.tool_quantity_required)
            tool_events.setdefault(tool_id, []).extend([(row.operation_start, qty), (row.operation_finish, -qty)])
    for tool_id, ev in tool_events.items():
        current = 0
        for _, change in sorted(ev, key=lambda x: (x[0], x[1])):
            current += change
            if current > int(tool_caps.get(tool_id, 0)):
                errors.append(f"tool capacity exceeded for {tool_id}")
                break
    # material availability and aggregate inventory sufficiency
    lots = data["inventory_lots"].copy()
    lots["available_at"] = pd.to_datetime(lots.available_at)
    lots["expiry_date"] = pd.to_datetime(lots.expiry_date, errors="coerce")
    req = data["material_requirements"].merge(s[["operation_id", "operation_start"]], on="operation_id")
    for _, row in req.iterrows():
        possible = lots[(lots.material_id == row.material_id) & (lots.available_at <= row.operation_start) &
                        (lots.expiry_date.isna() | (lots.expiry_date >= row.operation_start))]
        if possible.quantity_on_hand.sum() < row.required_quantity:
            errors.append(f"material unavailable at operation start for {row.operation_id}")
    return errors
