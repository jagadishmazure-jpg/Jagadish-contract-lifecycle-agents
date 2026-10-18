# Contract Lifecycle Agents

**Recruiter summary:** End-to-end contract lifecycle management on synthetic
data. A clause-risk scorer checks every clause against a cited playbook
(CLAUSE-LIAB-01 … CLAUSE-CONF-07) and explains each finding; a renewal
prioritizer ranks renewals by value × risk × days-to-expiry. Text-to-SQL
runs over read-only views behind a SELECT-only gateway, SOP answers carry
citations, and contract approvals need a human confirmation gate.
Deterministic tests (count checked by CI), Python stdlib only.

## Purpose
For legal-ops and procurement teams drowning in contract reviews: triage
which contracts need counsel, which renewals need decisions now, and which
obligations are slipping — with every risk finding traced to a named rule.
For engineers: a complete, offline-runnable example of an agentic
back-office system with guardrails.

## How this differs from coldchain/retail
The cold-chain and retail repos optimize physical flows (reefer telemetry,
shelf availability). This repo governs **paper**: the risk is in clauses,
not temperature. Its differentiators — a cited clause playbook scorer and
a value×risk×urgency renewal prioritizer — have no analogue in the
logistics repos, and neither do confirmation-gated approvals or
regulatory-change signals.

## Architecture
See [`knowledge/architecture.md`](knowledge/architecture.md) (Mermaid,
rendered on GitHub) and [`knowledge/domain-notes.md`](knowledge/domain-notes.md)
for the domain background.

## How it works, step by step
1. `telemetry.seed_db()` builds the synthetic SQLite database (seed 42,
   reference date 2026-10-18): 12 contracts, 18 clauses, 10 obligations,
   6 renewals, 6 fictional counterparties.
2. `views.create_views()` scores every contract with the clause scorer,
   ranks renewals, and exposes four read-only views.
3. `Orchestrator.run(question)` fans out: text-to-SQL (five fixed
   intents, one simplified retry, then escalation), SOP RAG with
   citations, and the regulatory signal (or an explicit gap).
4. `score_contract()` returns per-clause breakdowns; `rank_renewals()`
   returns the prioritized pipeline.
5. `approve_contract()` / `accept_high_risk_clause()` require a human
   confirmation gate; timeout denies. Everything lands in the
   hash-chained audit log.

## Real code excerpts and their real output

```python
from contractops.orchestrator import Orchestrator
o = Orchestrator()
rep = o.score_contract("CTR-1001")
print(rep["contract_score"], rep["band"])
for c in rep["clauses"][:2]:
    print(c["clause_id"], c["score"], "|", c["breakdown"])
```
```
100.0 high
CL-1001-A 20 | CLAUSE-LIAB-01 [FAIL]: cap is one-sided (+20)
CL-1001-B 30 | CLAUSE-INDEM-04 [FAIL]: indemnity is uncapped or one-sided (+30)
```

```python
for x in o.rank_renewals(3)["renewals"]:
    print(x["contract_id"], x["priority_score"], x["days_to_expiry"])
```
```
CTR-1003 77.0 -20
CTR-1007 36.1 21
CTR-1012 31.2 60
```
CTR-1003 is a lapsed auto-renewal (flagged as a control failure);
CTR-1007 is past its 30-day notice deadline.

```python
r = o.ask_sql("Which contracts are high risk?")
print(r["columns"]); print(r["rows"][0])
```
```
['contract_id', 'counterparty', 'type', 'annual_value', 'risk_score']
('CTR-1001', 'Tervanne Logistics', 'MSA', 480000.0, 100.0)
```

All figures above are verbatim from real runs in this repo.

## How to run
```bash
python -m pytest tests/ -q        # full suite, offline, stdlib only
python scripts/count_tests.py     # prints the real test total
pip install streamlit             # optional, demo UI only
streamlit run demo/app.py
```

## Guardrails and security controls
- SELECT-only SQL gateway: SEC-SELECT-01 (SELECT only), SEC-SELECT-02
  (write keywords rejected even outside string literals), SEC-SELECT-03
  (FROM/JOIN restricted to the 4 published views, and independently a
  SQLite authorizer that allows a base-table read only on behalf of a
  published view and always denies sqlite_master, writes and DDL; 100-row
  cap enforced at fetch time via `fetchmany`, never by trusting the
  query's LIMIT).
  See `docs/adr/0001-sqlite-authorizer-backstop.md`.
- Human confirmation gates on contract approvals and high-risk clause
  acceptances; timeout denies by default. Auto-renew override is defined
  as a T4 gated action in the tier table, but no override action is wired
  yet.
- Hash-chained, tamper-evident audit log (`AuditLog.verify()`).
- PII scrubbing (email/phone/SSN/card) before feedback is stored; only
  redaction counts persist.
- Live regulatory feed is a stub that reports its own unavailability
  (`SignalGap`) — never invents regulatory changes.
- See `docs/threat-model.md` and `SECURITY.md`.

## Limitations and known failures
- The clause playbook is keyword-based and simplified; adversarial
  wording can dodge a rule. It is a triage filter, **not legal advice
  and not a substitute for counsel**.
- TF-IDF has no stemming ("renewal" won't match "renewals"); mitigated
  in tests by matching SOP vocabulary.
- Renewal weights (0.40 value / 0.35 risk / 0.25 urgency) are
  illustrative, not calibrated against real outcomes.
- Jurisdiction list and notice floors are fictional simplifications.
- Notice deadlines are flagged (`past_notice_deadline`) but not escalated
  automatically; SOP-02's T2/T3 escalation is a human step.
- The "high-risk clauses" intent lists every clause of a high-risk
  contract, not only the clauses that failed a rule.
- Gateway: the authorizer allows an empty-column read of a table behind a
  view (needed for view self-joins), so `SELECT count(*)` of such a table
  returns a count if the text check is bypassed; no column data is
  readable.

## Standardization review (2026-10-18)

grokbot-portfolio reviewed this repo against the portfolio standard. Each
bug below has a regression test (`tests/test_contractops.py`, "review
fixes" section, and `tests/test_authorizer_strict.py`) that fails on the
old code.

- **Gateway bypass.** The FROM/JOIN check skipped any token starting with
  `(`, so `SELECT * FROM (contracts)` and `FROM v_contract_risk,(contracts)`
  read the raw table; the authorizer allowed every table behind a view, so
  nothing stopped it. Parenthesised tables are now checked, and the
  authorizer allows a base-table read only on behalf of a published view
  (ADR 0001, revision).
- **Clause scorer substring bugs.** "Mutual indemnity, uncapped." passed
  CLAUSE-INDEM-04 because "capped" matched inside "uncapped"; "not mutual"
  passed as mutual; "Unlimited liability" and a cap for one party only
  passed CLAUSE-LIAB-01.
- **Standard notice wording was missed.** "ninety (90) days' written
  notice" and "90 days prior written notice" parsed as no notice, so
  compliant auto-renewal and termination clauses failed.
- **Payment terms without "Net"** ("Payment due 90 days from invoice")
  passed CLAUSE-PAY-05.
- **Renewal score could exceed 100.** The value term was annual value /
  $1M with no ceiling; it is now capped at 1.0.
- **Lapsed renewals vanished from the pipeline.** `rank_renewals` kept only
  undecided renewals, so CTR-1003's lapsed auto-renewal (top priority in
  the SQL view, a control failure per SOP-02) was hidden. It is now listed
  and flagged, and each renewal says whether its notice deadline passed.
- **README overclaim:** auto-renew overrides were listed as gated, but no
  override action exists (the gate is only defined in the tier table).
- Card numbers are now redacted alongside email, phone and SSN.
- Fictional counterparties that matched real businesses were renamed
  (for example the logistics counterparty is now Tervanne Logistics).

Seed figures are unchanged: every seeded clause scores as before.

Differentiator on the seeded data (regenerated and checked by CI on every push):

<!-- run: python scripts/show_differentiator.py -->
```text
CTR-1001 contract risk 100.0 (high):
  CL-1001-A +20 | CLAUSE-LIAB-01 [FAIL]: cap is one-sided (+20)
  CL-1001-B +30 | CLAUSE-INDEM-04 [FAIL]: indemnity is uncapped or one-sided (+30)
  CL-1001-C +25 | CLAUSE-RENEW-03 [FAIL]: opt-out notice of 15 days is below 60-day floor (+25)
  CL-1001-D +25 | CLAUSE-TERM-02 [FAIL]: cure period of 10 days is below 30-day floor (+25)
Clause wording checks:
  'Mutual indemnity, uncapped.' -> CLAUSE-INDEM-04 [FAIL]: indemnity is uncapped or one-sided (+30)
  'Unlimited liability for Supplier.' -> CLAUSE-LIAB-01 [FAIL]: liability is uncapped (+20)
  "Renews annually unless either party gives ninety (90) days' written notice." -> CLAUSE-RENEW-03 [pass]: opt-out notice meets the floor (+0)
  'Payment due 90 days from invoice.' -> CLAUSE-PAY-05 [FAIL]: Net-90 exceeds Net-60 (+15)
Renewal pipeline (value x risk x urgency; lapsed renewals stay visible):
  CTR-1003 77.0 (-20d, lapsed) [lapsed renewal: control failure (SOP-02); past notice deadline]
  CTR-1007 36.1 (21d, undecided) [past notice deadline]
  CTR-1012 31.2 (60d, undecided)
  CTR-1008 24.8 (230d, undecided)
  CTR-1005 13.6 (215d, undecided)
Gateway: SELECT * FROM (contracts) -> SEC-SELECT-03: query references non-view tables: ['contracts']
```
<!-- /run -->

## Built / Written-not-run / Planned

| Status | Item |
|---|---|
| Built | Synthetic CLM telemetry (SQLite, seeded, deterministic) |
| Built | Clause-risk scorer with cited playbook (7 rules) |
| Built | Renewal prioritizer (value × risk × urgency) |
| Built | Text-to-SQL over 4 read-only views (5 intents, retry→escalate) |
| Built | SELECT-only gateway (SEC-SELECT-01/02/03) |
| Built | TF-IDF SOP RAG with citations + explicit not-found |
| Built | Regulatory signal (fake seeded / live gap stub) |
| Built | ReAct orchestrator with multi-intent fan-out |
| Built | T1–T4 escalation + confirmation gates (timeout denies) |
| Built | Hash-chained audit log with tamper detection |
| Built | PII-scrubbed feedback store |
| Built | knowledge/ docs + Mermaid architecture, 4 SOPs |
| Built | Thin Streamlit demo (lazy import, tested helpers) |
| Built | CI: ruff, pytest, docs drift check, hashed brand check, gitleaks; CodeQL; Dependabot |
| Planned | Keyed-HMAC pseudonymisation for counterparty names |
| Planned | SSO-bound approvers for confirmation gates |
| Planned | Prompt-injection test suite for the question interface |
| Planned | Append-only audit storage |

## Related repos
Part of a 12-domain enterprise agent series on one shared spine:
cold-chain logistics, retail ops, healthcare ops, insurance underwriting,
warehouse ops, energy grid, telecom incident, airline disruption,
pharma QA, predictive maintenance, marketplace seller, property ops, and
food-ingredients R&D. Each repo documents how it differs and links its
cousins instead of duplicating them.

Boundaries with the closest siblings:
- `Jagadish-insurance-underwriting-agents` scores *risks* against appetite
  rules to quote or refer; this repo scores *contract clauses* against a
  legal playbook and ranks renewals.
- `Jagadish-document-intelligence` extracts fields from documents and
  `Jagadish-document-automation` runs document versions, approvals and
  retention; this repo starts from clause text already in the database and
  does no extraction or e-signature.

## Test count

<!-- run: python scripts/count_tests.py -->
```text
115 tests collected
```
<!-- /run -->

Small self-written regression checks, not quality claims.

## Disclaimer
All companies, contracts, clauses, people, and numbers are synthetic and
fictional, generated for demonstration. This project is independent and
unaffiliated with any real company. Nothing here is legal advice.
