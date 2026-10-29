"""Graded response playbook.

Reversible steps for Low and Medium run without approval; anything that blocks a domain or locks a user
out needs an analyst. Order inside Critical matters: sessions and tokens are revoked before the password
is reset, because a still-valid token can keep an attacker signed in after the reset.

`connector` names the integration an enterprise deployment would call (mail gateway, identity provider,
DNS filter). This build ships a log-only connector: approving an action records who decided what and
when, and marks it done; it does not call a real mail or identity system.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from .types import CaseResult


@dataclass
class Action:
    code: str
    label: str
    detail: str
    order: int
    reversible: bool
    requires_approval: bool
    connector: str
    depends_on: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _has(result: CaseResult, prefix: str, min_points: int = 1) -> bool:
    return any(e.code.startswith(prefix) and e.points >= min_points for e in result.ledger)


def recommend(result: CaseResult, campaign_size: int = 1) -> list[Action]:
    em = result.email_score >= 30
    login_susp = result.login_score >= 30 and result.suspicious_login is not None and result.suspicious_login.get("success")
    acts: list[Action] = []
    n = 0

    def add(code, label, detail, reversible, approval, connector, depends=None):
        nonlocal n
        n += 1
        acts.append(Action(code, label, detail, n, reversible, approval, connector, depends))

    band = result.band
    if band == "low":
        add("close_with_note", "Close with a note", "Keep the case in the log as baseline evidence for this user.", True, False, "case.close")
        return acts

    if band == "medium":
        add("send_user_alert", "Send the user a verification alert", "Plain-language message listing what was seen and how to reach IT.", True, False, "notify.user")
        if em:
            add("add_warning_banner", "Add a warning banner to the message", "Reversible: the banner can be removed if the message proves harmless.", True, False, "mail.banner")
        add("watch_account", "Watch the account for further events", "Re-score on every new login and email for 7 days.", True, False, "case.watch")
        return acts

    if band == "high":
        if em:
            add("quarantine_message", "Quarantine the message", "Move it out of the inbox; the user can be given a release path if it is wrong.", True, True, "mail.quarantine")
            if campaign_size > 1:
                add("quarantine_lookalikes", f"Quarantine look-alike messages ({campaign_size} recipients)", "Same sender domain and subject pattern reached other users.", True, True, "mail.quarantine")
        if result.login_score >= 30:
            add("confirm_with_user", "Ask the user to confirm the recent login", "Send the alert and wait for a reply before any lockout.", True, True, "notify.user")
            add("require_mfa_stepup", "Require MFA step-up at next sign-in", "Does not end the session; forces a second factor next time.", True, True, "idp.require_mfa")
        if not acts:
            add("send_user_alert", "Send the user a verification alert", "", True, True, "notify.user")
        return acts

    # critical
    add("block_sender_domain", "Block the sender domain", "Add the sender's registrable domain to the mail and DNS block list.", True, True, "dns.block_domain")
    add("block_urls", "Block the link URLs", "Block every flagged destination at the web filter.", True, True, "dns.block_url")
    add("remove_from_mailboxes", f"Remove the message from all mailboxes ({max(campaign_size, 1)} recipient{'s' if campaign_size != 1 else ''})", "Purge the campaign, not just this user's copy.", False, True, "mail.purge")
    add("revoke_sessions", "Revoke refresh tokens and active sessions", "Do this before the password reset: a live token survives a reset.", True, True, "idp.revoke_sessions")
    add("reset_password", "Reset the password", "Only after sessions are revoked.", False, True, "idp.reset_password", depends="revoke_sessions")
    add("check_mailbox_rules", "Check forwarding rules and app consents", "Attackers often add auto-forwarding or grant OAuth access to keep a foothold.", True, True, "idp.audit_mailbox")
    add("monitor_30_days", "Monitor the account for 30 days", "Re-score every login for a month.", True, True, "case.watch")
    return acts


def user_alert(result: CaseResult, name: str, subject: Optional[str] = None) -> str:
    """Draft the user-facing message from the same facts as the ledger; it cannot claim more than the evidence shows."""
    first = name.split()[0] if name else "there"
    lines = [f"Hi {first},", ""]
    s = result.suspicious_login
    if s and result.login_score >= 30:
        place = ", ".join(x for x in (s.get("city"), s.get("country")) if x) or "an unfamiliar location"
        dev = f" using {s['device']}" if s.get("device") else ""
        lines.append(f"We noticed a sign-in to your campus account from {place}{dev} on {s['ts'][:16].replace('T', ' ')} UTC that does not match how you normally sign in.")
    if result.email_score >= 30 and subject:
        lines.append(f"You also received an email titled \"{subject}\" that our checks flagged as suspicious. Please do not click links in it or reply to it.")
    lines += ["", "If this was you, no action is needed.",
              "If it was not you, change your password now from the official campus sign-in page and contact the IT service desk straight away.",
              "We will never ask for your password by email.", "", "Campus IT Security"]
    return "\n".join(lines)
