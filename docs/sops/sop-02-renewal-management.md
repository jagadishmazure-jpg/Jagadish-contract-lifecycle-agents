# SOP-02: Renewal Management

## Renewal pipeline
Renewals are prioritized by value, contract risk, and days to expiry:
priority = 100 * (0.40 * value_norm + 0.35 * risk_norm + 0.25 * urgency).
The ranked list is reviewed weekly by the contract owner.

## Notice discipline
The renewal owner is alerted at twice the contractual notice period.
If no decision is recorded by the notice deadline, the renewal escalates
to T2 and then T3. Auto-renew overrides always require a T4 confirmation
gate — a lapsed auto-renewal is treated as a control failure.

## Decision options
Each renewal ends in one of: renew, renegotiate, or terminate. The
decision, the approver, and the business reason are written to the audit
log. "Undecided" is not a valid state past the notice deadline.

## High-risk renewals
Renewals on contracts in the high risk band get a fresh clause review
before any decision. The clause scorer re-runs and any new failures are
attached to the renewal record.
