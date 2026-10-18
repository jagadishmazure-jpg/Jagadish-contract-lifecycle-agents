"""PII scrubber: redacts email/phone/SSN before feedback is stored.

Redaction counts are kept so reviewers can see how much was removed
without ever seeing the original values.
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Phone: (?<!\w) (not \b) so parenthesised numbers match at string start;
# covers (555) 123-4567, +1 (555) 123-4567, 555.123.4567, 555-123-4567.
# Does NOT match dates like 2026-10-18 (wrong group sizes).
_PHONE = re.compile(
    r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)\s?|\d{3}[-.\s]?)\d{3}[-.\s]?\d{4}\b")
# SSN: strict 3-2-4 groups; does NOT match dates like 2026-10-18.
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Card: four groups of four (space or dash) or 13-16 contiguous digits.
_CARD = re.compile(r"\b(?:\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}|\d{13,16})\b")


class PIIScrubber:
    def scrub(self, text: str) -> tuple[str, dict]:
        counts = {"email": 0, "phone": 0, "ssn": 0, "card": 0}

        def _sub(pattern, label, s):
            def repl(m):
                counts[label] += 1
                return f"[REDACTED-{label.upper()}]"
            return pattern.sub(repl, s)

        out = _sub(_EMAIL, "email", text)
        out = _sub(_PHONE, "phone", out)
        out = _sub(_SSN, "ssn", out)
        out = _sub(_CARD, "card", out)
        return out, counts
