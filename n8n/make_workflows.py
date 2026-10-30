"""Generates the three import-ready n8n workflows in this folder.  python n8n/make_workflows.py"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
URL = "={{ ($env.TRACEGUARD_URL || 'http://host.docker.internal:8000') }}"
ADMIN = {"parameters": [{"name": "X-Role", "value": "admin"}, {"name": "X-User", "value": "n8n-connector"}, {"name": "Content-Type", "value": "application/json"}]}


def post(name, path, body, pos, qs=None):
    p = {"method": "POST", "url": URL + path, "sendHeaders": True, "headerParameters": ADMIN, "sendBody": True,
         "specifyBody": "json", "jsonBody": body, "options": {}}
    if qs:
        p.update({"sendQuery": True, "queryParameters": {"parameters": qs}})
    return {"parameters": p, "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos}


def link(a, b):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]}}


LOGIN_MAP = """// Accepts ONE event or an array. Works with Entra / Google / IdP exports (field aliases handled).
const body = $input.first().json.body ?? $input.first().json;
const list = Array.isArray(body) ? body : (body.events ?? [body]);
const out = list.map(e => ({
  user_id: String(e.user_id ?? e.userPrincipalName ?? e.email ?? e.user ?? ""),
  ts: new Date(e.ts ?? e.createdDateTime ?? e.timestamp ?? Date.now()).toISOString(),
  ip: e.ip ?? e.ipAddress ?? "",
  country: e.country ?? e.location?.countryOrRegion ?? "",
  city: e.city ?? e.location?.city ?? "",
  device: String(e.device ?? e.deviceDetail?.operatingSystem ?? "").toLowerCase(),
  success: e.success ?? (e.status?.errorCode === 0) ?? true,
  is_attack_ip: false
})).filter(x => x.user_id);
return [{ json: { batch: out } }];"""

MAIL_MAP = """// The recipient must be a user TraceGuard knows (email or id).
const j = $input.first().json;
const raw = j.raw ?? j.textPlain ?? "";
const to = (j.to?.value?.[0]?.address) ?? (j.to?.text ?? "").replace(/.*<|>.*/g, "");
return [{ json: { recipient: (to || "").trim(), raw_eml: String(raw) } }];"""

ALERTS = """const seen = $getWorkflowStaticData("global"); seen.ids = seen.ids || [];
const items = $input.first().json.items ?? [];
const fresh = items.filter(c => ["high", "critical"].includes(String(c.band).toLowerCase()) && !seen.ids.includes(c.id));
fresh.forEach(c => seen.ids.push(c.id));
return fresh.map(c => ({ json: { text: `TraceGuard ${String(c.band).toUpperCase()} ${c.score}: case #${c.id} for ${c.user?.name}` } }));"""


def save(name, nodes, conns):
    (OUT / name).write_text(json.dumps({"name": name[:-5].replace("_", " "), "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"}}, indent=2), encoding="utf-8")


save("workflow_logins.json", [
    {"parameters": {"httpMethod": "POST", "path": "traceguard-logins", "responseMode": "lastNode", "options": {}}, "name": "Login webhook",
     "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0], "webhookId": "traceguard-logins"},
    {"parameters": {"jsCode": LOGIN_MAP}, "name": "Map to TraceGuard fields", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [240, 0]},
    post("POST /api/ingest/logins", "/api/ingest/logins", "={{ JSON.stringify($json.batch) }}", [480, 0], [{"name": "sync", "value": "true"}])],
    {**link("Login webhook", "Map to TraceGuard fields"), **link("Map to TraceGuard fields", "POST /api/ingest/logins")})

save("workflow_email.json", [
    {"parameters": {"format": "raw", "options": {"customEmailConfig": "[\"UNSEEN\"]"}}, "name": "Mailbox (IMAP)",
     "type": "n8n-nodes-base.emailReadImap", "typeVersion": 2, "position": [0, 0]},
    {"parameters": {"jsCode": MAIL_MAP}, "name": "Build ingest body", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [240, 0]},
    post("POST /api/ingest/email", "/api/ingest/email", "={{ JSON.stringify({recipient: $json.recipient, raw_eml: $json.raw_eml}) }}", [480, 0])],
    {**link("Mailbox (IMAP)", "Build ingest body"), **link("Build ingest body", "POST /api/ingest/email")})

save("workflow_alerts.json", [
    {"parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 1}]}}, "name": "Every minute", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0]},
    {"parameters": {"url": URL + "/api/cases", "sendHeaders": True, "headerParameters": {"parameters": [{"name": "X-Role", "value": "analyst"}, {"name": "X-User", "value": "n8n-connector"}]}, "options": {}},
     "name": "GET /api/cases", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [240, 0]},
    {"parameters": {"jsCode": ALERTS}, "name": "Only new High/Critical", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [480, 0]},
    {"parameters": {}, "name": "Send to Slack / Teams / email (replace this node)", "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": [720, 0]}],
    {**link("Every minute", "GET /api/cases"), **link("GET /api/cases", "Only new High/Critical"), **link("Only new High/Critical", "Send to Slack / Teams / email (replace this node)")})
print("wrote", sorted(p.name for p in OUT.glob("workflow_*.json")))
