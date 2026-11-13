# SmartPlant Scheduler — Complete Project Package

This package contains the SmartPlant manufacturing scheduling source code, full-scale deterministic source datasets, documentation, tests and a Streamlit dashboard.

## Included source data
- 100 products
- 40 machines
- 500 production orders
- 2,000 operations
- 200 materials and 200 inventory lots
- 4 shared tool pools and 2,000 tool requirements
- 4,160 machine shift-calendar rows (60-day planning horizon)
- Machine downtime, routing, eligible-machine, material-requirement and changeover tables
- Ground-truth scenario catalogue for five required negative cases

Seed: `20261022`. Source datasets are already included under `data/`.

## Run on your Mac
1. Extract the ZIP file.
2. Open the extracted `SmartPlant_Complete` folder in VS Code.
3. Open Terminal → New Terminal.
4. Run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m smartplant.scheduler
```

The scheduler writes `data/operation_schedule.csv` and `data/scheduling_exceptions.csv`. The exceptions file is overwritten even when there are zero exceptions, preventing stale results.

Alternatively, double-click `START_HERE_MAC.command` to install dependencies and run the scheduler.

## Dashboard
After running the scheduler:

```bash
streamlit run app.py
```

## Tests
```bash
pytest -q
```

## Important design note
The scheduling engine is a deterministic serial heuristic, not a proof of global optimality. It checks machine calendars/downtime, operation precedence, material readiness, labor-group capacity, shared-tool capacity and sequence-dependent changeovers. The ground-truth CSV is a separate labelled scenario catalogue and is not used as scheduler input.
