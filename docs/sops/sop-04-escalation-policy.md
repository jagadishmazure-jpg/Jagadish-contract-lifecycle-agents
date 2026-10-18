# SOP-04: Escalation Policy

## Tier ownership
T1 (analyst) owns clause reviews and renewal reminders. T2 (contract
manager) owns obligation chasing and stalled renewals. T3 (legal counsel)
owns contract approvals and high-risk clause acceptances. T4 (general
counsel) owns auto-renew overrides and dispute declarations.

## Confirmation gates
Contract approvals and high-risk clause acceptances always require a
human confirmation gate. The gate names the approver and the decision;
a gate that times out denies by default. No agent may self-approve.

## Escalation records
Every escalation records the action, the tier, the reason, and whether a
gate was required. Escalations are written to the hash-chained audit log
and are tamper-evident.

## Regulatory changes
When the regulatory feed reports a change affecting a clause type, all
active contracts carrying that clause type are re-scored within one
business day. If the live feed is unavailable, the gap is stated
explicitly — regulatory impact is never assumed.
