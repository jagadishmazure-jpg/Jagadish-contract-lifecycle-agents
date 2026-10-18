"""Fixed-template text-to-SQL over the 4 read-only views.

Five intents. One simplified retry: if the first template fails to parse a
parameter, a simpler template is tried; otherwise EscalationNeeded is raised.
"""
from __future__ import annotations

import re


class EscalationNeeded(Exception):
    """Raised when the question cannot be mapped to a safe template."""


def _band(question: str):
    m = re.search(r"\b(high|medium|low)\b[-\s]?risk", question.lower())
    return m.group(1) if m else None


def _days(question: str):
    m = re.search(r"(\d+)\s*days?", question.lower())
    return int(m.group(1)) if m else None


def _health(question: str):
    m = re.search(r"\b(overdue|due soon|due_soon|on track|on_track|met)\b",
                  question.lower())
    if not m:
        return None
    return m.group(1).replace(" ", "_")


INTENTS = (
    "contracts_by_risk",
    "upcoming_renewals",
    "obligation_compliance",
    "high_risk_clauses",
    "counterparty_exposure",
)


def detect_intent(question: str) -> str:
    q = question.lower()
    if "renewal" in q or "expir" in q:
        return "upcoming_renewals"
    if "obligation" in q or "compliance" in q or "overdue" in q:
        return "obligation_compliance"
    if "clause" in q:
        return "high_risk_clauses"
    if "counterparty" in q or "exposure" in q or "spend" in q:
        return "counterparty_exposure"
    if "contract" in q or "risk" in q:
        return "contracts_by_risk"
    raise EscalationNeeded(f"no intent matched: {question!r}")


def to_sql(question: str) -> tuple[str, str]:
    """Return (intent, sql). May raise EscalationNeeded."""
    intent = detect_intent(question)
    if intent == "contracts_by_risk":
        band = _band(question)
        if band:
            return intent, (
                "SELECT contract_id, counterparty, type, annual_value, "
                f"risk_score FROM v_contract_risk WHERE risk_band = '{band}' "
                "ORDER BY risk_score DESC")
        # simplified retry: drop the band filter instead of escalating
        return intent, (
            "SELECT contract_id, counterparty, risk_band, risk_score "
            "FROM v_contract_risk ORDER BY risk_score DESC")
    if intent == "upcoming_renewals":
        days = _days(question) or 90
        return intent, (
            "SELECT contract_id, counterparty, expiry_date, days_to_expiry, "
            f"priority_score FROM v_upcoming_renewals WHERE days_to_expiry <= {days} "
            "ORDER BY priority_score DESC")
    if intent == "obligation_compliance":
        health = _health(question)
        if health:
            return intent, (
                "SELECT obligation_id, contract_id, kind, due_date "
                f"FROM v_obligation_status WHERE health = '{health}' "
                "ORDER BY due_date")
        return intent, (
            "SELECT health, COUNT(*) AS n FROM v_obligation_status "
            "GROUP BY health ORDER BY n DESC")
    if intent == "high_risk_clauses":
        band = _band(question) or "high"
        # Views only: v_contract_risk carries the scored band, so the raw
        # _contract_risk table is never referenced (SEC-SELECT-03).
        return intent, (
            "SELECT c.contract_id, c.clause_id, c.clause_type "
            "FROM v_clause_risk c JOIN v_contract_risk r "
            "ON r.contract_id = c.contract_id "
            f"WHERE r.risk_band = '{band}' ORDER BY r.risk_score DESC")
    if intent == "counterparty_exposure":
        return intent, (
            "SELECT counterparty, COUNT(*) AS contracts, "
            "ROUND(SUM(annual_value), 2) AS total_value, "
            "ROUND(AVG(risk_score), 1) AS avg_risk "
            "FROM v_contract_risk GROUP BY counterparty "
            "ORDER BY total_value DESC")
    raise EscalationNeeded(f"no template for intent {intent}")
