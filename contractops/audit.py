"""Hash-chained audit log with tamper detection."""
from __future__ import annotations

import hashlib
import json
import time


def _digest(prev: str, event: str, payload: dict, ts: float) -> str:
    body = json.dumps({"prev": prev, "event": event, "payload": payload,
                       "ts": ts}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


class AuditLog:
    def __init__(self):
        self.entries = []
        self._prev = "GENESIS"

    def append(self, event: str, payload: dict) -> dict:
        ts = time.time()
        digest = _digest(self._prev, event, payload, ts)
        entry = {"event": event, "payload": payload, "ts": ts,
                 "prev": self._prev, "digest": digest}
        self.entries.append(entry)
        self._prev = digest
        return entry

    def verify(self) -> bool:
        prev = "GENESIS"
        for e in self.entries:
            if e["prev"] != prev:
                return False
            if _digest(e["prev"], e["event"], e["payload"], e["ts"]) != e["digest"]:
                return False
            prev = e["digest"]
        return True
