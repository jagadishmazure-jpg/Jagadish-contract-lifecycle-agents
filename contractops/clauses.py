"""Clause-risk scorer: scores contract clauses against a cited playbook.

Each rule has an ID (CLAUSE-*) so every risk finding traces to a named rule.
Contract risk = sum of failed clause weights, capped at 100. The rules below
are a simplified illustrative playbook, not legal advice.
"""
from __future__ import annotations

import re


def _months(text: str):
    m = re.search(r"(\d+)\s*months?", text.lower())
    return int(m.group(1)) if m else None


def _days_notice(text: str):
    m = re.search(r"(\d+)\s*days?\s*(written\s*)?notice", text.lower())
    return int(m.group(1)) if m else None


def _net_days(text: str):
    m = re.search(r"net[ -]?(\d+)", text.lower())
    return int(m.group(1)) if m else None


def _cure_days(text: str):
    m = re.search(r"(\d+)[ -]?day cure", text.lower())
    return int(m.group(1)) if m else None


# rule_id -> (weight, applies_to clause types, description)
RULES = {
    "CLAUSE-LIAB-01": (
        20, ("liability_cap",),
        "Liability cap must be mutual and at least 12 months of fees.",
    ),
    "CLAUSE-TERM-02": (
        25, ("termination",),
        "Termination for convenience needs >= 90 days notice; "
        "cure periods must be >= 30 days.",
    ),
    "CLAUSE-RENEW-03": (
        25, ("auto_renewal",),
        "Auto-renewal opt-out notice must be >= 60 days.",
    ),
    "CLAUSE-INDEM-04": (
        30, ("indemnity",),
        "Indemnity must be mutual and capped.",
    ),
    "CLAUSE-PAY-05": (
        15, ("payment_terms",),
        "Payment terms must be Net-60 or better.",
    ),
    "CLAUSE-GOV-06": (
        15, ("governing_law",),
        "Governing law must be an approved jurisdiction "
        "(Delaware, New York, England, Singapore).",
    ),
    "CLAUSE-CONF-07": (
        10, ("confidentiality",),
        "Confidentiality should be mutual.",
    ),
}

_APPROVED_JURISDICTIONS = ("delaware", "new york", "england", "singapore")


def _check(rule_id: str, text: str):
    """Return (failed: bool, note: str)."""
    t = text.lower()
    if rule_id == "CLAUSE-LIAB-01":
        if "one-sided" in t:
            return True, "cap is one-sided"
        months = _months(t)
        if months is not None and months < 12:
            return True, f"cap of {months} months is below 12-month floor"
        return False, "mutual cap at >= 12 months"
    if rule_id == "CLAUSE-TERM-02":
        cure = _cure_days(t)
        if cure is not None and cure < 30:
            return True, f"cure period of {cure} days is below 30-day floor"
        notice = _days_notice(t)
        if "for convenience" in t and (notice is None or notice < 90):
            return True, "convenience termination notice below 90 days"
        return False, "termination rights meet the floor"
    if rule_id == "CLAUSE-RENEW-03":
        notice = _days_notice(t)
        if notice is None or notice < 60:
            return True, f"opt-out notice of {notice} days is below 60-day floor"
        return False, "opt-out notice meets the floor"
    if rule_id == "CLAUSE-INDEM-04":
        if "without cap" in t or "one-sided" in t:
            return True, "indemnity is uncapped or one-sided"
        if "mutual" in t and "capped" in t:
            return False, "mutual and capped"
        return True, "indemnity terms are not mutual-and-capped"
    if rule_id == "CLAUSE-PAY-05":
        net = _net_days(t)
        if net is not None and net > 60:
            return True, f"Net-{net} exceeds Net-60"
        return False, "payment terms within Net-60"
    if rule_id == "CLAUSE-GOV-06":
        if any(j in t for j in _APPROVED_JURISDICTIONS):
            return False, "approved jurisdiction"
        return True, "jurisdiction is not on the approved list"
    if rule_id == "CLAUSE-CONF-07":
        if "one-sided" in t:
            return True, "confidentiality is one-sided"
        return False, "confidentiality is mutual"
    raise ValueError(f"unknown rule {rule_id}")


def score_clause(clause_type: str, text: str) -> dict:
    """Score one clause. Returns score, band, failed rules, breakdown."""
    failed = []
    breakdown = []
    score = 0
    for rule_id, (weight, applies_to, _desc) in RULES.items():
        if clause_type not in applies_to:
            continue
        is_fail, note = _check(rule_id, text)
        mark = "FAIL" if is_fail else "pass"
        breakdown.append(f"{rule_id} [{mark}]: {note} (+{weight if is_fail else 0})")
        if is_fail:
            score += weight
            failed.append({"rule_id": rule_id, "weight": weight, "note": note})
    score = min(score, 100)
    return {
        "score": score,
        "band": risk_band(score),
        "failed": failed,
        "breakdown": "; ".join(breakdown) if breakdown else "no applicable rules",
    }


def risk_band(score: float) -> str:
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def contract_risk_score(clauses: list) -> float:
    """Contract risk = sum of clause scores, capped at 100."""
    return float(min(sum(score_clause(c["clause_type"], c["text"])["score"]
                         for c in clauses), 100))
