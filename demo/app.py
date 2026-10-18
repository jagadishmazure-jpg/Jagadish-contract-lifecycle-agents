"""Thin Streamlit demo. Run: pip install streamlit && streamlit run demo/app.py"""
try:
    import streamlit as st
except ImportError:  # pragma: no cover
    raise SystemExit("pip install streamlit, then streamlit run demo/app.py")

from contractops import demo_helpers as dh
from contractops.orchestrator import Orchestrator

st.title("Contract Lifecycle Agents (synthetic demo)")

st.subheader("Contract risk")
for row in dh.risk_summary():
    st.write(f"{row['contract_id']} ({row['counterparty']}): "
             f"{row['band']} ({row['score']})")

st.subheader("Renewal pipeline")
for r in dh.renewal_pipeline():
    st.write(f"{r['contract_id']}: priority {r['priority_score']} — "
             f"{r['days_to_expiry']}d to expiry")

st.subheader("Clause report: CTR-1001")
rep = dh.clause_report()
st.write(f"Contract score {rep['contract_score']} ({rep['band']})")
for c in rep["clauses"]:
    st.write(f"- {c['clause_id']}: {c['score']} — {c['breakdown']}")

st.subheader("Ask")
q = st.selectbox("Question", dh.default_questions())
if st.button("Run"):
    orch = Orchestrator()
    st.json(orch.run(q))
