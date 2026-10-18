# Architecture

```mermaid
flowchart TB
    subgraph Data["Synthetic data plane (SQLite, seeded)"]
        TEL[telemetry.py<br/>contracts · clauses · obligations<br/>counterparties · renewals]
        VIEWS[views.py<br/>4 read-only views<br/>SEC-SELECT-01/02/03 gateway]
    end
    subgraph Brain["Agent plane"]
        T2S[text2sql.py<br/>5 fixed intents + 1 retry]
        CLAUSE[clauses.py<br/>clause-risk scorer<br/>cited playbook rules]
        RENEW[renewals.py<br/>renewal prioritizer<br/>value × risk × urgency]
        RAG[sop_rag.py<br/>TF-IDF over 4 SOPs<br/>file §section citations]
        REG[regsignal.py<br/>fake seeded / live gap]
        ORCH[orchestrator.py<br/>ReAct fan-out]
    end
    subgraph Control["Control plane"]
        ESC[escalation.py<br/>T1–T4 + confirmation gates]
        AUD[audit.py<br/>hash-chained log]
        FB[feedback.py + pii.py<br/>PII-scrubbed feedback]
    end
    TEL --> VIEWS
    VIEWS --> T2S
    TEL --> CLAUSE
    TEL --> RENEW
    ORCH --> T2S
    ORCH --> CLAUSE
    ORCH --> RENEW
    ORCH --> RAG
    ORCH --> REG
    ORCH --> ESC
    ORCH --> AUD
    ORCH --> FB
    ESC --> AUD
```

## How it works, step by step
1. `telemetry.seed_db()` builds the synthetic SQLite database (seed 42,
   fixed reference date 2026-10-18).
2. `views.create_views()` materializes contract risk (via the clause
   scorer) and renewal priority into helper tables, then exposes the four
   read-only views.
3. A question reaches `Orchestrator.run()`: text-to-SQL maps it to one of
   five fixed templates (one simplified retry, then escalation); the SOP
   RAG answers process questions with citations; the regulatory signal
   reports changes or an explicit gap.
4. `score_contract()` runs every clause of a contract through the
   playbook and returns per-clause breakdowns plus the contract total.
5. `rank_renewals()` scores every undecided renewal on value, risk, and
   urgency and returns the ranked pipeline.
6. Gated actions (`approve_contract`, `accept_high_risk_clause`) require
   a human confirmation gate; a timed-out gate denies by default.
7. Every turn, escalation, and decision is appended to the hash-chained
   audit log; feedback text is PII-scrubbed before storage.

## Key decisions (ADRs, short form)
- **Fixed-template text-to-SQL, not generated SQL.** Deterministic,
  auditable, and the SELECT-only gateway is enforceable. Cost: no
  ad-hoc questions — anything outside the five intents escalates.
- **Clause rules as code with cited IDs.** Every risk finding traces to
  a named playbook rule, which is what legal reviewers need to trust or
  challenge a score.
- **Contract risk = sum of clause scores (capped).** A contract with
  several medium-risk clauses reads as high risk, matching how counsel
  actually triages a redline.
- **Explicit signal gaps.** The regulatory feed never hallucinates;
  unavailability is reported as a gap.
- **PII scrubbing before storage.** Feedback free text is scrubbed by
  `pii.py` before it touches the store; redaction counts are kept.
