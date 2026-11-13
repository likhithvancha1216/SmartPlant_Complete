
import sqlite3
from pathlib import Path

DB_PATH = Path("data/smartplant.db")


def test_database_has_19_tables():
    with sqlite3.connect(DB_PATH) as con:
        tables = con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

    assert len(tables) == 19


def test_primary_keys_exist():
    expected = {
        "products": "product_id",
        "machines": "machine_id",
        "materials": "material_id",
        "tools": "tool_id",
        "routings": "routing_id",
        "routing_operations": "routing_operation_id",
        "production_orders": "order_id",
        "operations": "operation_id",
        "operation_schedule": "schedule_id",
        "ground_truth": "scenario_id",
    }

    with sqlite3.connect(DB_PATH) as con:
        for table, column in expected.items():
            info = con.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()

            primary_keys = [
                row[1] for row in info if row[5] > 0
            ]

            assert column in primary_keys


def test_foreign_key_integrity():
    with sqlite3.connect(DB_PATH) as con:
        errors = con.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    assert errors == []


def test_database_integrity():
    with sqlite3.connect(DB_PATH) as con:
        result = con.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    assert result == "ok"


def test_schedule_has_2000_records():
    with sqlite3.connect(DB_PATH) as con:
        count = con.execute(
            "SELECT COUNT(*) FROM operation_schedule"
        ).fetchone()[0]

    assert count == 2000


def test_sql_seed_file_is_not_empty():
    seed = Path("data/smartplant_seed.sql")
    assert seed.exists()
    assert seed.stat().st_size > 0
