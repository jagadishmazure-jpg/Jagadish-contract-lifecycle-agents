"""SQLite authorizer backstop for the SELECT-only gateway.

The gateway's text checks (SEC-SELECT-01/02) inspect the query string, which
is inherently fragile: exotic SQL (comment tricks, quoted identifiers, comma
joins) can evade string matching. This module adds a second, independent
enforcement layer using SQLite's own authorizer callback.

What the authorizer enforces (inside ``views_only``):
  - Only SELECT statements may run (SQLITE_SELECT).
  - Only READs are allowed, and only on the allowed views plus the base
    tables that back them; scalar/aggregate SQL functions (COUNT, SUM,
    ROUND, ...) are allowed. Everything else -- INSERT/UPDATE/DELETE,
    DDL, PRAGMA, ATTACH/DETACH, and reads of sqlite_master -- is denied.

Why the backing tables are allowed: SQLite expands a view into its base
tables during query preparation, so denying READ on a backing table would
break the view itself (verified empirically: the authorizer sees the base
table read when a view is queried). Raw-table access in the *query text* is
blocked one layer up by the gateway's FROM/JOIN allowlist (SEC-SELECT-03);
the authorizer is the backstop for anything that check misses, and the sole
enforcer for non-read operations.

Denied operations raise ``sqlite3.DatabaseError`` ("... is prohibited"),
which the gateway maps to SEC-SELECT-03.
"""
from __future__ import annotations

import contextlib
import sqlite3


@contextlib.contextmanager
def views_only(con: sqlite3.Connection, allowed_views,
               backing_tables=()):
    """Install a restrictive SQLite authorizer for the block duration.

    Args:
        con: the SQLite connection (the authorizer is per-connection).
        allowed_views: view names the query text is restricted to.
        backing_tables: base tables those views expand to (required --
            without them the views themselves stop working).

    The authorizer is cleared on exit (``set_authorizer(None)``), so DDL
    and engine reads outside the block are unaffected.
    """
    readable = set(allowed_views) | set(backing_tables)

    def _authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION:
            # Scalar/aggregate functions (COUNT, SUM, ROUND, date(...)).
            # They cannot write; writes are denied by action type below.
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            # arg1 is the table/view name being read.
            if arg1 in readable:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_DENY

    con.set_authorizer(_authorizer)
    try:
        yield
    finally:
        con.set_authorizer(None)
