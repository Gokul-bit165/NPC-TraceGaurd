"""Send a phish-then-foreign-login pair for the live demo.

    python n8n/send_demo_events.py            # login goes through the n8n webhook (http://localhost:5678)
    python n8n/send_demo_events.py --direct   # straight to TraceGuard, no n8n
The app must be seeded: the recipient has to be a user TraceGuard knows.
"""
import argparse
import json
import urllib.request
from datetime import datetime, timedelta, timezone

ap = argparse.ArgumentParser()
ap.add_argument("--direct", action="store_true")
ap.add_argument("--app", default="http://localhost:8000")
ap.add_argument("--n8n", default="http://localhost:5678")
ap.add_argument("--user", default="u-aisha")
ap.add_argument("--email", default="aisha.khan@kestrel.edu")
a = ap.parse_args()
H = {"Content-Type": "application/json", "X-Role": "admin", "X-User": "demo-sender"}


def post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body).encode(), headers=H, method="POST")
    with urllib.request.urlopen(r, timeout=60) as x:
        return x.status, x.read().decode()[:300]


now = datetime.now(timezone.utc)
when = (now - timedelta(minutes=40)).strftime("%a, %d %b %Y %H:%M:%S +0000")
eml = (f"From: IT Support <helpdesk@kestrel-support.com>\r\nTo: {a.email}\r\nSubject: Password expires today\r\nDate: {when}\r\n"
       "Content-Type: text/plain\r\n\r\nDear user, your password expires in 24 hours. Verify your username and password now at "
       "http://kestrel-edu-login.top/auth or your account will be closed.\r\n")
print("email ->", post(a.app + "/api/ingest/email", {"recipient": a.email, "raw_eml": eml}))
login = {"user_id": a.user, "ts": now.isoformat(), "ip": "105.112.141.53", "country": "NG", "city": "Lagos", "device": "linux|firefox", "success": True}
if a.direct:
    print("login ->", post(a.app + "/api/ingest/logins?sync=true", [login]))
else:
    print("login ->", post(a.n8n + "/webhook/traceguard-logins", login))
