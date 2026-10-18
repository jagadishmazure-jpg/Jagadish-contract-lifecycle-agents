"""Renewal prioritizer: ranks renewals by value x risk x days-to-expiry.

priority = 100 * (0.40 * value_norm + 0.35 * risk_norm + 0.25 * urgency)
  value_norm = annual_value / 1_000_000
  risk_norm  = contract risk score / 100
  urgency    = max(0, 1 - days_to_expiry / 180); already-expired => 1.0
"""
from __future__ import annotations

import datetime

VALUE_NORM = 1_000_000.0
URGENCY_WINDOW_DAYS = 180


def days_to_expiry(expiry_date: str, ref_date: str) -> int:
    exp = datetime.date.fromisoformat(expiry_date)
    ref = datetime.date.fromisoformat(ref_date)
    return (exp - ref).days


def priority(annual_value: float, risk_score: float,
             expiry_date: str, ref_date: str) -> dict:
    days = days_to_expiry(expiry_date, ref_date)
    value_norm = annual_value / VALUE_NORM
    risk_norm = risk_score / 100.0
    if days < 0:
        urgency = 1.0
    else:
        urgency = max(0.0, 1.0 - days / URGENCY_WINDOW_DAYS)
    score = round(100.0 * (0.40 * value_norm + 0.35 * risk_norm
                           + 0.25 * urgency), 1)
    breakdown = (
        f"value {annual_value:,.0f} -> {value_norm:.3f} (x0.40); "
        f"risk {risk_score:.0f} -> {risk_norm:.3f} (x0.35); "
        f"{days}d to expiry -> urgency {urgency:.3f} (x0.25); "
        f"priority {score}"
    )
    return {"priority_score": score, "days_to_expiry": days,
            "breakdown": breakdown}
