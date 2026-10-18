# Implementation guide

## Running it
```bash
python -m pytest tests/ -q        # full suite, offline, stdlib only
python scripts/count_tests.py     # prints the real test total
pip install streamlit              # optional, demo UI only
streamlit run demo/app.py
```

## Wiring a real contract repository
Replace `telemetry.seed_db()` with a loader that reads your CLM export
(contracts, clauses, obligations) into the same five tables. Keep the
clause text verbatim — the scorer keys off it. Keep `REF_TODAY` replaced
by the real "today" once dates are real.

## Tuning the playbook
Edit `RULES` in `contractops/clauses.py`: adjust weights, add clause
types, extend `_check`. Every new rule needs a `CLAUSE-*` ID, a test in
`tests/test_contractops.py`, and a line in `docs/sops/sop-01-clause-playbook.md`.
The contract-band thresholds (20/50) live in `risk_band()`.

## Tuning renewal priority
Weights live in `contractops/renewals.py` (0.40 value / 0.35 risk /
0.25 urgency) with `VALUE_NORM` and `URGENCY_WINDOW_DAYS` as constants.
Recalibrate against your own renewal outcomes before trusting the rank.

## Connecting the regulatory feed
Implement `LiveRegSignal.latest()` against your real source (regulator
RSS, legal-tech API). Keep the `SignalGap` contract: on any failure,
raise `SignalGap` with a human-readable reason — never return guessed
items.

## Production hardening (not built here)
Keyed-HMAC pseudonymisation for counterparty names, PII-aware routing,
prompt-injection tests on the question interface, eval gate in CI with
safety metrics, human approval wired to your identity provider instead of
a callback.
