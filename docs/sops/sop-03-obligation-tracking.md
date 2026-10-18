# SOP-03: Obligation Tracking

## Obligation register
Every payment, report, and SLA commitment in a signed contract becomes a
tracked obligation with a due date and an owner. Obligations are never
tracked in email or spreadsheets alone.

## Health states
An obligation is met, on_track, due_soon (within 14 days), or overdue.
Overdue obligations page the contract owner immediately and escalate to
T2 after 7 days. Two missed obligations on one contract trigger a full
contract health review.

## Evidence
Each obligation closure needs evidence attached: a payment reference, a
report file name, or an SLA measurement. The evidence pointer is stored
in the audit log alongside the closure event.

## Counterparty obligations
Obligations owed by the counterparty are chased on the same cadence.
A counterparty with two overdue obligations is flagged in the
counterparty exposure view for the next business review.
