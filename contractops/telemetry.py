"""Synthetic contract-lifecycle telemetry on SQLite.

Everything is fictional and deterministic (seed 42). A fixed reference date
``REF_TODAY`` keeps expiry/overdue math stable across runs.
"""
from __future__ import annotations

import datetime
import random
import sqlite3

REF_TODAY = datetime.date(2026, 10, 18)
SEED = 42


def _d(days: int) -> str:
    return (REF_TODAY + datetime.timedelta(days=days)).isoformat()


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    return con


def seed(con: sqlite3.Connection) -> None:
    rng = random.Random(SEED)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE counterparties (
            counterparty_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            industry TEXT NOT NULL,
            risk_tier TEXT NOT NULL
        );
        CREATE TABLE contracts (
            contract_id TEXT PRIMARY KEY,
            counterparty_id TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            annual_value REAL NOT NULL,
            FOREIGN KEY (counterparty_id) REFERENCES counterparties(counterparty_id)
        );
        CREATE TABLE clauses (
            clause_id TEXT PRIMARY KEY,
            contract_id TEXT NOT NULL,
            clause_type TEXT NOT NULL,
            text TEXT NOT NULL,
            FOREIGN KEY (contract_id) REFERENCES contracts(contract_id)
        );
        CREATE TABLE obligations (
            obligation_id TEXT PRIMARY KEY,
            contract_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            description TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (contract_id) REFERENCES contracts(contract_id)
        );
        CREATE TABLE renewals (
            renewal_id TEXT PRIMARY KEY,
            contract_id TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            notice_days INTEGER NOT NULL,
            auto_renew INTEGER NOT NULL,
            decision TEXT NOT NULL,
            FOREIGN KEY (contract_id) REFERENCES contracts(contract_id)
        );
        """
    )

    counterparties = [
        ("CP-01", "Tervanne Logistics", "logistics", "medium"),
        ("CP-02", "Sorrelbeck Foods", "food", "low"),
        ("CP-03", "Veyrin Health", "healthcare", "high"),
        ("CP-04", "Ondrel Manufacturing", "manufacturing", "medium"),
        ("CP-05", "Harborlight Retail", "retail", "low"),
        ("CP-06", "Corvane Telecom", "telecom", "medium"),
    ]
    cur.executemany("INSERT INTO counterparties VALUES (?,?,?,?)", counterparties)

    # 12 contracts. CTR-1001 is the high-risk anchor (one-sided indemnity,
    # weak liability cap, auto-renewal without a proper opt-out notice).
    contracts = [
        ("CTR-1001", "CP-01", "MSA", "pending_approval", _d(-320), _d(45), 480000.0),
        ("CTR-1002", "CP-02", "SOW", "active", _d(-200), _d(165), 120000.0),
        ("CTR-1003", "CP-03", "MSA", "active", _d(-400), _d(-20), 950000.0),
        ("CTR-1004", "CP-04", "License", "active", _d(-90), _d(275), 210000.0),
        ("CTR-1005", "CP-05", "MSA", "active", _d(-150), _d(215), 340000.0),
        ("CTR-1006", "CP-06", "NDA", "active", _d(-60), _d(305), 25000.0),
        # CTR-1007: renewal anchor — expires in 21 days, no decision recorded.
        ("CTR-1007", "CP-02", "SOW", "active", _d(-344), _d(21), 175000.0),
        ("CTR-1008", "CP-04", "MSA", "active", _d(-500), _d(230), 620000.0),
        ("CTR-1009", "CP-01", "Lease", "active", _d(-100), _d(630), 88000.0),
        ("CTR-1010", "CP-03", "NDA", "expired", _d(-500), _d(-135), 15000.0),
        ("CTR-1011", "CP-05", "SOW", "pending_approval", _d(-30), _d(335), 96000.0),
        ("CTR-1012", "CP-06", "License", "active", _d(-120), _d(60), 145000.0),
    ]
    cur.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?)", contracts)

    clauses = [
        # CTR-1001: deliberately risky clause set (anchors).
        ("CL-1001-A", "CTR-1001", "liability_cap",
         "Supplier liability is capped at one month of fees, one-sided in Supplier's favour."),
        ("CL-1001-B", "CTR-1001", "indemnity",
         "Customer indemnifies Supplier against all claims without cap or carve-outs."),
        ("CL-1001-C", "CTR-1001", "auto_renewal",
         "Agreement auto-renews for successive 12-month terms; opt-out requires 15 days notice."),
        ("CL-1001-D", "CTR-1001", "termination",
         "Termination for cause only, with a 10-day cure period; no termination for convenience."),
        # CTR-1002: clean-ish set.
        ("CL-1002-A", "CTR-1002", "liability_cap",
         "Mutual liability cap at 12 months of fees, excluding willful misconduct."),
        ("CL-1002-B", "CTR-1002", "payment_terms",
         "Payment terms Net-30 from invoice date."),
        ("CL-1002-C", "CTR-1002", "confidentiality",
         "Mutual confidentiality for 3 years post-termination."),
        # CTR-1003: expired MSA with a weak termination clause.
        ("CL-1003-A", "CTR-1003", "termination",
         "Termination for cause only, with a 5-day cure period."),
        ("CL-1003-B", "CTR-1003", "governing_law",
         "Governing law: the courts of North Ruritania."),
        # CTR-1004..CTR-1008: mixed bag.
        ("CL-1004-A", "CTR-1004", "payment_terms",
         "Payment terms Net-90 from invoice date."),
        ("CL-1005-A", "CTR-1005", "auto_renewal",
         "Auto-renews annually; either party may opt out with 90 days written notice."),
        ("CL-1007-A", "CTR-1007", "liability_cap",
         "Mutual liability cap at 6 months of fees."),
        ("CL-1007-B", "CTR-1007", "indemnity",
         "Mutual indemnity for third-party IP claims, capped at fees paid."),
        ("CL-1008-A", "CTR-1008", "liability_cap",
         "Mutual liability cap at 12 months of fees."),
        ("CL-1008-B", "CTR-1008", "termination",
         "Either party may terminate for convenience with 120 days notice."),
        # CTR-1011: pending approval, payment terms too long.
        ("CL-1011-A", "CTR-1011", "payment_terms",
         "Payment terms Net-75 from invoice date."),
        ("CL-1011-B", "CTR-1011", "confidentiality",
         "One-sided confidentiality in favour of the counterparty, 5 years."),
        # CTR-1012: auto-renewal with short notice.
        ("CL-1012-A", "CTR-1012", "auto_renewal",
         "Auto-renews for 12-month terms; cancellation requires 20 days notice."),
    ]
    cur.executemany("INSERT INTO clauses VALUES (?,?,?,?)", clauses)

    obligations = [
        # OBL-01: overdue anchor (due 12 days ago, still open).
        ("OBL-01", "CTR-1001", "payment", "Q3 license true-up payment", _d(-12), "open"),
        ("OBL-02", "CTR-1001", "report", "Quarterly security attestation", _d(9), "open"),
        ("OBL-03", "CTR-1002", "sla", "Monthly uptime report 99.5%", _d(4), "open"),
        ("OBL-04", "CTR-1003", "payment", "Final invoice settlement", _d(-40), "open"),
        ("OBL-05", "CTR-1005", "report", "Annual ESG disclosure pack", _d(60), "open"),
        ("OBL-06", "CTR-1007", "sla", "Helpdesk response-time audit", _d(14), "open"),
        ("OBL-07", "CTR-1008", "payment", "Milestone 2 payment", _d(-3), "open"),
        ("OBL-08", "CTR-1004", "report", "License usage true-up", _d(25), "open"),
        ("OBL-09", "CTR-1012", "sla", "Quarterly service review deck", _d(40), "open"),
        ("OBL-10", "CTR-1002", "payment", "SOW phase-2 kickoff fee", _d(-60), "met"),
    ]
    cur.executemany("INSERT INTO obligations VALUES (?,?,?,?,?,?)", obligations)

    renewals = [
        ("REN-01", "CTR-1001", _d(45), 30, 1, "undecided"),
        ("REN-02", "CTR-1007", _d(21), 30, 0, "undecided"),   # anchor: 21 days, no decision
        ("REN-03", "CTR-1003", _d(-20), 60, 1, "lapsed"),
        ("REN-04", "CTR-1012", _d(60), 30, 1, "undecided"),
        ("REN-05", "CTR-1005", _d(215), 90, 1, "undecided"),
        ("REN-06", "CTR-1008", _d(230), 90, 0, "undecided"),
    ]
    cur.executemany("INSERT INTO renewals VALUES (?,?,?,?,?,?)", renewals)

    # A little deterministic jitter in a few values so aggregates aren't trivial.
    _ = rng  # reserved for future jitter; schema is fixed for now.
    con.commit()


def seed_db() -> sqlite3.Connection:
    con = connect()
    seed(con)
    return con
