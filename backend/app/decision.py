"""Decision support for a case: what to do, how sure we are, why, and what would change the answer.

Everything here is derived from the stored evidence ledger and the proposed actions. It adds no new facts, and it never runs an action:
the analyst still approves every step.
"""
from __future__ import annotations

WHY = {
    "close_with_note": "Nothing here needs action; the note keeps this activity as a baseline for the user.",
    "send_user_alert": "Fast and reversible. The user is the best source of truth about their own sign-in.",
    "add_warning_banner": "Warns the user before they click, and can be removed if the mail proves harmless.",
    "watch_account": "Re-checks every new sign-in and email so a slow attack is not missed.",
    "quarantine_message": "Stops the user (and anyone else) from opening the mail while it is reviewed.",
    "quarantine_lookalikes": "The same campaign reached other mailboxes; one copy is rarely the only one.",
    "confirm_with_user": "A lockout is disruptive, so confirm with the user first.",
    "require_mfa_stepup": "Makes a stolen password useless without ending the user's current session.",
    "block_sender_domain": "Cuts off further mail from the attacker's domain.",
    "block_urls": "Stops anyone who already has the mail from reaching the phishing page.",
    "remove_from_mailboxes": "Removes the whole campaign, not only this user's copy.",
    "revoke_sessions": "A stolen session token survives a password reset, so end sessions first.",
    "reset_password": "The credential may be known to the attacker; do it after sessions are revoked.",
    "check_mailbox_rules": "Attackers add auto-forwarding or app consent to keep access after a reset.",
    "monitor_30_days": "Re-scores every sign-in for a month to catch a return visit.",
}

DECISIONS = {
    "critical": ("contain", "Contain the account now", "rose",
                 "The evidence points to a compromised account. Act before the attacker does more."),
    "high": ("verify", "Verify with the user, then contain if unconfirmed", "orange",
             "There is strong evidence but not proof. Confirm with the user before a lockout."),
    "medium": ("monitor", "Alert the user and monitor", "amber",
               "Something looks off but it has plausible innocent explanations. Keep watching."),
    "low": ("dismiss", "No action needed", "emerald", "Activity matches the user's normal behaviour."),
}


def _confidence(c, res: dict) -> int:
    base = {"critical": 88, "high": 72, "medium": 58, "low": 82}.get(c.band, 60)
    if c.correlated:
        base += 7
    if c.low_confidence:
        base -= 15
    return max(30, min(97, base))


def build(case, res: dict, actions: list, narrative: dict) -> dict:
    code, label, tone, why = DECISIONS.get(case.band, DECISIONS["medium"])
    ledger = [e for e in res.get("ledger", []) if e.get("points", 0) > 0 and e.get("side") in ("email", "login", "correlation")]
    ledger.sort(key=lambda e: -e["points"])
    reasons = [{"code": e["code"], "side": e["side"], "label": e["label"], "detail": e["detail"], "points": e["points"]} for e in ledger[:5]]

    would_change = []
    if case.band != "low":
        if case.login_score >= 30:
            would_change.append("If the user confirms the sign-in was theirs, the login evidence no longer counts and the case drops.")
        if case.email_score >= 30:
            would_change.append("If the mail is a known newsletter or an expected message, mark it a false alarm to teach the review queue.")
        if not case.correlated:
            would_change.append("A suspicious sign-in after this email would link the two and raise the case to critical.")
    else:
        would_change.append("A new suspicious sign-in or email for this user would reopen and re-score the case.")
    for line in res.get("not_evaluated", []):
        would_change.append(f"Not checked: {line}")

    options = [
        {"id": "dismiss", "label": "Dismiss as a false alarm", "effect": "Closes the case and records the verdict.",
         "risk": "If wrong, a real attack goes unhandled.", "recommended": code == "dismiss"},
        {"id": "verify", "label": "Ask the user to confirm", "effect": "Sends a plain-language alert; nothing is locked.",
         "risk": "Slow if the user does not answer.", "recommended": code in ("verify", "monitor")},
        {"id": "contain", "label": "Contain the account", "effect": "Revokes sessions, resets the password, removes the mail.",
         "risk": "Disruptive if it was the real user.", "recommended": code == "contain"},
    ]
    ordered = sorted(actions, key=lambda a: (a.status != "auto_done", a.order, a.id or 0))   # finished steps first, then what is still to do
    steps = [{"order": i, "code": a.code, "label": a.label, "status": a.status, "requires_approval": a.requires_approval,
              "reversible": a.reversible, "why": WHY.get(a.code, a.detail or "")} for i, a in enumerate(ordered, 1)]
    return {
        "decision": {"code": code, "label": label, "tone": tone, "summary": why, "confidence": _confidence(case, res)},
        "reasons": reasons, "options": options, "steps": steps, "would_change": would_change,
        "ai": {"source": narrative.get("source", "template"), "validated": narrative.get("validated", True)},
    }
