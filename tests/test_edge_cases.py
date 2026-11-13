
import pandas as pd
from pathlib import Path
import sqlite3


def test_ground_truth_has_five_scenarios():
    ground_truth = pd.read_csv("data/ground_truth.csv")

    assert len(ground_truth) == 5

    expected = {
        "MACHINE_OVERLAP",
        "PRECEDENCE_VIOLATION",
        "MATERIAL_BEFORE_AVAILABILITY",
        "OUTSIDE_SHIFT",
        "CHANGEOVER_OMITTED",
    }

    assert set(ground_truth["scenario"]) == expected


def test_sqlite_database_contains_all_tables():
    connection = sqlite3.connect("data/smartplant.db")

    tables = pd.read_sql_query(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%'",
        connection
    )["name"].tolist()

    connection.close()

    assert len(tables) == 19
    assert "operation_schedule" in tables
    assert "ground_truth" in tables


def test_sql_seed_file_exists():
    assert Path("data/smartplant_seed.sql").exists()
    assert Path("data/smartplant_seed.sql").stat().st_size > 0
