"""Print the clause-risk scorer, renewal prioritizer and gateway on the seeded data."""
from contractops import clauses
from contractops.orchestrator import Orchestrator
from contractops.views import GatewayError, run_readonly

o = Orchestrator()
rep = o.score_contract("CTR-1001")
print(f"CTR-1001 contract risk {rep['contract_score']} ({rep['band']}):")
for c in rep["clauses"]:
    print(f"  {c['clause_id']} +{c['score']} | {c['breakdown']}")

print("Clause wording checks:")
for ctype, text in (
        ("indemnity", "Mutual indemnity, uncapped."),
        ("liability_cap", "Unlimited liability for Supplier."),
        ("auto_renewal", "Renews annually unless either party gives ninety (90) days' written notice."),
        ("payment_terms", "Payment due 90 days from invoice.")):
    print(f"  {text!r} -> {clauses.score_clause(ctype, text)['breakdown']}")

print("Renewal pipeline (value x risk x urgency; lapsed renewals stay visible):")
for r in o.rank_renewals(5)["renewals"]:
    flags = [f for f in (r.get("flag"), "past notice deadline" if r["past_notice_deadline"] else None) if f]
    print(f"  {r['contract_id']} {r['priority_score']} ({r['days_to_expiry']}d, {r['decision']})"
          + (f" [{'; '.join(flags)}]" if flags else ""))

try:
    run_readonly(o.con, "SELECT * FROM (contracts)")
except GatewayError as exc:
    print(f"Gateway: SELECT * FROM (contracts) -> {exc}")
