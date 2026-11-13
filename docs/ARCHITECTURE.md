# Architecture

1. `smartplant.generator.generate_data()` creates deterministic source/master data with seed 20261022.
2. `smartplant.scheduler.run_scheduler()` sequences orders by priority and due date, then schedules operations subject to precedence, machine eligibility, calendars, downtime, material readiness, labor capacity, shared tool capacity and family changeovers.
3. `smartplant.validation` independently checks keys, relationships, machine intervals, shift/downtime, precedence, labor, tools and material readiness.
4. `run.py` exports source tables, schedule, exceptions, event history, ground-truth labels and a SHA-256 manifest.
5. `app.py` presents the resulting CSV outputs in Streamlit.

The scheduler is a deterministic serial heuristic; it is not a proof of global optimality. The five ground-truth rows describe negative scenario labels separately and are never used as scheduler inputs.
