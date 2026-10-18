"""Regression checks for contractops (synthetic data, deterministic)."""
import sqlite3

import pytest

from contractops import clauses, renewals
from contractops.audit import AuditLog
from contractops.demo_helpers import (clause_report, default_questions,
                                      renewal_pipeline, risk_summary)
from contractops.escalation import (ConfirmationGate, escalate, gate_required,
                                    tier_for)
from contractops.feedback import FeedbackError, FeedbackStore
from contractops.orchestrator import Orchestrator
from contractops.pii import PIIScrubber
from contractops.regsignal import FakeRegSignal, LiveRegSignal, SignalGap
from contractops.sop_rag import answer as rag_answer
from contractops.sop_rag import load_chunks
from contractops.telemetry import REF_TODAY, seed_db
from contractops.text2sql import EscalationNeeded, detect_intent, to_sql
from contractops.views import (GatewayError, create_views, run_readonly,
                               MAX_ROWS)


@pytest.fixture()
def db():
    con = seed_db()
    create_views(con)
    return con


@pytest.fixture()
def orch():
    return Orchestrator()


# ---- telemetry anchors -------------------------------------------------
def test_seed_is_deterministic():
    a = seed_db()
    b = seed_db()
    ca = a.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    cb = b.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    assert ca == cb == 12


def test_reference_date_fixed():
    assert REF_TODAY.isoformat() == "2026-10-18"


def test_high_risk_anchor_contract(db):
    row = db.execute(
        "SELECT risk_band, risk_score FROM v_contract_risk "
        "WHERE contract_id = 'CTR-1001'").fetchone()
    assert row[0] == "high" and row[1] == 100.0


def test_renewal_anchor_21_days(db):
    row = db.execute(
        "SELECT days_to_expiry, priority_score FROM v_upcoming_renewals "
        "WHERE contract_id = 'CTR-1007'").fetchone()
    assert row[0] == 21
    assert row[1] == 36.1


def test_overdue_obligation_anchor(db):
    rows = db.execute(
        "SELECT obligation_id FROM v_obligation_status "
        "WHERE health = 'overdue' ORDER BY obligation_id").fetchall()
    ids = [r[0] for r in rows]
    assert "OBL-01" in ids  # due 12 days ago, still open


# ---- clause scorer ------------------------------------------------------
def test_liability_one_sided_fails():
    r = clauses.score_clause(
        "liability_cap",
        "Supplier liability is capped at one month of fees, one-sided.")
    assert r["score"] == 20 and r["band"] == "medium"
    assert r["failed"][0]["rule_id"] == "CLAUSE-LIAB-01"


def test_liability_mutual_12m_passes():
    r = clauses.score_clause(
        "liability_cap", "Mutual liability cap at 12 months of fees.")
    assert r["score"] == 0 and r["failed"] == []


def test_termination_short_cure_fails():
    r = clauses.score_clause(
        "termination", "Termination for cause only, with a 10-day cure period.")
    assert any(f["rule_id"] == "CLAUSE-TERM-02" for f in r["failed"])


def test_termination_generous_passes():
    r = clauses.score_clause(
        "termination",
        "Either party may terminate for convenience with 120 days notice.")
    assert r["score"] == 0


def test_auto_renewal_short_notice_fails():
    r = clauses.score_clause(
        "auto_renewal",
        "Auto-renews; opt-out requires 15 days notice.")
    assert any(f["rule_id"] == "CLAUSE-RENEW-03" for f in r["failed"])


def test_indemnity_uncapped_fails():
    r = clauses.score_clause(
        "indemnity", "Customer indemnifies Supplier against all claims "
                     "without cap or carve-outs.")
    assert any(f["rule_id"] == "CLAUSE-INDEM-04" for f in r["failed"])


def test_payment_net90_fails():
    r = clauses.score_clause("payment_terms", "Payment terms Net-90.")
    assert any(f["rule_id"] == "CLAUSE-PAY-05" for f in r["failed"])


def test_governing_law_unapproved_fails():
    r = clauses.score_clause(
        "governing_law", "Governing law: the courts of North Ruritania.")
    assert any(f["rule_id"] == "CLAUSE-GOV-06" for f in r["failed"])


def test_confidentiality_one_sided_fails():
    r = clauses.score_clause(
        "confidentiality", "One-sided confidentiality, 5 years.")
    assert any(f["rule_id"] == "CLAUSE-CONF-07" for f in r["failed"])


def test_breakdown_names_every_rule():
    r = clauses.score_clause(
        "indemnity", "Mutual indemnity for IP claims, capped at fees paid.")
    assert "CLAUSE-INDEM-04" in r["breakdown"]
    assert "[pass]" in r["breakdown"]


def test_contract_score_sums_and_caps():
    many = [{"clause_type": "indemnity",
             "text": "without cap, one-sided indemnity"}] * 5
    assert clauses.contract_risk_score(many) == 100.0


def test_contract_score_no_clauses_is_zero():
    assert clauses.contract_risk_score([]) == 0.0


def test_risk_bands():
    assert clauses.risk_band(0) == "low"
    assert clauses.risk_band(19.9) == "low"
    assert clauses.risk_band(20) == "medium"
    assert clauses.risk_band(49.9) == "medium"
    assert clauses.risk_band(50) == "high"


# ---- renewal prioritizer -------------------------------------------------
def test_priority_math():
    pr = renewals.priority(500000, 50, "2026-11-17", "2026-10-18")
    # value 0.5*0.4=0.2, risk 0.5*0.35=0.175, urgency (1-30/180)=0.833*0.25
    assert pr["priority_score"] == pytest.approx(58.3, abs=0.1)
    assert pr["days_to_expiry"] == 30


def test_expired_is_max_urgency():
    pr = renewals.priority(100000, 0, "2026-10-01", "2026-10-18")
    assert pr["days_to_expiry"] < 0
    assert "urgency 1.000" in pr["breakdown"]


def test_far_future_has_no_urgency():
    pr = renewals.priority(100000, 0, "2027-10-18", "2026-10-18")
    assert "urgency 0.000" in pr["breakdown"]


def test_renewal_ranking_anchor_first(orch):
    top = orch.rank_renewals(5)["renewals"][0]
    assert top["contract_id"] == "CTR-1007"


# ---- gateway security ------------------------------------------------------
def test_gateway_rejects_non_select(db):
    with pytest.raises(GatewayError, match="SEC-SELECT-01"):
        run_readonly(db, "DELETE FROM contracts")


def test_gateway_rejects_comment_prefixed_injection(db):
    with pytest.raises(GatewayError, match="SEC-SELECT-01"):
        run_readonly(db, "-- sneaky\nDROP TABLE contracts")


def test_gateway_rejects_write_keyword_outside_literal(db):
    with pytest.raises(GatewayError, match="SEC-SELECT-02"):
        run_readonly(db, "SELECT * FROM contracts; UPDATE contracts SET x=1")


def test_gateway_allows_write_word_inside_literal(db):
    cols, rows = run_readonly(
        db, "SELECT contract_id FROM v_contract_risk "
            "WHERE counterparty = 'delete me'")
    assert cols == ["contract_id"]  # no false positive from the literal


def test_gateway_enforces_row_cap(db):
    cols, rows = run_readonly(db, "SELECT contract_id FROM v_contract_risk")
    assert len(rows) <= MAX_ROWS


def test_gateway_allows_plain_select(db):
    cols, rows = run_readonly(
        db, "SELECT contract_id FROM v_contract_risk LIMIT 3")
    assert len(rows) == 3


# ---- text2sql ---------------------------------------------------------------
@pytest.mark.parametrize("q,intent", [
    ("Which contracts are high risk?", "contracts_by_risk"),
    ("Which renewals expire within 30 days?", "upcoming_renewals"),
    ("What obligations are overdue?", "obligation_compliance"),
    ("Show me the riskiest clauses", "high_risk_clauses"),
    ("What is our counterparty exposure?", "counterparty_exposure"),
])
def test_intent_detection(q, intent):
    assert detect_intent(q) == intent


def test_unknown_question_escalates():
    with pytest.raises(EscalationNeeded):
        detect_intent("What is the weather on Mars?")


def test_risk_band_filter_in_sql():
    intent, sql = to_sql("Which contracts are high risk?")
    assert intent == "contracts_by_risk" and "'high'" in sql


def test_simplified_retry_drops_band():
    intent, sql = to_sql("contracts by risk please")
    assert intent == "contracts_by_risk" and "WHERE risk_band" not in sql


def test_renewal_sql_has_priority_order():
    intent, sql = to_sql("renewals expiring in 45 days")
    assert "45" in sql and "priority_score DESC" in sql


# ---- SOP RAG ------------------------------------------------------------------
def test_rag_cites_playbook():
    chunks = load_chunks()
    res = rag_answer("What does the clause playbook say about indemnity?",
                     chunks)
    assert res["found"] is True
    assert any("sop-01-clause-playbook.md" in c for c in res["citations"])


def test_rag_not_found_is_explicit():
    chunks = load_chunks()
    res = rag_answer("quantum cryptography key rotation policy", chunks)
    assert res["found"] is False
    assert res["citations"] == []


def test_rag_skips_title_only_chunks(tmp_path):
    md = tmp_path / "sop-x.md"
    md.write_text("## Empty section\n\n## Real section\n\n" +
                  "Auto-renewal needs sixty days notice, always in writing, "
                  "with a calendar reminder set at twice the notice period.")
    from contractops.sop_rag import load_chunks as lc
    chunks = lc(tmp_path)
    assert all(len(c["text"].split()) > 4 for c in chunks)
    res = rag_answer("auto-renewal notice period", chunks)
    assert res["found"] is True


# ---- regulatory signal ----------------------------------------------------------
def test_fake_signal_seeded():
    sig = FakeRegSignal()
    items = sig.latest()
    assert len(items) == 2
    assert {i["topic"] for i in items} == {"data-retention", "auto-renewal"}


def test_fake_signal_topic_filter():
    sig = FakeRegSignal()
    assert [i["id"] for i in sig.latest("auto-renewal")] == ["REG-2026-021"]


def test_live_signal_reports_gap():
    with pytest.raises(SignalGap, match="not connected"):
        LiveRegSignal().latest()


# ---- escalation -------------------------------------------------------------------
def test_tier_policy():
    assert tier_for("contract_approval") == "T3"
    assert gate_required("contract_approval") is True
    assert gate_required("clause_review") is False


def test_gate_approves_and_denies():
    assert ConfirmationGate("g1", approver=lambda: True).request() is True
    assert ConfirmationGate("g2", approver=lambda: False).request() is False


def test_gate_without_approver_denies():
    assert ConfirmationGate("g3").request() is False


def test_gate_exception_denies():
    def boom():
        raise RuntimeError("idp down")
    assert ConfirmationGate("g4", approver=boom).request() is False


def test_escalate_record_shape():
    rec = escalate("contract_approval", "needs counsel")
    assert rec["tier"] == "T3" and rec["gate_required"] is True


# ---- audit --------------------------------------------------------------------------
def test_audit_chain_verifies():
    log = AuditLog()
    log.append("a", {"x": 1})
    log.append("b", {"x": 2})
    assert log.verify() is True


def test_audit_tamper_detected():
    log = AuditLog()
    log.append("a", {"x": 1})
    log.entries[0]["payload"]["x"] = 999
    assert log.verify() is False


# ---- PII + feedback -------------------------------------------------------------------
def test_pii_scrubber_redacts():
    scrub = PIIScrubber()
    clean, counts = scrub.scrub(
        "Contact jane@northgate.example or 555-123-4567, SSN 123-45-6789.")
    assert "jane@northgate.example" not in clean
    assert "555-123-4567" not in clean
    assert "123-45-6789" not in clean
    assert counts == {"email": 1, "phone": 1, "ssn": 1}


def test_feedback_stores_scrubbed_text():
    store = FeedbackStore()
    rec = store.add("correction", "Call me at 555-123-4567 please",
                    "s1", "t1")
    assert "555-123-4567" not in rec["text"]
    assert rec["redactions"]["phone"] == 1
    assert rec["session_id"] == "s1" and rec["turn_id"] == "t1"


def test_feedback_rejects_bad_kind():
    with pytest.raises(FeedbackError):
        FeedbackStore().add("shrug", "fine", "s1", "t1")


def test_feedback_rejects_empty_text():
    with pytest.raises(FeedbackError):
        FeedbackStore().add("thumbs_up", "   ", "s1", "t1")


# ---- orchestrator -----------------------------------------------------------------------
def test_orchestrator_sql_step(orch):
    out = orch.ask_sql("Which contracts are high risk?")
    assert out["intent"] == "contracts_by_risk"
    assert any(r[0] == "CTR-1001" for r in out["rows"])


def test_orchestrator_score_contract(orch):
    rep = orch.score_contract("CTR-1001")
    assert rep["band"] == "high"
    assert len(rep["clauses"]) == 4
    assert all("CLAUSE-" in c["breakdown"] for c in rep["clauses"])


def test_orchestrator_run_audits_turn(orch):
    before = len(orch.audit.entries)
    res = orch.run("What obligations are overdue?", session_id="s9")
    assert res["session_id"] == "s9"
    assert len(orch.audit.entries) == before + 1
    assert orch.audit.verify() is True


def test_orchestrator_gated_approval_denied_without_approver(orch):
    res = orch.approve_contract("CTR-1001")
    assert res["status"] == "denied"
    assert res["gate"]["approved"] is False


def test_orchestrator_live_signal_gap():
    orch = Orchestrator(use_live_signal=True)
    res = orch.reg_update()
    assert res["available"] is False and res["items"] == []


# ---- demo helpers -------------------------------------------------------------------------
def test_demo_risk_summary():
    rows = risk_summary()
    assert any(r["contract_id"] == "CTR-1001" and r["band"] == "high"
               for r in rows)


def test_demo_renewal_pipeline():
    pipe = renewal_pipeline(3)
    assert pipe[0]["contract_id"] == "CTR-1007"
    assert len(pipe) == 3


def test_demo_clause_report():
    rep = clause_report("CTR-1001")
    assert rep["contract_score"] == 100.0


def test_demo_default_questions():
    qs = default_questions()
    assert len(qs) >= 4 and all(isinstance(q, str) for q in qs)
