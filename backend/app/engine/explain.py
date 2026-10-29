"""Explanation layer. The evidence ledger is the source of truth; narration only paraphrases it.

Default narrator is a deterministic template. An optional language-model narrator can be plugged in with
`register_llm`; it receives only structured ledger JSON (never raw email text), and its output is accepted
only if every cited reason code exists in the ledger and every number it states appears in the evidence.
If it fails either check, or errors, the template is used and the rejection reason is recorded.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from .types import CaseResult

_CODE = re.compile(r"\[([A-Z][A-Z0-9_]+)\]")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")

_llm: Optional[Callable[[dict], str]] = None


def register_llm(fn: Optional[Callable[[dict], str]]) -> None:
    global _llm
    _llm = fn


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(text or "")}


def allowed_numbers(result: CaseResult) -> set[str]:
    nums: set[str] = set()
    for e in result.ledger:
        nums |= _numbers(e.detail) | _numbers(e.label) | {str(abs(e.points)), str(abs(e.raw_points))}
    nums |= {str(result.score), str(result.email_score), str(result.login_score)}
    if result.text_probability is not None:
        nums |= {str(round(result.text_probability * 100))}
    nums |= _numbers(result.extras.get("formula", ""))
    return nums


def validate(text: str, result: CaseResult) -> tuple[bool, str]:
    codes = {e.code for e in result.ledger}
    cited = set(_CODE.findall(text))
    if result.score > 0 and not cited:
        return False, "no reason codes cited"
    unknown = cited - codes
    if unknown:
        return False, f"cites codes not in the evidence: {', '.join(sorted(unknown))}"
    extra = _numbers(_CODE.sub("", text)) - allowed_numbers(result)
    if extra:
        return False, f"states numbers not in the evidence: {', '.join(sorted(extra))}"
    return True, ""


def _top(result: CaseResult, side: Optional[str] = None, k: int = 3):
    items = [e for e in result.ledger if e.points > 0 and e.side in ({side} if side else {"email", "login"})]
    return sorted(items, key=lambda e: -e.points)[:k]


PHRASES = {
    "E_AUTH_FAILURE": "the sender failed authentication", "E_REPLY_TO_MISMATCH": "replies going to a different domain",
    "E_LOOKALIKE_DOMAIN": "a look-alike sender or link domain", "E_LINK_MISMATCH": "a link whose text names a different site than its target",
    "E_RISKY_LINK": "risky link features", "E_URGENCY_LANGUAGE": "urgent language", "E_CREDENTIAL_REQUEST": "a request to sign in or confirm credentials",
    "E_PROMPT_INJECTION": "hidden text addressed to an AI reviewer", "E_TEXT_MODEL": "wording typical of phishing",
    "L_NEW_COUNTRY": "a first login from a new country", "L_NEW_CITY": "a first login from a new city", "L_NEW_IP": "a new IP address",
    "L_IMPOSSIBLE_TRAVEL": "travel between logins that is too fast to be real", "L_NEW_DEVICE": "a device not seen before",
    "L_ODD_HOUR": "an unusual hour", "L_FAILED_BURST": "a burst of failed logins", "L_SUCCESS_AFTER_FAILURES": "a success right after repeated failures",
    "L_MULTI_ACCOUNT_IP": "one IP trying many accounts", "L_ATTACK_IP": "an IP on the attack list",
}


def _phrase(e) -> str:
    return f"{PHRASES.get(e.code, e.label.lower())} [{e.code}]"


def template(result: CaseResult, name: str) -> dict:
    em, lg = _top(result, "email"), _top(result, "login")
    first = name.split()[0] if name else "The user"
    if result.score == 0 or result.band == "low":
        parts = [f"Nothing here suggests an attack on {first}'s account."]
        busy = [e for e in result.ledger if e.points > 0]
        if busy:
            parts.append("Minor signals were seen (" + "; ".join(_phrase(e) for e in busy[:2]) + ") but they are expected for normal activity.")
        headline = "Low risk: no action needed"
    elif result.correlated:
        gap = next((e.detail for e in result.ledger if e.code == "X_EMAIL_THEN_LOGIN"), "")
        parts = [
            f"{first}'s account may have been compromised after a phishing email.",
            "The email looks wrong because of " + "; ".join(_phrase(e) for e in em) + ".",
            "The sign-in looks wrong because of " + "; ".join(_phrase(e) for e in lg) + ".",
            f"The sign-in came after the email ({gap.split(';')[0]}) [X_EMAIL_THEN_LOGIN], which is why the case scores higher than either side alone.",
        ]
        headline = "Likely account compromise after phishing"
    elif em and not lg:
        parts = [f"A message sent to {first} looks like phishing: " + "; ".join(_phrase(e) for e in em) + ".",
                 "No unusual sign-in was seen for this user, so there is no sign the message has worked yet."]
        headline = "Suspicious email, no sign of compromise yet"
    else:
        parts = [f"{first}'s sign-in activity is unusual: " + "; ".join(_phrase(e) for e in lg) + ".",
                 "No suspicious email was found for this user, so the cause may be travel, a new device or an attacker using stolen credentials."]
        headline = "Suspicious sign-in, no related email"
    if result.low_confidence:
        parts.append("Confidence is limited because this user has little sign-in history.")
    ceiling = next((e for e in result.ledger if e.code == "EMAIL_ONLY_CEILING"), None)
    if ceiling:
        parts.append("The score is held at High because an email alone does not reach Critical [EMAIL_ONLY_CEILING].")
    text = " ".join(parts)
    findings = [{"code": e.code, "text": f"{e.label}: {e.detail}", "points": e.points} for e in sorted(
        (e for e in result.ledger if e.points > 0 and e.side in ("email", "login", "correlation")), key=lambda x: -x.points)]
    return {"headline": headline, "summary": text, "findings": findings, "source": "template", "validated": True, "rejected_reason": ""}


def _safe_detail(e) -> str:
    """Ledger detail as shown to a model. Anything that echoes attacker-written text is withheld or reduced to a bounded form."""
    if e.code == "E_PROMPT_INJECTION":
        return "text addressed to an AI reviewer was found in the message (content withheld)"
    if e.code == "E_TEXT_MODEL":
        return e.detail.split(";")[0]                      # keep "probability NN%", drop the echoed terms
    return re.sub(r"[^\w\s.,:;()/%|@\-]", "", e.detail)[:200]


def evidence_payload(result: CaseResult, name: str) -> dict:
    """What a model is allowed to see: structured evidence only. No email body, subject or hidden text."""
    return {
        "user": name, "band": result.band, "score": result.score, "email_score": result.email_score, "login_score": result.login_score,
        "correlated": result.correlated, "low_confidence": result.low_confidence,
        "ledger": [{"code": e.code, "label": e.label, "detail": _safe_detail(e), "points": e.points} for e in result.ledger],
        "instructions": "Write 3 to 5 plain sentences. Cite every claim with its reason code in square brackets, for example [E_AUTH_FAILURE]. "
                        "Use only facts and numbers present in the ledger. Do not add recommendations.",
    }


def narrate(result: CaseResult, name: str) -> dict:
    base = template(result, name)
    if _llm is None:
        return base
    try:
        text = _llm(evidence_payload(result, name))
    except Exception as exc:  # network failure, quota, anything: fail safe to the template
        base["rejected_reason"] = f"language model unavailable ({type(exc).__name__})"
        return base
    ok, why = validate(text or "", result)
    if not ok:
        base["rejected_reason"] = f"language model output rejected: {why}"
        return base
    out = dict(base)
    out.update({"summary": text.strip(), "source": "llm", "validated": True, "rejected_reason": ""})
    return out
