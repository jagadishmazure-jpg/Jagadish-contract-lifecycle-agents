"""Feedback capture: thumbs / corrections with PII scrubbed before storage.

Every record links back to the session and turn that produced it, and the
free text is scrubbed by PIIScrubber before it ever touches the store.
"""
from __future__ import annotations

from .pii import PIIScrubber

_VALID_KINDS = ("thumbs_up", "thumbs_down", "correction")


class FeedbackError(Exception):
    pass


class FeedbackStore:
    def __init__(self):
        self.records = []
        self._scrubber = PIIScrubber()

    def add(self, kind: str, text: str, session_id: str,
            turn_id: str) -> dict:
        if kind not in _VALID_KINDS:
            raise FeedbackError(f"unknown feedback kind: {kind!r}")
        if not text or not text.strip():
            raise FeedbackError("feedback text must not be empty")
        if not session_id or not turn_id:
            raise FeedbackError("session_id and turn_id are required")
        clean, counts = self._scrubber.scrub(text)
        record = {
            "kind": kind,
            "text": clean,
            "redactions": counts,
            "session_id": session_id,
            "turn_id": turn_id,
        }
        self.records.append(record)
        return record
