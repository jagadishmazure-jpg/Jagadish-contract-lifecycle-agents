"""Read-only views over the CLM telemetry plus a SELECT-only query gateway.

Security rules (cited in errors and README):
  SEC-SELECT-01 — only SELECT statements are allowed.
  SEC-SELECT-02 — write keywords are rejected even when the literal-strip
                  scan sees them outside string literals.
  SEC-SELECT-03 — queries may only reference the four published views
                  (FROM/JOIN allowlist). The SQLite authorizer
                  (contractops.authz) enforces this independently: a base
                  table is readable only on behalf of a published view,
                  never when named directly, and sqlite_master, writes and
                  DDL are always denied. Rows are capped at MAX_ROWS at
                  fetch time.
"""
from __future__ import annotations

import re
import sqlite3

from . import clauses as clause_mod
from . import renewals as renewal_mod
from .authz import views_only
from .telemetry import REF_TODAY

MAX_ROWS = 100

ALLOWED_VIEWS = (
    "v_contract_risk",
    "v_upcoming_renewals",
    "v_obligation_status",
    "v_clause_risk",
)

_WRITE_KEYWORDS = ("insert", "update", "delete", "drop", "alter", "create",
                   "replace", "truncate", "grant", "revoke", "attach", "detach")
_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_FROM_JOIN_RE = re.compile(r"\b(?:from|join)\b", re.IGNORECASE)
_CLAUSE_END_RE = re.compile(
    r"\b(where|group\s+by|order\s+by|having|limit|offset|union|except|"
    r"intersect|join|left|right|inner|outer|cross|full|natural|on|using|"
    r"window|values)\b", re.IGNORECASE)


def create_views(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute("DROP VIEW IF EXISTS v_contract_risk")
    cur.execute("DROP VIEW IF EXISTS v_upcoming_renewals")
    cur.execute("DROP VIEW IF EXISTS v_obligation_status")
    cur.execute("DROP VIEW IF EXISTS v_clause_risk")

    # Materialised inputs: contract risk comes from the clause scorer.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS _contract_risk ("
        "contract_id TEXT PRIMARY KEY, risk_score REAL, risk_band TEXT)"
    )
    cur.execute("DELETE FROM _contract_risk")
    rows = cur.execute(
        "SELECT contract_id, annual_value FROM contracts").fetchall()
    for (cid, _value) in rows:
        clauses = cur.execute(
            "SELECT clause_id, clause_type, text FROM clauses "
            "WHERE contract_id = ?", (cid,)).fetchall()
        score = clause_mod.contract_risk_score(
            [{"clause_id": c[0], "clause_type": c[1], "text": c[2]}
             for c in clauses])
        cur.execute(
            "INSERT INTO _contract_risk VALUES (?,?,?)",
            (cid, score, clause_mod.risk_band(score)),
        )

    cur.execute(
        "CREATE TABLE IF NOT EXISTS _renewal_priority ("
        "contract_id TEXT PRIMARY KEY, days_to_expiry INTEGER, "
        "priority_score REAL, expiry_date TEXT)"
    )
    cur.execute("DELETE FROM _renewal_priority")
    for (cid, value) in rows:
        ren = cur.execute(
            "SELECT renewal_id, expiry_date, notice_days, auto_renew, decision "
            "FROM renewals WHERE contract_id = ? "
            "ORDER BY expiry_date LIMIT 1", (cid,)).fetchone()
        if ren is None:
            continue
        risk = cur.execute(
            "SELECT risk_score FROM _contract_risk WHERE contract_id = ?",
            (cid,)).fetchone()[0]
        pr = renewal_mod.priority(
            annual_value=value,
            risk_score=risk,
            expiry_date=ren["expiry_date"],
            ref_date=REF_TODAY.isoformat(),
        )
        days = (datetime_date(ren["expiry_date"])
                - datetime_date(REF_TODAY.isoformat())).days
        cur.execute(
            "INSERT INTO _renewal_priority VALUES (?,?,?,?)",
            (cid, days, pr["priority_score"], ren["expiry_date"]),
        )

    cur.execute(
        """
        CREATE VIEW v_contract_risk AS
        SELECT c.contract_id, p.name AS counterparty, c.type, c.status,
               c.annual_value, r.risk_score, r.risk_band
        FROM contracts c
        JOIN counterparties p ON p.counterparty_id = c.counterparty_id
        JOIN _contract_risk r ON r.contract_id = c.contract_id
        """
    )
    cur.execute(
        """
        CREATE VIEW v_upcoming_renewals AS
        SELECT c.contract_id, p.name AS counterparty, rp.expiry_date,
               rp.days_to_expiry, rp.priority_score, c.annual_value
        FROM contracts c
        JOIN counterparties p ON p.counterparty_id = c.counterparty_id
        JOIN _renewal_priority rp ON rp.contract_id = c.contract_id
        WHERE c.status = 'active'
        """
    )
    cur.execute(
        """
        CREATE VIEW v_obligation_status AS
        SELECT o.obligation_id, o.contract_id, o.kind, o.description,
               o.due_date, o.status,
               CASE
                 WHEN o.status = 'met' THEN 'met'
                 WHEN o.due_date < '%s' THEN 'overdue'
                 WHEN o.due_date <= date('%s', '+14 days') THEN 'due_soon'
                 ELSE 'on_track'
               END AS health
        FROM obligations o
        """ % (REF_TODAY.isoformat(), REF_TODAY.isoformat())
    )
    cur.execute(
        """
        CREATE VIEW v_clause_risk AS
        SELECT cl.clause_id, cl.contract_id, cl.clause_type,
               cl.text AS clause_text
        FROM clauses cl
        """
    )
    con.commit()


def datetime_date(s: str):
    import datetime
    return datetime.date.fromisoformat(s)


class GatewayError(Exception):
    """Raised when a query violates a SEC-SELECT-* rule."""


def _first_keyword(sql: str) -> str:
    stripped = sql.strip()
    # drop leading SQL comments
    while stripped.startswith("--"):
        nl = stripped.find("\n")
        stripped = stripped[nl + 1:].strip() if nl != -1 else ""
    m = re.match(r"([A-Za-z]+)", stripped)
    return m.group(1).upper() if m else ""


def _unquote(name: str) -> str:
    name = name.strip()
    if len(name) >= 2:
        if name[0] == '"' and name[-1] == '"':
            return name[1:-1]
        if name[0] == "[" and name[-1] == "]":
            return name[1:-1]
        if name[0] == "`" and name[-1] == "`":
            return name[1:-1]
    return name


def _referenced_tables(sql: str) -> set:
    """Return table names referenced after FROM/JOIN in the query.

    String literals and SQL comments are stripped first (so
    ``FROM/**/contracts`` and ``FROM "contracts"`` are still seen), then
    each comma-separated item contributes its first token (the table name;
    aliases are ignored). Subquery parentheses yield no table token; the
    inner FROM is matched separately by the same scan.
    """
    text = _COMMENT_RE.sub(" ", _LITERAL_RE.sub(" ", sql))
    tables = set()
    for m in _FROM_JOIN_RE.finditer(text):
        rest = text[m.end():]
        end = _CLAUSE_END_RE.search(rest)
        segment = rest[:end.start()] if end else rest
        # A subquery or parenthesised join: skip the '(' token; inner
        # FROMs are visited by the outer finditer loop.
        for item in segment.split(","):
            token = item.strip().split()
            if not token:
                continue
            raw = token[0].rstrip(";").lstrip("(").rstrip(")")
            # "(SELECT ..." is a subquery (its FROM is scanned separately);
            # "(contracts)" is a parenthesised table and is still a table.
            if not raw or raw.lower() in ("select", "with", "values"):
                continue
            tables.add(_unquote(raw))
    return tables


def run_readonly(con: sqlite3.Connection, sql: str):
    """Run a SELECT-only query over the allowed views.

    Raises GatewayError on rule violations. Enforcement is two layers:
    text checks (SEC-SELECT-01/02/03) plus the SQLite authorizer backstop
    (contractops.authz). The row cap is applied at fetch time with
    fetchmany(MAX_ROWS + 1) -- the query's own LIMIT is never trusted.
    """
    if _first_keyword(sql) != "SELECT":
        raise GatewayError("SEC-SELECT-01: only SELECT statements are allowed")
    scrubbed = _LITERAL_RE.sub(" ", sql)
    lowered = scrubbed.lower()
    for kw in _WRITE_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", lowered):
            raise GatewayError(
                f"SEC-SELECT-02: write keyword '{kw}' is not allowed")
    bad = sorted(t for t in _referenced_tables(sql) if t not in ALLOWED_VIEWS)
    if bad:
        raise GatewayError(
            f"SEC-SELECT-03: query references non-view tables: {bad}")
    cur = con.cursor()
    try:
        with views_only(con, ALLOWED_VIEWS) as denied:
            cur.execute(sql)
            cols = [d[0] for d in (cur.description or [])]
            rows = cur.fetchmany(MAX_ROWS)
    except sqlite3.DatabaseError as e:
        if denied:
            raise GatewayError(
                f"SEC-SELECT-03: denied by database authorizer: {sorted(set(denied))}") from e
        raise GatewayError(f"SEC-SELECT-01: query failed ({e})") from e
    return cols, rows
