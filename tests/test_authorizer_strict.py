"""Strict, view-aware authorizer (SEC-SELECT-03), tested independently of the text check.

A base-table READ is allowed only when SQLite reports it on behalf of an
allowed view (the authorizer's view-name argument). A READ naming the table
directly, with no view, is denied; sqlite_master is always denied.
"""

import sqlite3

import pytest

from contractops import views
from contractops.authz import views_only

ALLOWED = list(views.ALLOWED_VIEWS)

DIRECT_READS = [
    "SELECT * FROM contracts, v_contract_risk",
    "SELECT * FROM/**/\"contracts\"/**/,/**/v_contract_risk",
    "SELECT * FROM v_contract_risk JOIN (contracts) ON 1 = 1",
    "SELECT * FROM v_contract_risk WHERE EXISTS (SELECT 1 FROM main.[contracts] WHERE contracts.rowid > 0)",
    "SELECT annual_value FROM contracts",
    "SELECT * FROM\"contracts\"\t,\nv_contract_risk",
]
GATEWAY_READS = DIRECT_READS


@pytest.fixture()
def conn():
    from contractops import telemetry
    c = telemetry.seed_db()
    views.create_views(c)
    return c


@pytest.mark.parametrize("sql", DIRECT_READS)
def test_authorizer_denies_direct_base_table_reads(conn, sql):
    with views_only(conn, ALLOWED) as denied:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql).fetchall()
    assert "contracts" in [d.lower() for d in denied]


@pytest.mark.parametrize("sql", GATEWAY_READS)
def test_gateway_denies_direct_reads_with_text_check_disabled(conn, monkeypatch, sql):
    monkeypatch.setattr(views, "_referenced_tables", lambda sql: set())
    with pytest.raises(views.GatewayError, match="SEC-SELECT-03"):
        views.run_readonly(conn, sql)


def test_sqlite_master_is_denied_even_if_listed_as_allowed(conn):
    with views_only(conn, ALLOWED + ["sqlite_master"]):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute('SELECT name FROM "sqlite_master"').fetchall()


def test_load_extension_is_denied(conn):
    with views_only(conn, ALLOWED):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("SELECT load_extension('x') FROM v_contract_risk").fetchall()


@pytest.mark.parametrize("view", ALLOWED)
def test_every_published_view_is_readable(conn, view):
    with views_only(conn, ALLOWED) as denied:
        conn.execute(f"SELECT * FROM {view}").fetchall()
    assert denied == []


def test_view_self_join_is_not_falsely_denied(conn):
    with views_only(conn, ALLOWED) as denied:
        conn.execute("SELECT count(*) FROM v_contract_risk a JOIN v_contract_risk b ON 1 = 1").fetchall()
    assert denied == []


def test_base_column_filter_is_denied_even_in_count(conn):
    # Documented residual: count(*) of a table behind a view reads no column.
    # Any column access (here a WHERE filter) is still denied.
    with views_only(conn, ALLOWED):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("SELECT count(*) FROM contracts WHERE annual_value > 0").fetchall()


# Queries that got past the text check before 2026-10-18 and read the raw table.
@pytest.mark.parametrize("sql", ['SELECT * FROM (contracts)', 'SELECT * FROM v_contract_risk,(contracts)', 'SELECT * FROM v_contract_risk WHERE 1 IN (SELECT 1 FROM (contracts))'])
def test_former_text_bypasses_are_denied(conn, sql):
    with pytest.raises(views.GatewayError, match="SEC-SELECT-03"):
        views.run_readonly(conn, sql)
