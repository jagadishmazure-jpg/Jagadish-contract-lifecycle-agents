# Interview points

## The 30-second pitch
"I built an end-to-end contract lifecycle agent on synthetic data: a
clause-risk scorer that cites the exact playbook rule behind every
finding, a renewal prioritizer trading off value, risk, and days to
expiry, text-to-SQL over read-only views behind a SELECT-only gateway,
SOP-grounded answers with citations, T1–T4 escalation with confirmation
gates, and a hash-chained audit log. 40+ deterministic tests, stdlib
only."

## Likely questions
- **Why fixed-template text-to-SQL instead of generated SQL?**
  Determinism and auditability. The gateway can actually enforce
  SELECT-only on five known templates; generated SQL needs a much
  stronger sandbox. Trade-off: no ad-hoc questions.
- **How does the clause scorer stay explainable?** Every rule has a
  cited ID; the breakdown lists pass/fail per rule with the weight it
  contributed. A lawyer can challenge rule CLAUSE-INDEM-04 without
  trusting a score.
- **Why sum clause scores instead of max?** Counsel triages a redline
  by accumulation — several medium risks together read as high risk.
  Capped at 100 so one terrible contract doesn't distort the scale.
- **What stops the agent approving a bad contract?** The confirmation
  gate: `approve_contract` and `accept_high_risk_clause` require a human
  callback; timeout denies by default; denials are audited.
- **How do you handle the regulatory feed being down?** Explicit
  `SignalGap` — the agent reports unavailability instead of inventing
  regulatory changes.
- **Where's the PII boundary?** Feedback free text is scrubbed by
  `pii.py` (email/phone/SSN) before storage; only redaction counts are
  kept.

## Failure modes I can speak to
- TF-IDF has no stemming: "renewal" won't match "renewals" in an SOP.
  Mitigated in tests by matching the SOP vocabulary; real fix is
  stemming or embeddings.
- The playbook is keyword-based: adversarial clause wording can dodge a
  rule. It's a triage filter, not a substitute for counsel.
- Renewal weights (0.40/0.35/0.25) are illustrative, not calibrated.
