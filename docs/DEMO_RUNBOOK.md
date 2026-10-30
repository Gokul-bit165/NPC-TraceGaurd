# TraceGuard demo runbook

## Start
    docker compose -f docker-compose.yml -f docker-compose.n8n.yml up -d --build
App http://localhost:8000 (seeds 38 scenario cases on start, ~1 min). n8n http://localhost:5678.
Narrator needs `backend/.env` (see `backend/.env.example`); without a key the app still works.

## Data modes
Default (docker-compose.yml): `TRACEGUARD_DATA=real` - no synthetic data; only real mail from n8n, kept across restarts (volume `tg-data-real`).
Set `TRACEGUARD_DATA=demo` to get the 38 synthetic scenarios (resets on start) for testing the correlation demo.

## Login logs (simulated)
No identity provider is connected, so there are no real sign-in logs. In real mode, use **Simulate logins** (Suspicious Logins page, or "Simulate a follow-up login" on a mail's investigation) to generate believable sign-ins for your real mailbox: normal, takeover (follows the chosen real email), impossible travel, credential stuffing. They are scored like real events and the Logins page says they are simulated. "Clear simulated logins" removes them. Each case page opens with a **Recommended decision**: the call, confidence, strongest evidence, options, ordered steps with the reason for each, and what would change the answer. Steps that need approval are never run automatically.

## n8n workflows (import from `n8n/`, or run `python n8n/make_*.py` to regenerate)
| File | Purpose |
|---|---|
| workflow_collect.json | POST /webhook/traceguard-collect: any login/email payload -> cleaned, de-duplicated -> TraceGuard |
| workflow_logins.json | Login webhook -> /api/ingest/logins |
| workflow_gmail.json | Gmail (read-only) -> /api/ingest/email. Runs every 5 min on its own (publish it) and from the Mailbox page's Sync now button. Needs a Gmail OAuth2 credential in n8n |
| workflow_alerts.json | Poll cases, pick new High/Critical; replace the last node with Slack/Teams/email |

## Pages
Dashboard, Mailbox (fetched mail, auto-refreshing; click a mail for its investigation: evidence, SPF/DKIM/DMARC, links, wording check, steps), Suspicious Logins, AI Investigation, Incident Response, Reports & Analytics.

## Live demo (2 minutes)
1. `python n8n/send_demo_events.py` - a phishing email, then a foreign login 40 minutes later, via n8n.
2. Open Cases: Aisha Khan appears Critical (score 100), "Likely account compromise after phishing", correlated.
3. Open the case: evidence, narrative, recommended actions awaiting analyst approval, report.
4. Reports page: campaign and analytics views.

## Model facts (docs/MODEL_REPORT.txt)
Shipped: TF-IDF + logistic regression, `backend/models/text_model.joblib`, needs scikit-learn 1.9.0 (pinned).
Cross-source test: precision 0.84, recall 0.87, false-positive rate 3.9%, AUC 0.976.
Login scoring is rule-based; there is no trained login model. BERT/DistilBERT were benchmark candidates, not shipped.

## Checks
    cd backend && python -m pytest -q      # all pass
    cd frontend && npm run build
