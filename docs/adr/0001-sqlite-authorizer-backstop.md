# ADR 0001: SQLite authorizer backstop for the SELECT-only gateway

- **Status:** accepted
- **Date:** 2026-10-18
- **Context:** the text-to-SQL planner runs generated SELECTs through
  `contractops.views.run_readonly`, which enforced SEC-SELECT-01/02/03 by
  inspecting the query string.

## The bypass class

String-matching a query is inherently fragile. During standardization of a
sibling repo, a real bypass was confirmed: `... LIMIT 100000 -- x` returned
36,864 rows because the gateway trusted the query's own LIMIT (it only
appended one when no `LIMIT` keyword was present). The same family includes:

- **Raw table references** -- `SELECT * FROM contracts` sailed through; the
  old SEC-SELECT-03 never checked *which* tables were named.
- **Comma joins** -- `FROM v_contract_risk, contracts` mixes an allowed view
  with a raw table.
- **Quoted identifiers** -- `FROM "sqlite_master"` (or `[x]`, `` `x` ``)
  defeats naive name matching.
- **Comment whitespace** -- `FROM/**/contracts` breaks token-based parsing
  that doesn't strip comments first.
- **LIMIT smuggling** -- `LIMIT n OFFSET m`, `LIMIT m, n`, or a LIMIT inside
  a subquery all defeat "append LIMIT if missing".

## Decision

Defense in depth, two layers, both in the gateway path:

1. **FROM/JOIN allowlist (text layer).** After stripping string literals and
   SQL comments and unquoting identifiers, every table named after FROM or
   JOIN (including comma-separated lists) must be one of the four published
   views. Anything else raises `GatewayError(SEC-SELECT-03)`.
2. **SQLite authorizer backstop** (`contractops/authz.py`). Every planner
   query runs inside `views_only(...)`, which installs
   `conn.set_authorizer()`: only SELECT + READ (+ SQL functions) are allowed;
   writes, DDL, PRAGMA, ATTACH, and `sqlite_master` reads are denied, raising
   `sqlite3.DatabaseError`, mapped to SEC-SELECT-03.
3. **Fetch-time row cap.** The gateway uses `cursor.fetchmany(MAX_ROWS + 1)`
   and truncates. The query's LIMIT is never trusted. `fetchall()` is never
   called on planner queries.

### Why the authorizer permits the views' backing tables

SQLite expands a view into its base tables during preparation, and the
authorizer sees those base-table reads (verified empirically). Denying them
would break the views themselves. So the authorizer allows the four views
*plus* their backing tables, and raw-table references in query text are
blocked by layer 1. The authorizer's unique value is blocking everything
layer 1 cannot see: writes, DDL, PRAGMAs, ATTACH, and schema reads.

### Engine reads

The clause scorer and renewal prioritizer read via direct cursors on fixed
internal SQL, never through the planner gateway -- so the fetch cap cannot
silently drop rows they need. No change required; verified by inspection.

## Consequences

- `run_readonly` now rejects any query naming non-view tables, including the
  previously-allowed `SELECT ... FROM contracts` pattern (one existing test
  updated to use `v_contract_risk`).
- The `high_risk_clauses` text-to-SQL template was rewritten to join
  `v_clause_risk` to `v_contract_risk` instead of the raw `_contract_risk`
  table (same result, views only).
- PII scrubber extended: phone now matches `(555) 123-4567`, `+1 (555)
  123-4567`, `555.123.4567` (via `(?<!\w)` instead of `\b`, which failed on
  a leading paren); SSN pattern kept strict 3-2-4 so dates like `2026-10-18`
  are never redacted.
- Regression tests: `tests/test_gateway_backstop.py` (19 tests, one per
  bypass above).
