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

## Branch Workflow

Three branches separate team responsibilities. Always branch off from and PR back into the relevant base branch.

| Branch | Owner | Scope |
|--------|-------|-------|
| `frontend` | Frontend team | `frontend/` — React/Vite UI, components, styles, routing |
| `backend` | Backend & ML team | `backend/app/` — FastAPI routes, engine, scoring logic, ML models |
| `data` | Data team | `backend/data/`, `backend/scripts/`, `backend/config/` — seeds, weights, evaluation scripts |

### Getting started

```bash
# Clone the repo (first time)
git clone <repo-url>
cd TraceGaurd-NPC

# --- Frontend team ---
git checkout frontend
# work inside frontend/
git add frontend/...
git commit -m "feat: ..."
git push origin frontend
# Open a PR: frontend → main

# --- Backend / ML team ---
git checkout backend
# work inside backend/app/
git add backend/app/...
git commit -m "feat: ..."
git push origin backend
# Open a PR: backend → main

# --- Data team ---
git checkout data
# work inside backend/data/, backend/scripts/, backend/config/
git add backend/data/... backend/scripts/... backend/config/...
git commit -m "data: ..."
git push origin data
# Open a PR: data → main
```

### Keeping your branch up to date

```bash
git checkout <your-branch>        # e.g. frontend
git fetch origin
git merge origin/main             # pull in latest merged changes
```

### Rules
- Never commit directly to `main`.
- One PR per feature / fix; request review before merging.
- Run `make test` before opening a PR.

## Response Connectors

TraceGuard provides pluggable response connectors that execute approved actions. The active connector is set via `TRACEGUARD_CONNECTOR`:

| Connector | Mode | Description |
|-----------|------|-------------|
| `log` (default) | Safe / Demo | Records the action in audit logs without calling external systems. |
| `m365` | Real | Executes actions against Microsoft 365 / Entra ID via Microsoft Graph API. |

### Microsoft 365 Setup
Set the following environment variables:
```bash
TRACEGUARD_CONNECTOR=m365
M365_TENANT_ID=<your-tenant-id>
M365_CLIENT_ID=<your-client-id>
M365_CLIENT_SECRET=<your-client-secret>
# Optional: M365_MAILBOX_USER=<test-user-upn>
```
Supported actions:
- **Mail**: Quarantine message (moves to Deleted Items/Junk), purge across mailboxes, block sender domain and link URLs.
- **Identity**: Revoke active sessions / refresh tokens, reset user password, require MFA step-up.

Every action is retry-safe (idempotent), records full results in the audit log, and requires analyst/admin approval before execution.

## Limits
Scenarios are team-written; demo data is synthetic; RBA values are artificial and 15 of 16 takeovers had no baseline.
Data credit: RBA data set, Wiefling et al., CC BY 4.0.
