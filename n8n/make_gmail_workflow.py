"""Generates workflow_gmail.json: Gmail (read-only) -> rebuild an .eml -> TraceGuard /api/ingest/email.
Stage C/D of the Gmail-only plan, run from n8n.  python n8n/make_gmail_workflow.py"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
URL = "={{ ($env.TRACEGUARD_URL || 'http://host.docker.internal:8000') }}"
ADMIN = {"parameters": [{"name": "X-Role", "value": "admin"}, {"name": "X-User", "value": "n8n-gmail"}, {"name": "Content-Type", "value": "application/json"}]}

# Gmail node (simple=false) returns id, threadId, internalDate and payload{headers, parts}. Rebuild an RFC822 message so
# TraceGuard's parse_eml() sees the same headers (From, Subject, Authentication-Results, Received-SPF ...) and body.
BUILD_EML = r"""// One item in = one Gmail message. Output: {recipient, raw_eml, message_id} or nothing (duplicate / unusable).
// Handles the Gmail node's flattened output (headers{}, text, html) and the raw Gmail shape (payload.headers[]).
const seen = $getWorkflowStaticData("global"); seen.ids = seen.ids || [];
const b64 = (s) => Buffer.from(String(s || "").replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8");
const strip = (name, v) => { v = String(v ?? ""); const p = name.toLowerCase() + ":"; return v.toLowerCase().startsWith(p) ? v.slice(p.length).trim() : v.trim(); };
const out = [];
for (const it of $input.all()) {
  const m = it.json;
  const id = m.id;
  if (!id || seen.ids.includes(id)) continue;
  const hv = {};
  if (m.headers && !Array.isArray(m.headers)) for (const [k, v] of Object.entries(m.headers)) hv[k.toLowerCase()] = strip(k, Array.isArray(v) ? v.join(" ") : v);
  for (const x of m.payload?.headers ?? []) hv[x.name.toLowerCase()] = x.value;
  const h = (n) => String(hv[n.toLowerCase()] ?? "").replace(/\r?\n\s*/g, " ");
  const keep = ["From", "To", "Reply-To", "Subject", "Message-ID", "Authentication-Results", "Received-SPF", "DKIM-Signature", "Return-Path", "Delivered-To"];
  const lines = keep.filter(n => h(n)).map(n => `${n}: ${h(n)}`);
  if (!hv["subject"] && m.subject) lines.push(`Subject: ${m.subject}`);
  if (!hv["from"] && m.from?.text) lines.push(`From: ${m.from.text}`);
  const when = new Date(h("Date") || m.date || Number(m.internalDate) || Date.now());
  lines.push(`Date: ${(isNaN(when) ? new Date() : when).toUTCString().replace("GMT", "+0000")}`);

  let plain = m.text ?? "", html = m.html ?? "";
  if (!plain && !html && m.payload) {
    const walk = (p) => { if (!p) return; if (p.mimeType === "text/plain" && p.body?.data) plain += b64(p.body.data); else if (p.mimeType === "text/html" && p.body?.data) html += b64(p.body.data); (p.parts ?? []).forEach(walk); };
    walk(m.payload);
  }
  plain = plain || m.snippet || "";
  let ctype, body;
  if (plain && html) {
    const bd = "tgb" + id;
    ctype = `multipart/alternative; boundary="${bd}"`;
    body = `--${bd}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n${plain}\r\n--${bd}\r\nContent-Type: text/html; charset=utf-8\r\n\r\n${html}\r\n--${bd}--\r\n`;
  } else if (html) { ctype = "text/html; charset=utf-8"; body = html + "\r\n"; }
  else { ctype = "text/plain; charset=utf-8"; body = plain + "\r\n"; }

  const rcpt = (h("Delivered-To") || m.to?.value?.[0]?.address || h("To")).replace(/.*<|>.*/g, "").split(",")[0].trim().toLowerCase();
  if (!rcpt.includes("@")) continue;
  seen.ids.push(id); if (seen.ids.length > 2000) seen.ids.splice(0, seen.ids.length - 2000);
  out.push({ json: { recipient: rcpt, message_id: id, subject: h("Subject") || m.subject || "", from: h("From"),
    raw_eml: lines.join("\r\n") + `\r\nContent-Type: ${ctype}\r\n\r\n${body}` } });
}
return out;"""

REPORT = r"""const rows = $input.all().map(i => i.json);
const built = $("Build .eml").all().map(i => i.json);
return [{ json: {
  fetched: built.length,
  analysed: rows.filter(r => r.email_id).length,
  suspicious: rows.filter(r => (r.score ?? 0) >= 50).length,
  cases: rows.filter(r => r.case_id).map(r => r.case_id),
  failed: rows.filter(r => r.error).length
} }];"""


def code(name, js, pos):
    return {"parameters": {"jsCode": js}, "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}


def one(target):
    return {"main": [[{"node": target, "type": "main", "index": 0}]]}


nodes = [
    {"parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, "name": "Every 5 minutes",
     "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, -80]},
    {"parameters": {}, "name": "Sync Now (manual)", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 80]},
    # TraceGuard's "Sync now" button posts here; the reply is the Sync report.
    {"parameters": {"httpMethod": "POST", "path": "traceguard-gmail-sync", "responseMode": "lastNode", "options": {}}, "name": "Sync Now (from TraceGuard)",
     "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 240], "webhookId": "traceguard-gmail-sync"},
    # Attach a Gmail OAuth2 credential (scope gmail.readonly) to this node in the n8n UI.
    {"parameters": {"resource": "message", "operation": "getAll", "returnAll": False, "limit": 20, "simple": False,
                    "filters": {"q": "newer_than:1d in:inbox"}, "options": {}},
     "name": "Gmail: latest inbox (read-only)", "type": "n8n-nodes-base.gmail", "typeVersion": 2.1, "position": [240, 0]},
    code("Build .eml", BUILD_EML, [480, 0]),
    {"parameters": {"method": "POST", "url": URL + "/api/ingest/email", "sendHeaders": True, "headerParameters": ADMIN, "sendBody": True,
                    "specifyBody": "json", "jsonBody": "={{ JSON.stringify({recipient: $json.recipient, raw_eml: $json.raw_eml}) }}", "options": {}},
     "name": "POST /api/ingest/email", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [720, 0], "onError": "continueRegularOutput"},
    code("Sync report", REPORT, [960, 0]),
]
conns = {
    "Every 5 minutes": one("Gmail: latest inbox (read-only)"),
    "Sync Now (manual)": one("Gmail: latest inbox (read-only)"),
    "Sync Now (from TraceGuard)": one("Gmail: latest inbox (read-only)"),
    "Gmail: latest inbox (read-only)": one("Build .eml"),
    "Build .eml": one("POST /api/ingest/email"),
    "POST /api/ingest/email": one("Sync report"),
}
(OUT / "workflow_gmail.json").write_text(json.dumps({"name": "TraceGuard Gmail sync", "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"}}, indent=2), encoding="utf-8")
print("wrote workflow_gmail.json")
