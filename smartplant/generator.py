
"""
SmartPlant Scheduler
Synthetic manufacturing data generator.

Creates master data first, then dependent production records.
Uses a fixed random seed for reproducibility.
"""

import random
import pandas as pd

from datetime import datetime, timedelta, time

from smartplant.config import (
    SEED,
    PRODUCT_COUNT,
    MACHINE_COUNT,
    ORDER_COUNT,
    MATERIAL_COUNT,
    PLANNING_DAYS,
    MACHINE_TYPES,
    ORDER_PRIORITIES
)


def generate_data():

    # Fixed seed: same input produces the same data
    random.seed(SEED)

    planning_start = datetime(2026, 11, 16)

    # ==========================================
    # STEP 1: GENERATE PRODUCTS
    # ==========================================

    products = []

    families = [
        "FAMILY-A",
        "FAMILY-B",
        "FAMILY-C",
        "FAMILY-D",
        "FAMILY-E"
    ]

    for i in range(1, PRODUCT_COUNT + 1):

        product_id = f"PROD-2026-{i:06d}"
        sku = f"SKU-{i:04d}"

        products.append({
            "product_id": product_id,
            "sku": sku,
            "product_name": f"Industrial Product {i}",
            "family": random.choice(families),
            "lifecycle_state": "ACTIVE"
        })

    products_df = pd.DataFrame(products)

    # ==========================================
    # STEP 2: GENERATE MACHINES
    # ==========================================

    machines = []

    for i in range(1, MACHINE_COUNT + 1):

        machine_id = f"MACH-{i:03d}"

        machine_type = MACHINE_TYPES[
            (i - 1) % len(MACHINE_TYPES)
        ]

        machines.append({
            "machine_id": machine_id,
            "machine_name": f"{machine_type}-CELL-{i}",
            "machine_type": machine_type,
            "capacity_units_per_hour": random.randint(8, 20),
            "labor_group": f"LABOR-{((i - 1) // 10) + 1}",
            "lifecycle_state": "ACTIVE"
        })

    machines_df = pd.DataFrame(machines)

    # ==========================================
    # STEP 3: GENERATE ROUTINGS
    # ==========================================

    routings = []
    routing_operations = []

    operation_types = [
        "CUT",
        "MILL",
        "DRILL",
        "ASSEMBLE"
    ]

    for product in products:

        routing_id = f"ROUTE-{product['sku']}-01"

        routings.append({
            "routing_id": routing_id,
            "product_id": product["product_id"],
            "revision": 1,
            "effective_from": planning_start.date(),
            "effective_to": None,
            "lifecycle_state": "RELEASED"
        })

        for sequence, operation_type in enumerate(
            operation_types, start=1
        ):

            routing_operation_id = (
                f"{routing_id}-STEP-{sequence:02d}"
            )

            routing_operations.append({
                "routing_operation_id": routing_operation_id,
                "routing_id": routing_id,
                "sequence": sequence,
                "operation_type": operation_type,
                "standard_duration_minutes": random.randint(45, 180),
                "required_labor": (
                    2 if operation_type == "ASSEMBLE" else 1
                )
            })

    routings_df = pd.DataFrame(routings)
    routing_operations_df = pd.DataFrame(routing_operations)

    # ==========================================
    # STEP 4: ELIGIBLE MACHINES
    # ==========================================

    eligible_machines = []

    for operation in routing_operations:

        candidates = machines_df[
            machines_df["machine_type"]
            == operation["operation_type"]
        ]

        for _, machine in candidates.iterrows():

            eligible_machines.append({
                "routing_operation_id":
                    operation["routing_operation_id"],

                "machine_id": machine["machine_id"]
            })

    eligible_machines_df = pd.DataFrame(
        eligible_machines
    )

    # ==========================================
    # STEP 5: MACHINE CALENDARS
    # ==========================================

    calendars = []

    for machine in machines:

        for day in range(PLANNING_DAYS):

            work_date = (
                planning_start + timedelta(days=day)
            )

            # Sunday is a non-working day
            if work_date.weekday() == 6:
                continue

            shifts = [
                ("DAY", 6),
                ("EVENING", 14)
            ]

            for shift_name, start_hour in shifts:

                shift_start = datetime.combine(
                    work_date.date(),
                    time(start_hour, 0)
                )

                shift_end = shift_start + timedelta(hours=8)

                calendars.append({
                    "calendar_id": (
                        f"CAL-{machine['machine_id']}-"
                        f"{day:02d}-{shift_name}"
                    ),
                    "machine_id": machine["machine_id"],
                    "work_date": work_date.date(),
                    "shift": shift_name,
                    "shift_start": shift_start,
                    "shift_end": shift_end,
                    "capacity_minutes": 480,
                    "labor_group": machine["labor_group"],
                    "labor_capacity": 10
                })

    calendars_df = pd.DataFrame(calendars)

    # ==========================================
    # STEP 6: MACHINE DOWNTIME
    # ==========================================

    downtime_records = []

    for machine in machines:

        for event_number in range(1, 3):

            day_offset = random.randint(
                0, PLANNING_DAYS - 1
            )

            downtime_date = (
                planning_start + timedelta(days=day_offset)
            )

            # Skip Sunday
            if downtime_date.weekday() == 6:
                continue

            start_hour = random.choice([8, 10, 15, 17])

            downtime_start = datetime.combine(
                downtime_date.date(),
                time(start_hour, 0)
            )

            downtime_end = (
                downtime_start
                + timedelta(minutes=random.choice([30, 60, 90]))
            )

            downtime_records.append({
                "downtime_id": (
                    f"DOWN-{machine['machine_id']}-{event_number}"
                ),
                "machine_id": machine["machine_id"],
                "downtime_start": downtime_start,
                "downtime_end": downtime_end,
                "reason": random.choice([
                    "MAINTENANCE",
                    "BREAKDOWN",
                    "QUALITY_INSPECTION"
                ])
            })

    downtime_df = pd.DataFrame(downtime_records)

    # ==========================================
    # STEP 7: GENERATE MATERIALS
    # ==========================================

    materials = []

    for i in range(1, MATERIAL_COUNT + 1):

        materials.append({
            "material_id": f"MAT-{i:04d}",
            "material_name": f"Raw Material {i}",
            "unit": "KG",
            "lifecycle_state": "ACTIVE"
        })

    materials_df = pd.DataFrame(materials)

    # STEP 7A: shared tool pools (two units per operation type)
    tools = []
    for operation_type in operation_types:
        tools.append({
            "tool_id": f"TOOL-{operation_type}-001",
            "tool_name": f"Shared {operation_type} Tool Pool",
            "tool_type": operation_type,
            "quantity_available": 2,
            "lifecycle_state": "ACTIVE"
        })
    tools_df = pd.DataFrame(tools)
    tool_lookup = {tool["tool_type"]: tool["tool_id"] for tool in tools}

    # ==========================================
    # STEP 8: GENERATE INVENTORY LOTS
    # ==========================================

    inventory_lots = []

    for i, material in enumerate(materials, start=1):

        available_at = (
            planning_start
            + timedelta(days=random.randint(0, 5))
        )

        inventory_lots.append({
            "lot_id": f"LOT-{i:04d}-01",
            "material_id": material["material_id"],
            "quantity_on_hand": random.randint(500, 3000),
            "available_at": available_at,
            "expiry_date": (
                planning_start + timedelta(days=90)
            ).date()
        })

    inventory_lots_df = pd.DataFrame(inventory_lots)

    # ==========================================
    # STEP 9: GENERATE PRODUCTION ORDERS
    # ==========================================

    orders = []

    for i in range(1, ORDER_COUNT + 1):

        product = random.choice(products)

        order_id = f"ORD-2026-{i:06d}"

        due_date = (
            planning_start
            + timedelta(days=random.randint(3, 35))
        )

        priority = (
            "URGENT" if i % 17 == 0
            else random.choice(ORDER_PRIORITIES)
        )

        orders.append({
            "order_id": order_id,
            "product_id": product["product_id"],
            "routing_id": (
                f"ROUTE-{product['sku']}-01"
            ),
            "quantity": random.randint(20, 150),
            "order_date": planning_start.date(),
            "due_date": due_date.date(),
            "priority": priority,
            "lifecycle_state": "RELEASED"
        })

    orders_df = pd.DataFrame(orders)

    # ==========================================
    # STEP 10: GENERATE ORDER OPERATIONS
    # ==========================================

    operations = []
    material_requirements = []
    operation_tool_requirements = []

    for order in orders:

        route_steps = routing_operations_df[
            routing_operations_df["routing_id"]
            == order["routing_id"]
        ].sort_values("sequence")

        for _, step in route_steps.iterrows():

            operation_id = (
                f"OP-{order['order_id']}-"
                f"{step['sequence']:02d}"
            )

            operations.append({
                "operation_id": operation_id,
                "order_id": order["order_id"],
                "routing_operation_id":
                    step["routing_operation_id"],
                "sequence": int(step["sequence"]),
                "operation_type": step["operation_type"],
                "duration_minutes":
                    int(step["standard_duration_minutes"]),
                "required_labor": int(step["required_labor"]),
                "status": "READY"
            })

            # One material requirement for each operation
            material = random.choice(materials)

            material_requirements.append({
                "requirement_id": f"REQ-{operation_id}-01",
                "operation_id": operation_id,
                "material_id": material["material_id"],
                "required_quantity": round(
                    order["quantity"] * random.uniform(0.05, 0.20),
                    2
                )
            })

            operation_tool_requirements.append({
                "tool_requirement_id": f"TREQ-{operation_id}-01",
                "operation_id": operation_id,
                "tool_id": tool_lookup[step["operation_type"]],
                "required_quantity": 1
            })

    operations_df = pd.DataFrame(operations)

    material_requirements_df = pd.DataFrame(
        material_requirements
    )

    operation_tool_requirements_df = pd.DataFrame(
        operation_tool_requirements
    )

    # ==========================================
    # STEP 11: GENERATE CHANGEOVER MATRIX
    # ==========================================

    changeovers = []

    for from_family in families:

        for to_family in families:

            changeovers.append({
                "from_family": from_family,
                "to_family": to_family,
                "changeover_minutes": (
                    0 if from_family == to_family
                    else random.choice([15, 30, 45, 60])
                )
            })

    changeover_df = pd.DataFrame(changeovers)

    # ==========================================
    # RETURN ALL GENERATED DATA
    # ==========================================

    return {

        "products": products_df,

        "routings": routings_df,

        "routing_operations": routing_operations_df,

        "machines": machines_df,

        "eligible_machines": eligible_machines_df,

        "machine_calendars": calendars_df,

        "machine_downtime": downtime_df,

        "materials": materials_df,

        "inventory_lots": inventory_lots_df,

        "production_orders": orders_df,

        "operations": operations_df,

        "material_requirements": material_requirements_df,

        "tools": tools_df,

        "operation_tool_requirements": operation_tool_requirements_df,

        "changeover_matrix": changeover_df
    }



if __name__ == "__main__":

    import os

    data = generate_data()

    # Create output directory
    os.makedirs("data", exist_ok=True)

    print("\nSMARTPLANT DATA GENERATION REPORT")
    print("--------------------------------")

    for name, dataframe in data.items():

        # Save each dataset as a CSV file
        file_path = f"data/{name}.csv"

        dataframe.to_csv(file_path, index=False)

        print(
            f"{name}: {len(dataframe)} records "
            f"-> {file_path}"
        )

    print("\nAll datasets exported successfully!")
