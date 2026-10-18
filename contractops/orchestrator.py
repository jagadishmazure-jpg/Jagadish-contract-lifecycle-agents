"""ReAct-style orchestrator with multi-intent fan-out.

A question is mapped to intents; each intent fans out to the right tool
(text-to-SQL views, clause scorer, renewal prioritizer, SOP RAG, regulatory
signal). Gated actions (contract approvals, high-risk clause acceptances)
require a ConfirmationGate before anything is recorded. Every turn is
audited.
"""
from __future__ import annotations

from . import clauses as clause_mod
from . import renewals as renewal_mod
from .audit import AuditLog
from .escalation import ConfirmationGate, escalate, gate_required, tier_for
from .feedback import FeedbackStore
from .regsignal import FakeRegSignal, LiveRegSignal, SignalGap
from .sop_rag import answer as rag_answer
from .telemetry import seed_db
from .text2sql import EscalationNeeded, to_sql
from .views import GatewayError, create_views, run_readonly


class Orchestrator:
    def __init__(self, use_live_signal: bool = False):
        self.con = seed_db()
        create_views(self.con)
        self.audit = AuditLog()
        self.feedback = FeedbackStore()
        self.signal = LiveRegSignal() if use_live_signal else FakeRegSignal()
        self._turn = 0

    # ---- tools ---------------------------------------------------------
    def ask_sql(self, question: str) -> dict:
        intent, sql = to_sql(question)
        try:
            cols, rows = run_readonly(self.con, sql)
        except GatewayError as e:
            raise EscalationNeeded(str(e)) from e
        return {"intent": intent, "columns": cols,
                "rows": [tuple(r) for r in rows], "sql": sql}

    def score_contract(self, contract_id: str) -> dict:
        cur = self.con.cursor()
        rows = cur.execute(
            "SELECT clause_id, clause_type, text FROM clauses "
            "WHERE contract_id = ?", (contract_id,)).fetchall()
        if not rows:
            raise EscalationNeeded(f"no clauses for {contract_id}")
        scored = [
            {"clause_id": r[0], **clause_mod.score_clause(r[1], r[2])}
            for r in rows
        ]
        total = clause_mod.contract_risk_score(
            [{"clause_type": r[1], "text": r[2]} for r in rows])
        return {"contract_id": contract_id, "contract_score": total,
                "band": clause_mod.risk_band(total), "clauses": scored}

    def rank_renewals(self, limit: int = 5) -> dict:
        cur = self.con.cursor()
        rows = cur.execute(
            "SELECT contract_id, annual_value FROM contracts "
            "WHERE status = 'active'").fetchall()
        ranked = []
        for (cid, value) in rows:
            # Lapsed renewals stay in the pipeline: SOP-02 treats a lapsed
            # auto-renewal as a control failure, not a closed item.
            ren = cur.execute(
                "SELECT expiry_date, decision, notice_days FROM renewals "
                "WHERE contract_id = ? AND decision IN ('undecided', 'lapsed') "
                "ORDER BY expiry_date LIMIT 1",
                (cid,)).fetchone()
            if ren is None:
                continue
            risk = cur.execute(
                "SELECT risk_score FROM _contract_risk WHERE contract_id = ?",
                (cid,)).fetchone()[0]
            from .telemetry import REF_TODAY
            pr = renewal_mod.priority(value, risk, ren[0],
                                      REF_TODAY.isoformat())
            entry = {"contract_id": cid, **pr, "decision": ren[1],
                     "past_notice_deadline": pr["days_to_expiry"] < ren[2]}
            if ren[1] == "lapsed":
                entry["flag"] = "lapsed renewal: control failure (SOP-02)"
            ranked.append(entry)
        ranked.sort(key=lambda r: -r["priority_score"])
        return {"renewals": ranked[:limit]}

    def ask_sop(self, question: str) -> dict:
        return rag_answer(question)

    def reg_update(self, topic: str | None = None) -> dict:
        try:
            items = self.signal.latest(topic)
        except SignalGap as e:
            return {"available": False, "gap": str(e), "items": []}
        return {"available": True, "gap": None, "items": items}

    # ---- gated actions --------------------------------------------------
    def approve_contract(self, contract_id: str,
                         approver=None) -> dict:
        action = "contract_approval"
        tier = tier_for(action)
        result = {"contract_id": contract_id, "tier": tier}
        if gate_required(action):
            gate = ConfirmationGate(f"approve-{contract_id}",
                                    approver=approver)
            ok = gate.request()
            result["gate"] = {"name": gate.name, "approved": ok}
            if not ok:
                escalate(action, f"gate denied for {contract_id}",
                         self.audit)
                result["status"] = "denied"
                self.audit.append("contract_approval_denied", result)
                return result
        result["status"] = "approved"
        self.audit.append("contract_approved", result)
        return result

    def accept_high_risk_clause(self, clause_id: str,
                                approver=None) -> dict:
        action = "high_risk_clause_accept"
        gate = ConfirmationGate(f"accept-{clause_id}", approver=approver)
        ok = gate.request()
        result = {"clause_id": clause_id, "tier": tier_for(action),
                  "approved": ok}
        self.audit.append("high_risk_clause_decision", result)
        if not ok:
            escalate(action, f"gate denied for {clause_id}", self.audit)
        return result

    # ---- main loop ------------------------------------------------------
    def run(self, question: str, session_id: str = "demo") -> dict:
        self._turn += 1
        turn_id = f"t{self._turn}"
        steps = []
        try:
            steps.append(("sql", self.ask_sql(question)))
        except EscalationNeeded as e:
            steps.append(("sql_escalated", {"reason": str(e)}))
        steps.append(("sop", self.ask_sop(question)))
        self.audit.append("turn", {"session_id": session_id,
                                   "turn_id": turn_id,
                                   "question": question,
                                   "steps": [s[0] for s in steps]})
        return {"session_id": session_id, "turn_id": turn_id,
                "steps": steps}
