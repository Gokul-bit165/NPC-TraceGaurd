# TraceGuard

Correlates phishing-email evidence with login evidence into one explainable, graded incident (TCS PS 1.3).

## Run
```
make setup && make web && make seed && make run     # http://localhost:8000
# or: docker compose up --build
make test
```
Use the "View as" switch (top right) for Administrator, Analyst, Student.

## How it scores
Email score E and login score L (0-100, signed evidence ledger, grouped caps). Case score
`S = min(100, max(E,L) + 0.5*min(E,L))` only when a suspicious login follows a risky email within 72 h and both sides are
at least Medium. An email alone stops at High (79). Bands: Low 0-29, Medium 30-59, High 60-79, Critical 80-100.
Weights: `backend/config/weights.yaml`; `POST /api/config/simulate` previews the effect on all scenarios.

## Real data
- `python backend/scripts/fetch_rba_head.py` pulls real RBA rows from the GitHub release when Zenodo is blocked.
- `scripts/evaluate_rba.py --src data/rba_head.csv` and `scripts/benchmark.py` write `models/*.json`.
- `scripts/train_text_model.py --csv phishing_email.csv` trains on the Kaggle data (not run in the build sandbox: Kaggle was unreachable). The bundled model is trained on synthetic template text.

## Limits
Scenarios are team-written; demo data is synthetic; RBA values are artificial and 15 of 16 takeovers had no baseline; actions use a log-only connector (no real mail/IdP calls); demo roles are header-based, not security.
Data credit: RBA data set, Wiefling et al., CC BY 4.0.
