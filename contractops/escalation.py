"""T1-T4 escalation tiers plus confirmation gates.

Contract approvals and high-risk clause acceptances always require a
human confirmation. A gate that times out denies by default.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ConfirmationGate:
    name: str
    approver: Callable[[], bool] | None = None
    timeout_s: float = 30.0
    decided_at: float = field(default=0.0, init=False)
    decision: bool | None = field(default=None, init=False)

    def request(self) -> bool:
        start = time.monotonic()
        if self.approver is None:
            self.decision = False
        else:
            try:
                self.decision = bool(self.approver())
            except Exception:
                self.decision = False
        elapsed = time.monotonic() - start
        if elapsed > self.timeout_s:
            self.decision = False  # timeout denies
        self.decided_at = time.monotonic()
        return self.decision


TIERS = ("T1", "T2", "T3", "T4")

# Which tier owns which decision, and whether a gate is required.
POLICY = {
    "clause_review": ("T1", False),
    "renewal_reminder": ("T1", False),
    "obligation_chase": ("T2", False),
    "contract_approval": ("T3", True),
    "high_risk_clause_accept": ("T3", True),
    "auto_renew_override": ("T4", True),
}


def tier_for(action: str) -> str:
    return POLICY.get(action, ("T2", False))[0]


def gate_required(action: str) -> bool:
    return POLICY.get(action, ("T2", False))[1]


def escalate(action: str, reason: str, audit_log=None) -> dict:
    tier, gated = POLICY.get(action, ("T2", False))
    record = {"action": action, "tier": tier, "gate_required": gated,
              "reason": reason}
    if audit_log is not None:
        audit_log.append("escalation", record)
    return record
