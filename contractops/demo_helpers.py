"""Thin, fully-tested helpers behind the Streamlit demo (stdlib only)."""
from __future__ import annotations

from .orchestrator import Orchestrator


def risk_summary() -> list[dict]:
    orch = Orchestrator()
    out = orch.ask_sql("contracts by risk")
    return [
        {"contract_id": r[0], "counterparty": r[1], "band": r[2],
         "score": r[3]}
        for r in out["rows"]
    ]


def renewal_pipeline(limit: int = 5) -> list[dict]:
    orch = Orchestrator()
    return orch.rank_renewals(limit=limit)["renewals"]


def clause_report(contract_id: str = "CTR-1001") -> dict:
    orch = Orchestrator()
    return orch.score_contract(contract_id)


def default_questions() -> list[str]:
    return [
        "Which contracts are high risk?",
        "Which renewals expire within 30 days?",
        "What obligations are overdue?",
        "What is our counterparty exposure?",
    ]
