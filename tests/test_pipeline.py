import smartplant.generator as generator
from smartplant.generator import generate_data
from smartplant.scheduler import run_scheduler
from smartplant.validation import validate_data, validate_schedule

def test_full_scale_source_counts():
    d = generate_data()
    assert len(d["products"]) == 100
    assert len(d["machines"]) == 40
    assert len(d["production_orders"]) == 500
    assert len(d["operations"]) == 2000
    assert len(d["materials"]) == 200
    assert len(d["tools"]) == 4
    assert len(d["operation_tool_requirements"]) == 2000
    assert validate_data(d) == []

def test_small_schedule_constraints(monkeypatch):
    monkeypatch.setattr(generator, "ORDER_COUNT", 20)
    d = generate_data()
    s, e = run_scheduler(d)
    assert len(s) == len(d["operations"])
    assert e.empty
    assert validate_schedule(d, s) == []
