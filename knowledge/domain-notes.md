# Domain notes: contract lifecycle management (CLM)

## What CLM covers
Contract lifecycle management runs from intake and clause review, through
negotiation and approval, to signature, obligation tracking, renewal, and
eventually termination or expiry. The riskiest moments are clause
acceptance (bad terms locked in for years) and renewal (auto-renewal
sleepwalking, missed notice windows).

## Clause risk, in practice
Enterprise legal teams keep a "playbook": fallback positions for the
clauses they negotiate most — liability caps, indemnity, termination,
auto-renewal, payment terms, governing law, confidentiality. This repo
implements a simplified, illustrative version of such a playbook. Each
rule has a cited ID (CLAUSE-LIAB-01 … CLAUSE-CONF-07) so a risk score is
never a black box: the breakdown names the exact rule that fired and why.

Contract risk here is the sum of failed clause weights, capped at 100.
A contract is as risky as its clauses make it — one uncapped one-sided
indemnity (30 points) plus a 15-day auto-renewal notice (25 points) is
already a high-band contract before anything else is read.

## Renewal math
Renewals compete for attention. The prioritizer combines three things
legal and procurement actually trade off: how much money is at stake
(value), how risky the paper is (risk), and how little time is left
(urgency). Weights 0.40 / 0.35 / 0.25 are documented in the README and in
`contractops/renewals.py`; they are illustrative, not industry standard.

## Obligation tracking
Signed contracts leak value through forgotten obligations: missed
true-up payments, late reports, unclaimed SLA credits. The obligation
register turns each commitment into a tracked item with a health state
(met / on_track / due_soon / overdue).

## Regulatory change
Contract terms live under changing regulation (data retention, renewal
notice rules). The regulatory feed models this as an external signal with
explicit gap behavior: if the live feed is unavailable, the agent says so
instead of inventing regulatory changes.

## What this repo is not
It is not legal advice and not a substitute for counsel. The playbook is
simplified and illustrative; real playbooks are jurisdiction-specific and
far longer. All companies, contracts, and numbers are synthetic.
