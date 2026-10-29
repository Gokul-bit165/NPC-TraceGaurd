"""API workflow tests against a freshly seeded database."""
import json

H = {"x-role": "analyst", "x-user": "Test Analyst"}
ADMIN = {"x-role": "admin", "x-user": "Test Admin"}


def case_by_scenario(client, key):
    items = client.get("/api/cases?limit=200", headers=H).json()["items"]
    return next(c for c in items if c["scenario"] == key)


def test_health_and_overview(client):
    assert client.get("/api/health").json()["status"] == "ok"
    o = client.get("/api/overview", headers=H).json()
    assert o["kpis"]["emails_analyzed"] > 100 and o["triage"]["cases_opened"] > 0
    assert 0 < o["triage"]["review_share"] < 0.2


def test_roles(client):
    # user without X-User-Id gets 400 (not 403 – users ARE allowed but must identify)
    assert client.get("/api/cases", headers={"x-role": "user"}).status_code == 400
    assert client.get("/api/cases", headers={"x-role": "nonsense"}).status_code == 400
    assert client.put("/api/config", json={"overrides": {}}, headers=H).status_code == 403


def test_critical_case_detail(client):
    c = case_by_scenario(client, "phish_takeover")
    assert c["band"] == "critical"
    d = client.get(f"/api/cases/{c['id']}", headers=H).json()
    assert d["formula"].startswith("S = min(100")
    assert sum(1 for e in d["ledger"] if e["points"] > 0) >= 6
    assert d["narrative"]["validated"] and "[X_EMAIL_THEN_LOGIN]" in d["narrative"]["summary"]
    assert d["email"]["auth"]["dmarc"] == "fail" and d["actions"][0]["code"] == "block_sender_domain"
    assert "Lagos" in d["user_alert"]


def test_password_reset_waits_for_session_revocation(client):
    c = case_by_scenario(client, "phish_takeover")
    acts = {a["code"]: a for a in client.get(f"/api/cases/{c['id']}", headers=H).json()["actions"]}
    r = client.post(f"/api/cases/{c['id']}/actions/{acts['reset_password']['id']}", json={"decision": "approve"}, headers=H)
    assert r.status_code == 409 and "token" in r.json()["detail"]
    assert client.post(f"/api/cases/{c['id']}/actions/{acts['revoke_sessions']['id']}", json={"decision": "approve"}, headers=H).status_code == 200
    assert client.post(f"/api/cases/{c['id']}/actions/{acts['reset_password']['id']}", json={"decision": "approve"}, headers=H).status_code == 200
    again = client.post(f"/api/cases/{c['id']}/actions/{acts['reset_password']['id']}", json={"decision": "approve"}, headers=H)
    assert again.status_code == 409                     # cannot decide twice
    audit = client.get(f"/api/audit?case_id={c['id']}", headers=H).json()
    events = [a["event"] for a in audit]
    assert events.count("action_approved") == 2 and "case_opened" in events


def test_all_actions_decided_resolves_case(client):
    c = case_by_scenario(client, "student_trip")          # Medium: reversible steps only, auto-run
    d = client.get(f"/api/cases/{c['id']}", headers=H).json()
    assert all(a["status"] == "auto_done" for a in d["actions"])
    h = case_by_scenario(client, "impossible_travel")     # High: needs approval
    d = client.get(f"/api/cases/{h['id']}", headers=H).json()
    for a in d["actions"]:
        assert client.post(f"/api/cases/{h['id']}/actions/{a['id']}", json={"decision": "approve"}, headers=H).status_code == 200
    assert client.get(f"/api/cases/{h['id']}", headers=H).json()["case"]["status"] == "resolved"


def test_medium_case_alerts_the_student(client):
    c = case_by_scenario(client, "student_trip")
    uid = c["user"]["id"]
    r = client.get("/api/me/alerts", headers={"x-role": "user", "x-user-id": uid, "x-user": "Nikhil"}).json()
    assert r["items"] and "Singapore" in r["items"][0]["body"]
    nid = r["items"][0]["id"]
    assert client.post(f"/api/me/alerts/{nid}/ack", json={"answer": "it_was_me"}, headers={"x-role": "user", "x-user-id": uid}).status_code == 200
    # another student cannot answer it
    assert client.post(f"/api/me/alerts/{nid}/ack", json={"answer": "not_me"}, headers={"x-role": "user", "x-user-id": "someone-else"}).status_code == 404


def test_false_positive_feedback_closes_and_is_counted(client):
    c = case_by_scenario(client, "spoofed_harmless")
    assert client.post(f"/api/cases/{c['id']}/verdict", json={"verdict": "false_positive"}, headers=H).status_code == 200
    rep = client.get("/api/reports", headers=H).json()
    assert rep["verdicts"]["false_positive"] == 1
    assert client.get(f"/api/cases/{c['id']}", headers=H).json()["case"]["status"] == "false_positive"


def test_email_analyze_upload_and_typed(client, scenarios):
    em = next(s for s in scenarios if s.key == "prompt_injection").emails[0]
    r = client.post("/api/emails/analyze", files={"file": ("x.eml", em.raw.encode(), "message/rfc822")}, headers=H).json()
    assert r["band"] == "high" and r["probability"] > 0.5
    assert any(e["code"] == "E_PROMPT_INJECTION" for e in r["ledger"])
    assert r["email"]["hidden_text_found"] and r["narrative"]["validated"]
    t = client.post("/api/emails/analyze", data={"sender": "helpdesk@kestrel-support.com", "subject": "Verify your account within 24 hours",
                                                 "body": "Sign in at http://kestrel-support.com/login to confirm your password"}, headers=H).json()
    assert any("not checked" in x for x in t["not_evaluated"]) and t["score"] > 0 and t["saved_case_id"] is None
    assert client.post("/api/emails/analyze", data={}, headers=H).status_code == 422


def test_email_save_requires_known_recipient(client):
    r = client.post("/api/emails/analyze", data={"sender": "a@b.example", "subject": "hi", "save": "true"}, headers=H)
    assert r.status_code == 422


def test_login_filters(client):
    r = client.get("/api/logins?country=RU", headers=H).json()
    assert r["total"] > 0 and all(i["country"] == "RU" for i in r["items"])
    r = client.get("/api/logins?q=aisha&success=true&unusual_only=true", headers=H).json()
    assert r["items"] and r["items"][0]["user"]["name"] == "Aisha Khan"
    hist = client.get("/api/users/aisha.khan@kestrel.edu/logins", headers=H).json()
    assert "IN" in hist["baseline"]["countries"] and hist["items"]


def test_ingest_login_stream_opens_a_case(client):
    batch = [{"user_id": "u-rohan", "ts": "2026-01-15T14:30:00Z", "ip": "198.51.100.9", "country": "BR", "city": "Sao Paulo", "device": "Linux|Firefox", "success": True}]
    assert client.post("/api/ingest/logins", json=batch, headers=H).status_code == 403          # analysts cannot push events
    r = client.post("/api/ingest/logins", json=batch, headers=ADMIN)
    assert r.status_code == 200 and r.json()["stored"] == 1


def test_config_simulate_and_guarded_save(client):
    ok = client.post("/api/config/simulate", json={"overrides": {}}, headers=H).json()
    assert ok["all_ok"]
    bad = client.post("/api/config/simulate", json={"overrides": {"login": {"signals": {"new_country": {"points": 0, "group": "location"}, "impossible_travel": {"points": 5, "group": "location"}}}}}, headers=H).json()
    assert not bad["all_ok"]
    assert client.post("/api/config/simulate", json={"overrides": {"bands": {"high": [70, 79]}}}, headers=H).status_code == 422
    blocked = client.put("/api/config", json={"overrides": {"login": {"signals": {"impossible_travel": {"points": 5, "group": "location"}}}}}, headers=ADMIN)
    assert blocked.status_code == 409


def test_report_download(client):
    c = case_by_scenario(client, "phish_takeover")
    r = client.get(f"/api/cases/{c['id']}/report", headers=H)
    assert r.status_code == 200 and "Evidence ledger" in r.text and "attachment" in r.headers["content-disposition"]


def test_campaigns_group_recipients(client):
    camps = client.get("/api/campaigns", headers=H).json()
    assert camps and camps[0]["recipients"] >= 3
