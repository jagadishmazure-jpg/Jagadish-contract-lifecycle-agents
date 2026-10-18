"""Regression tests for the SQLite gateway backstop (issue #8).

Each test targets one concrete bypass of the old string-matching gateway:
comma joins, quoted identifiers, comment-whitespace, LIMIT smuggling, and
raw table references. The authorizer (contractops.authz) is also exercised
directly, plus the extended phone/SSN PII patterns.
"""
import sqlite3

import pytest

from contractops.authz import views_only
from contractops.pii import PIIScrubber
from contractops.telemetry import seed_db
from contractops.views import (ALLOWED_VIEWS, GatewayError, _VIEW_BACKING_TABLES,
                               create_views, run_readonly, MAX_ROWS)


@pytest.fixture()
def db():
    con = seed_db()
    create_views(con)
    return con


# ---- FROM/JOIN allowlist (SEC-SELECT-03) ----------------------------------
def test_backstop_denies_comma_join_with_raw_table(db):
    with pytest.raises(GatewayError, match="SEC-SELECT-03"):
        run_readonly(db, "SELECT * FROM v_contract_risk, contracts")


def test_backstop_denies_quoted_sqlite_master(db):
    with pytest.raises(GatewayError, match="SEC-SELECT-03"):
        run_readonly(db, 'SELECT * FROM "sqlite_master"')


def test_backstop_denies_comment_whitespace_from(db):
    with pytest.raises(GatewayError, match="SEC-SELECT-03"):
        run_readonly(db, "SELECT * FROM/**/contracts")


def test_backstop_denies_raw_base_table(db):
    with pytest.raises(GatewayError, match="SEC-SELECT-03"):
        run_readonly(db, "SELECT * FROM contracts")


def test_backstop_denies_bracket_quoted_table(db):
    with pytest.raises(GatewayError, match="SEC-SELECT-03"):
        run_readonly(db, "SELECT * FROM [contracts]")


# ---- fetch-time row cap ----------------------------------------------------
def _big_query():
    # 12 x 12 cross join = 144 rows without a cap.
    return ("SELECT a.contract_id FROM v_contract_risk a, v_contract_risk b")


def test_backstop_caps_limit_injection_with_comment(db):
    # The old gateway trusted the query's LIMIT: `LIMIT 100000 -- x`
    # returned every row (36,864 in the sibling repo). Now fetchmany caps.
    cols, rows = run_readonly(db, _big_query() + " LIMIT 100000 -- x")
    assert len(rows) == MAX_ROWS


def test_backstop_caps_limit_offset(db):
    cols, rows = run_readonly(db, _big_query() + " LIMIT 200 OFFSET 10")
    assert len(rows) == MAX_ROWS


def test_backstop_allows_legit_small_query(db):
    cols, rows = run_readonly(
        db, "SELECT contract_id FROM v_contract_risk LIMIT 3")
    assert len(rows) == 3


# ---- authorizer backstop (independent of text checks) ----------------------
def test_authorizer_denies_write(db):
    with views_only(db, ALLOWED_VIEWS, _VIEW_BACKING_TABLES):
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("DELETE FROM contracts")


def test_authorizer_denies_ddl(db):
    with views_only(db, ALLOWED_VIEWS, _VIEW_BACKING_TABLES):
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("DROP TABLE contracts")


def test_authorizer_denies_sqlite_master(db):
    with views_only(db, ALLOWED_VIEWS, _VIEW_BACKING_TABLES):
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("SELECT name FROM sqlite_master").fetchall()


def test_authorizer_allows_view_reads(db):
    with views_only(db, ALLOWED_VIEWS, _VIEW_BACKING_TABLES):
        n = db.execute("SELECT COUNT(*) FROM v_contract_risk").fetchone()[0]
    assert n == 12


def test_authorizer_is_cleared_after_block(db):
    with views_only(db, ALLOWED_VIEWS, _VIEW_BACKING_TABLES):
        pass
    # DDL works again outside the block (create_views uses it).
    db.execute("CREATE TABLE IF NOT EXISTS _probe (x TEXT)")
    db.execute("DROP TABLE _probe")


# ---- PII: phone formats and dates ------------------------------------------
def test_pii_redacts_parenthesised_phone():
    out, counts = PIIScrubber().scrub("call (555) 123-4567 today")
    assert "[REDACTED-PHONE]" in out and counts["phone"] == 1


def test_pii_redacts_plus1_phone():
    out, counts = PIIScrubber().scrub("call +1 (555) 123-4567 today")
    assert "[REDACTED-PHONE]" in out and counts["phone"] == 1


def test_pii_redacts_dotted_phone():
    out, counts = PIIScrubber().scrub("call 555.123.4567 today")
    assert "[REDACTED-PHONE]" in out and counts["phone"] == 1


def test_pii_redacts_dashed_phone():
    out, counts = PIIScrubber().scrub("call 555-123-4567 today")
    assert "[REDACTED-PHONE]" in out and counts["phone"] == 1


def test_pii_redacts_ssn():
    out, counts = PIIScrubber().scrub("ssn 123-45-6789 on file")
    assert "[REDACTED-SSN]" in out and counts["ssn"] == 1


def test_pii_keeps_dates_intact():
    text = "renewal due 2026-10-18, signed 2026-01-05"
    out, counts = PIIScrubber().scrub(text)
    assert out == text
    assert counts == {"email": 0, "phone": 0, "ssn": 0}
