"""Lightweight dashboard for generated SmartPlant outputs."""
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartPlant Scheduler", layout="wide")
st.title("SmartPlant Production Scheduler")
st.caption("Constraint-aware manufacturing schedule | Seed 20261022")
base=Path("data")
required=["operation_schedule.csv","production_orders.csv","machines.csv","scheduling_exceptions.csv"]
if not all((base/f).exists() for f in required):
    st.warning("Run `python run.py` first to generate the data and schedule.")
    st.stop()
s=pd.read_csv(base/"operation_schedule.csv",parse_dates=["setup_start","operation_start","operation_finish"])
o=pd.read_csv(base/"production_orders.csv")
m=pd.read_csv(base/"machines.csv")
e=pd.read_csv(base/"scheduling_exceptions.csv")
cols=st.columns(4)
cols[0].metric("Scheduled operations",f"{len(s):,}")
cols[1].metric("Orders",f"{len(o):,}")
cols[2].metric("Machines",f"{len(m):,}")
cols[3].metric("Exceptions",f"{len(e):,}")
st.subheader("Operations by type")
if not s.empty: st.bar_chart(s.groupby("operation_type").size())
left,right=st.columns(2)
with left:
    st.subheader("Machine workload")
    st.bar_chart(s.groupby("machine_id").duration_minutes.sum().sort_values(ascending=False))
with right:
    st.subheader("Operations by priority")
    st.bar_chart(s.groupby("priority").size())
st.subheader("Schedule")
search=st.text_input("Filter by order or operation ID")
view=s
if search: view=s[s.order_id.astype(str).str.contains(search,case=False) | s.operation_id.astype(str).str.contains(search,case=False)]
st.dataframe(view, use_container_width=True, height=420)
st.subheader("Exceptions")
if e.empty: st.success("No scheduling exceptions in this run.")
else: st.dataframe(e,use_container_width=True)
for filename in ["operation_schedule.csv","scheduling_exceptions.csv","ground_truth.csv","source_manifest.json"]:
    path=base/filename
    if path.exists(): st.download_button(f"Download {filename}",path.read_bytes(),file_name=filename)
