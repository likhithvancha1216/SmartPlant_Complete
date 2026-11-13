
"""Create a relational SQLite database and SQL seed export."""

import sqlite3
from pathlib import Path

import pandas as pd


DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "smartplant.db"
SQL_PATH = DATA_DIR / "smartplant_seed.sql"


SCHEMA = """
CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    family TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL
);

CREATE TABLE machines (
    machine_id TEXT PRIMARY KEY,
    machine_name TEXT NOT NULL,
    machine_type TEXT NOT NULL,
    capacity_units_per_hour INTEGER NOT NULL CHECK(capacity_units_per_hour > 0),
    labor_group TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL
);

CREATE TABLE materials (
    material_id TEXT PRIMARY KEY,
    material_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL
);

CREATE TABLE tools (
    tool_id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    tool_type TEXT NOT NULL,
    quantity_available INTEGER NOT NULL CHECK(quantity_available >= 0),
    lifecycle_state TEXT NOT NULL
);

CREATE TABLE routings (
    routing_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision > 0),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    lifecycle_state TEXT NOT NULL,
    UNIQUE(product_id, routing_id),
    FOREIGN KEY(product_id) REFERENCES products(product_id),
    CHECK(effective_to IS NULL OR effective_to >= effective_from)
);

CREATE TABLE routing_operations (
    routing_operation_id TEXT PRIMARY KEY,
    routing_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence > 0),
    operation_type TEXT NOT NULL,
    standard_duration_minutes INTEGER NOT NULL CHECK(standard_duration_minutes > 0),
    required_labor INTEGER NOT NULL CHECK(required_labor > 0),
    UNIQUE(routing_id, sequence),
    FOREIGN KEY(routing_id) REFERENCES routings(routing_id)
);

CREATE TABLE eligible_machines (
    routing_operation_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    PRIMARY KEY(routing_operation_id, machine_id),
    FOREIGN KEY(routing_operation_id)
        REFERENCES routing_operations(routing_operation_id),
    FOREIGN KEY(machine_id) REFERENCES machines(machine_id)
);

CREATE TABLE machine_calendars (
    calendar_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL,
    work_date TEXT NOT NULL,
    shift TEXT NOT NULL,
    shift_start TEXT NOT NULL,
    shift_end TEXT NOT NULL,
    capacity_minutes INTEGER NOT NULL CHECK(capacity_minutes >= 0),
    labor_group TEXT NOT NULL,
    labor_capacity INTEGER NOT NULL CHECK(labor_capacity >= 0),
    UNIQUE(machine_id, work_date, shift),
    FOREIGN KEY(machine_id) REFERENCES machines(machine_id),
    CHECK(shift_end > shift_start)
);

CREATE TABLE machine_downtime (
    downtime_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL,
    downtime_start TEXT NOT NULL,
    downtime_end TEXT NOT NULL,
    reason TEXT NOT NULL,
    FOREIGN KEY(machine_id) REFERENCES machines(machine_id),
    CHECK(downtime_end > downtime_start)
);

CREATE TABLE inventory_lots (
    lot_id TEXT PRIMARY KEY,
    material_id TEXT NOT NULL,
    quantity_on_hand REAL NOT NULL CHECK(quantity_on_hand >= 0),
    available_at TEXT NOT NULL,
    expiry_date TEXT,
    FOREIGN KEY(material_id) REFERENCES materials(material_id)
);

CREATE TABLE production_orders (
    order_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    routing_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    order_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    priority TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    FOREIGN KEY(product_id) REFERENCES products(product_id),
    FOREIGN KEY(routing_id) REFERENCES routings(routing_id),
    FOREIGN KEY(product_id, routing_id)
        REFERENCES routings(product_id, routing_id),
    CHECK(due_date >= order_date)
);

CREATE TABLE operations (
    operation_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    routing_operation_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence > 0),
    operation_type TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
    required_labor INTEGER NOT NULL CHECK(required_labor > 0),
    status TEXT NOT NULL,
    UNIQUE(order_id, operation_id),
    FOREIGN KEY(order_id) REFERENCES production_orders(order_id),
    FOREIGN KEY(routing_operation_id)
        REFERENCES routing_operations(routing_operation_id)
);

CREATE TABLE material_requirements (
    requirement_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    required_quantity REAL NOT NULL CHECK(required_quantity > 0),
    FOREIGN KEY(operation_id) REFERENCES operations(operation_id),
    FOREIGN KEY(material_id) REFERENCES materials(material_id),
    UNIQUE(operation_id, material_id)
);

CREATE TABLE operation_tool_requirements (
    tool_requirement_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    required_quantity INTEGER NOT NULL CHECK(required_quantity > 0),
    FOREIGN KEY(operation_id) REFERENCES operations(operation_id),
    FOREIGN KEY(tool_id) REFERENCES tools(tool_id),
    UNIQUE(operation_id, tool_id)
);

CREATE TABLE changeover_matrix (
    from_family TEXT NOT NULL,
    to_family TEXT NOT NULL,
    changeover_minutes INTEGER NOT NULL CHECK(changeover_minutes >= 0),
    PRIMARY KEY(from_family, to_family)
);

CREATE TABLE operation_schedule (
    schedule_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    labor_group TEXT NOT NULL,
    required_labor INTEGER NOT NULL,
    tool_ids TEXT,
    tool_quantity_required INTEGER,
    sequence INTEGER NOT NULL,
    operation_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    due_date TEXT NOT NULL,
    setup_start TEXT,
    operation_start TEXT NOT NULL,
    operation_finish TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    changeover_minutes INTEGER NOT NULL,
    schedule_status TEXT NOT NULL,
    FOREIGN KEY(operation_id) REFERENCES operations(operation_id),
    FOREIGN KEY(order_id, operation_id)
        REFERENCES operations(order_id, operation_id),
    FOREIGN KEY(machine_id) REFERENCES machines(machine_id),
    CHECK(operation_finish > operation_start),
    CHECK(duration_minutes > 0),
    CHECK(changeover_minutes >= 0)
);

CREATE TABLE scheduling_exceptions (
    operation_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    exception TEXT NOT NULL,
    PRIMARY KEY(operation_id, order_id, exception),
    FOREIGN KEY(order_id, operation_id)
        REFERENCES operations(order_id, operation_id)
);

CREATE TABLE event_history (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_time TEXT,
    detail TEXT
);

CREATE TABLE ground_truth (
    scenario_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL UNIQUE,
    expected_detection TEXT NOT NULL,
    description TEXT NOT NULL
);
"""


# Insertion order respects the foreign-key dependencies.
TABLE_ORDER = [
    "products",
    "machines",
    "materials",
    "tools",
    "routings",
    "routing_operations",
    "eligible_machines",
    "machine_calendars",
    "machine_downtime",
    "inventory_lots",
    "production_orders",
    "operations",
    "material_requirements",
    "operation_tool_requirements",
    "changeover_matrix",
    "operation_schedule",
    "scheduling_exceptions",
    "event_history",
    "ground_truth",
]


def create_database():
    DATA_DIR.mkdir(exist_ok=True)

    if DB_PATH.exists():
        DB_PATH.unlink()

    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)

        for table in TABLE_ORDER:
            csv_path = DATA_DIR / f"{table}.csv"

            if not csv_path.exists():
                raise FileNotFoundError(
                    f"Missing required CSV: {csv_path}"
                )

            frame = pd.read_csv(csv_path)

            frame.to_sql(
                table,
                connection,
                if_exists="append",
                index=False
            )

        # Verify all foreign-key relationships.
        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if foreign_key_errors:
            raise ValueError(
                f"Foreign-key errors: {foreign_key_errors[:10]}"
            )

        # Verify SQLite integrity.
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise ValueError(f"Database integrity failure: {integrity}")

        connection.commit()

        # Export schema and data as a reproducible SQL seed.
        with open(SQL_PATH, "w", encoding="utf-8") as sql_file:
            for statement in connection.iterdump():
                sql_file.write(statement + "\n")

        print("DATABASE CREATION: PASS")
        print("Tables created:", len(TABLE_ORDER))
        print("Foreign-key validation: PASS")
        print("SQLite integrity check: PASS")
        print("Database:", DB_PATH)
        print("SQL seed:", SQL_PATH)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    create_database()
