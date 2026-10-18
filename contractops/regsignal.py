"""Regulatory-change signal with fake and live backends.

FakeRegSignal is seeded and deterministic. LiveRegSignal is a stub that
raises SignalGap — the agent must say the feed is unavailable, never invent
regulatory changes.
"""
from __future__ import annotations


class SignalGap(Exception):
    """Raised when the live regulatory feed is unavailable."""


_FAKE_ITEMS = [
    {
        "id": "REG-2026-014",
        "topic": "data-retention",
        "summary": "Draft amendment extends minimum data-retention to 7 years; "
                   "affects confidentiality and record-keeping clauses.",
        "affects_clause_types": ["confidentiality"],
    },
    {
        "id": "REG-2026-021",
        "topic": "auto-renewal",
        "summary": "Proposed rule requires 60-day opt-out notice for "
                   "auto-renewing commercial contracts.",
        "affects_clause_types": ["auto_renewal"],
    },
]


class FakeRegSignal:
    """Seeded fake regulatory feed."""

    def __init__(self, items=None):
        self._items = items if items is not None else list(_FAKE_ITEMS)

    def latest(self, topic: str | None = None):
        if topic:
            return [i for i in self._items if i["topic"] == topic]
        return list(self._items)


class LiveRegSignal:
    """Live backend stub — always reports the gap explicitly."""

    def latest(self, topic: str | None = None):  # noqa: ARG002
        raise SignalGap(
            "live regulatory feed is not connected; "
            "no regulatory changes can be reported")
