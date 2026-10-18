# Contract Lifecycle Agents

**Recruiter summary:** End-to-end contract lifecycle management on synthetic
data. A clause-risk scorer checks every clause against a cited playbook
(CLAUSE-LIAB-01 … CLAUSE-CONF-07) and explains each finding; a renewal
prioritizer ranks renewals by value × risk × days-to-expiry. Text-to-SQL
runs over read-only views behind a SELECT-only gateway, SOP answers carry
citations, and contract approvals need a human confirmation gate. 63
deterministic tests, Python stdlib only.

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
CTR-1007 36.1 21
CTR-1012 31.2 60
CTR-1008 24.8 230
```

```python
r = o.ask_sql("Which contracts are high risk?")
print(r["columns"]); print(r["rows"][0])
```
```
['contract_id', 'counterparty', 'type', 'annual_value', 'risk_score']
('CTR-1001', 'Northgate Logistics', 'MSA', 480000.0, 100.0)
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
  (FROM/JOIN restricted to the 4 published views; SQLite authorizer
  backstop denies writes/DDL/sqlite_master; 100-row cap enforced at fetch
  time via `fetchmany`, never by trusting the query's LIMIT).
  See `docs/adr/0001-sqlite-authorizer-backstop.md`.
- Human confirmation gates on contract approvals, high-risk clause
  acceptances, and auto-renew overrides; timeout denies by default.
- Hash-chained, tamper-evident audit log (`AuditLog.verify()`).
- PII scrubbing (email/phone/SSN) before feedback is stored; only
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
| Written-not-run | `.github/workflows/ci.yml` (pushed by the standardizing assistant) |
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

## Test count
63 tests, all passing (`python scripts/count_tests.py`). Small
self-written regression checks, not quality claims.

## Disclaimer
All companies, contracts, clauses, people, and numbers are synthetic and
fictional, generated for demonstration. This project is independent and
unaffiliated with any real company. Nothing here is legal advice.
