"""Generates workflow_collect.json: one entry point that collects raw security data, prepares it for TraceGuard and
routes it to the right ingest endpoint.  python n8n/make_collect_workflow.py"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
URL = "={{ ($env.TRACEGUARD_URL || 'http://host.docker.internal:8000') }}"
ADMIN = {"parameters": [{"name": "X-Role", "value": "admin"}, {"name": "X-User", "value": "n8n-collector"}, {"name": "Content-Type", "value": "application/json"}]}

PREPARE = r"""// COLLECT -> PREPARE. Accepts one record, an array, or {logins|events|emails: [...]}.
// Understands TraceGuard-native, Entra / Azure AD sign-in, Google / Okta style fields and raw or structured emails.
const root = $input.first().json;
const body = root.body ?? root;
let list = Array.isArray(body) ? body : [...(body.logins ?? []), ...(body.events ?? []), ...(body.emails ?? [])];
if (!list.length && !Array.isArray(body) && !body.logins && !body.events && !body.emails) list = [body];

const seen = $getWorkflowStaticData("global"); seen.keys = seen.keys || [];
const meta = { received: list.length, logins: 0, emails: 0, duplicates: 0, rejected: [] };
const logins = [], emails = [];

const asBool = (v) => {
  if (typeof v === "boolean") return v;
  const s = String(v ?? "").toLowerCase();
  if (["false", "failure", "failed", "fail", "denied", "0", "error"].includes(s)) return false;
  return true;
};
const bad = (i, why) => meta.rejected.push({ index: i, reason: why });

list.forEach((e, i) => {
  if (!e || typeof e !== "object") return bad(i, "not an object");
  const isEmail = e.raw_eml || e.raw || (e.subject && (e.from || e.text || e.body));
  if (isEmail) {
    const rcpt = String(e.recipient ?? e.to?.address ?? e.to?.value?.[0]?.address ?? (Array.isArray(e.to) ? e.to[0] : e.to) ?? "").replace(/.*<|>.*/g, "").trim().toLowerCase();
    if (!rcpt.includes("@")) return bad(i, "email has no valid recipient");
    let eml = e.raw_eml ?? e.raw;
    if (!eml) {
      const when = new Date(e.date ?? e.ts ?? Date.now()).toUTCString().replace("GMT", "+0000");
      eml = `From: ${e.from ?? "unknown@unknown"}\r\nTo: ${rcpt}\r\nSubject: ${e.subject ?? ""}\r\nDate: ${when}\r\nContent-Type: text/plain\r\n\r\n${e.text ?? e.body ?? ""}\r\n`;
    }
    meta.emails++;
    return emails.push({ recipient: rcpt, raw_eml: String(eml) });
  }
  const user = String(e.user_id ?? e.userPrincipalName ?? e.user ?? e.email ?? e.actor?.alternateId ?? "").trim().toLowerCase();
  if (!user) return bad(i, "login has no user");
  const t = new Date(e.ts ?? e.createdDateTime ?? e.timestamp ?? e.published ?? Date.now());
  if (isNaN(t)) return bad(i, "unparseable timestamp");
  const os = e.deviceDetail?.operatingSystem ?? e.client?.device ?? "";
  const br = e.deviceDetail?.browser ?? e.client?.userAgent?.browser ?? "";
  const device = String(e.device ?? (os || br ? `${os}|${br}` : "")).toLowerCase().replace(/\s+/g, "");
  const ip = String(e.ip ?? e.ipAddress ?? e.client?.ipAddress ?? "").trim();
  const row = {
    user_id: user,
    ts: t.toISOString(),
    ip,
    country: String(e.country ?? e.location?.countryOrRegion ?? e.client?.geographicalContext?.country ?? "").trim().toUpperCase().slice(0, 2),
    city: String(e.city ?? e.location?.city ?? e.client?.geographicalContext?.city ?? "").trim(),
    device,
    success: asBool(e.success ?? (e.status?.errorCode !== undefined ? e.status.errorCode === 0 : undefined) ?? e.outcome?.result),
    is_attack_ip: false
  };
  const key = `${row.user_id}|${row.ts}|${row.ip}`;
  if (seen.keys.includes(key)) { meta.duplicates++; return; }
  seen.keys.push(key); if (seen.keys.length > 5000) seen.keys.splice(0, seen.keys.length - 5000);
  meta.logins++;
  logins.push(row);
});

const out = [];
if (logins.length) out.push({ json: { kind: "logins", batch: logins, meta } });
emails.forEach(m => out.push({ json: { kind: "email", ...m, meta } }));
if (!out.length) out.push({ json: { kind: "none", meta } });
return out;"""

SUMMARY = r"""const meta = $("Prepare & validate").first().json.meta;
const results = $input.all().map(i => i.json).filter(j => j && !j.kind);
const logins = results.filter(r => r.stored !== undefined);
const mails = results.filter(r => r.email_id !== undefined);
return [{ json: {
  ok: true,
  received: meta.received,
  prepared: { logins: meta.logins, emails: meta.emails },
  duplicates_skipped: meta.duplicates,
  rejected: meta.rejected,
  logins_stored: logins.reduce((n, r) => n + r.stored, 0),
  cases_opened: logins.flatMap(r => r.cases ?? []).length + mails.filter(m => m.case_id).length,
  emails_scored: mails.map(m => ({ email_id: m.email_id, score: m.score, band: m.band, case_id: m.case_id }))
} }];"""


def http(name, path, body, pos, qs=None):
    p = {"method": "POST", "url": URL + path, "sendHeaders": True, "headerParameters": ADMIN, "sendBody": True,
         "specifyBody": "json", "jsonBody": body, "options": {}}
    if qs:
        p.update({"sendQuery": True, "queryParameters": {"parameters": qs}})
    return {"parameters": p, "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos, "onError": "continueRegularOutput"}


def code(name, js, pos):
    return {"parameters": {"jsCode": js}, "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}


def rule(kind, key):
    return {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
            "conditions": [{"leftValue": "={{ $json.kind }}", "rightValue": kind, "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"},
            "renameOutput": True, "outputKey": key}


def one(target, idx=0):
    return {"main": [[{"node": target, "type": "main", "index": idx}]]}


nodes = [
    {"parameters": {"httpMethod": "POST", "path": "traceguard-collect", "responseMode": "responseNode", "options": {}}, "name": "Collect (webhook)",
     "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0], "webhookId": "traceguard-collect"},
    code("Prepare & validate", PREPARE, [240, 0]),
    {"parameters": {"rules": {"values": [rule("logins", "logins"), rule("email", "email")]}, "options": {"fallbackOutput": "extra", "renameFallbackOutput": "nothing valid"}},
     "name": "Route by type", "type": "n8n-nodes-base.switch", "typeVersion": 3.2, "position": [480, 0]},
    http("POST /api/ingest/logins", "/api/ingest/logins", "={{ JSON.stringify($json.batch) }}", [740, -120], [{"name": "sync", "value": "true"}]),
    http("POST /api/ingest/email", "/api/ingest/email", "={{ JSON.stringify({recipient: $json.recipient, raw_eml: $json.raw_eml}) }}", [740, 40]),
    {"parameters": {}, "name": "Nothing valid", "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": [740, 200]},
    {"parameters": {"numberInputs": 3}, "name": "Join results", "type": "n8n-nodes-base.merge", "typeVersion": 3, "position": [980, 40]},
    code("Summarize", SUMMARY, [1200, 40]),
    {"parameters": {"respondWith": "firstIncomingItem", "options": {}}, "name": "Respond", "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.1, "position": [1420, 40]},
]
conns = {
    "Collect (webhook)": one("Prepare & validate"),
    "Prepare & validate": one("Route by type"),
    "Route by type": {"main": [[{"node": "POST /api/ingest/logins", "type": "main", "index": 0}],
                               [{"node": "POST /api/ingest/email", "type": "main", "index": 0}],
                               [{"node": "Nothing valid", "type": "main", "index": 0}]]},
    "POST /api/ingest/logins": one("Join results", 0),
    "POST /api/ingest/email": one("Join results", 1),
    "Nothing valid": one("Join results", 2),
    "Join results": one("Summarize"),
    "Summarize": one("Respond"),
}
(OUT / "workflow_collect.json").write_text(json.dumps({"name": "TraceGuard collect and prepare", "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"}}, indent=2), encoding="utf-8")
print("wrote workflow_collect.json")
