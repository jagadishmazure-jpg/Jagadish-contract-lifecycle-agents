# Security policy

## Reporting
Do not open public issues for security concerns in this demo repo.
Use GitHub's private vulnerability reporting on the repo page.

## Scope
This is a synthetic-data demo: no real contracts, no real PII, no
production credentials. Security controls demonstrated here:

- SELECT-only SQL gateway (SEC-SELECT-01/02/03) over read-only views.
- Human confirmation gates before contract approvals and high-risk
  clause acceptances; timeout denies by default.
- Hash-chained, tamper-evident audit log.
- PII scrubbing (email/phone/SSN) before feedback is stored.
- No network calls in the default path; the live regulatory feed is a
  stub that reports its own unavailability.

## Not covered
Keyed pseudonymisation, SSO-bound approvers, prompt-injection test
suite, and append-only audit storage are documented as planned
hardening, not built here.
