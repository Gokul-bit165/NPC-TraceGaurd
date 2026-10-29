"""Regression suite: the scripted scenarios must stay in their expected bands.

These scenarios were written by the team. Passing them shows the weights behave as designed; it is not a
measure of accuracy on real attacks.
"""
import pytest

from app.engine import config as cfgmod

KEYS = ["phish_takeover", "phish_only", "spoofed_harmless", "bulk_notice", "student_trip", "impossible_travel", "credential_stuffing", "lab_machine", "prompt_injection"]


@pytest.mark.parametrize("key", KEYS)
def test_expected_band(key, scenarios, results):
    s = next(x for x in scenarios if x.key == key)
    assert results[key].band == s.expected_band, f"{key}: got {results[key].band} score {results[key].score}"


def test_ledger_sums_to_side_scores(results):
    for key, r in results.items():
        email = sum(e.points for e in r.ledger if e.side == "email" or e.code == "EMAIL_CAP")
        login = sum(e.points for e in r.ledger if e.side == "login" or e.code == "LOGIN_CAP")
        assert email == r.email_score, key
        assert login == r.login_score, key


def test_case_score_formula(results, cfg):
    u, ceil = cfg["correlation"]["uplift"], cfg["correlation"]["email_only_ceiling"]
    for key, r in results.items():
        uplift = round(u * min(r.email_score, r.login_score) + 1e-9) if r.correlated else 0
        expected = min(100, max(r.email_score, r.login_score) + uplift)
        if not r.correlated and r.email_score >= r.login_score:
            expected = min(expected, ceil)
        assert r.score == expected, key
        assert sum(e.points for e in r.ledger if e.side in ("correlation", "cap") and e.code in ("X_EMAIL_THEN_LOGIN", "CASE_CAP", "EMAIL_ONLY_CEILING")) \
            + max(r.email_score, r.login_score) == r.score, key


def test_critical_needs_login_evidence(results):
    for key, r in results.items():
        if r.band == "critical":
            assert r.login_score > 0 and r.correlated, key


def test_email_alone_never_critical(results):
    assert results["phish_only"].score == 79 and results["phish_only"].band == "high"
    assert any(e.code == "EMAIL_ONLY_CEILING" for e in results["phish_only"].ledger)


def test_correlation_requires_both_sides_medium(scenarios, cfg, ctx):
    """A newsletter plus a typo burst must not be linked."""
    from app import scenarios as sc
    from app.engine.pipeline import analyze_case
    from app.engine.types import LoginEvent
    from datetime import timedelta
    from conftest import FIXED_NOW
    A = sc.anchor_time(FIXED_NOW)
    s = next(x for x in scenarios if x.key == "phish_only")      # strong email, normal logins
    p = s.person
    logins = list(s.logins)
    ip = logins[-1].ip
    for k in range(3):
        logins.append(LoginEvent(p.id, A - timedelta(minutes=50 - k), ip, p.country, p.city, device=logins[-1].device, success=False))
    logins.append(LoginEvent(p.id, A - timedelta(minutes=45), ip, p.country, p.city, device=logins[-4].device, success=True))
    r = analyze_case(p.id, s.emails, logins, cfg, ctx, as_of=A)
    assert r.login_score < cfg["correlation"]["min_login_score"]
    assert not r.correlated and r.band == "high"


def test_login_before_email_does_not_correlate(scenarios, cfg, ctx):
    from app import scenarios as sc
    from app.engine.pipeline import analyze_case
    from datetime import timedelta
    from conftest import FIXED_NOW
    A = sc.anchor_time(FIXED_NOW)
    s = next(x for x in scenarios if x.key == "phish_takeover")
    late = s.emails[0]
    late.received_at = A - timedelta(minutes=5)          # email arrives AFTER the takeover login
    try:
        r = analyze_case(s.person.id, [late], s.logins, cfg, ctx, as_of=A)
        assert not r.correlated
        assert r.band in ("high", "critical")
    finally:
        late.received_at = A - timedelta(hours=3)


def test_thin_history_is_flagged_and_halved(cfg, ctx):
    from datetime import datetime, timedelta, timezone
    from app.engine.pipeline import analyze_case
    from app.engine.types import LoginEvent
    A = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
    hist = [LoginEvent("new-user", A - timedelta(days=3, hours=i), "1.1.1.1", "IN", "Pune", device="windows|chrome") for i in range(2)]
    now = LoginEvent("new-user", A - timedelta(hours=1), "2.2.2.2", "GB", "London", device="ios|safari")
    r = analyze_case("new-user", [], hist + [now], cfg, ctx, as_of=A)
    assert r.low_confidence
    pts = {e.code: e.points for e in r.ledger}
    assert pts["L_NEW_COUNTRY"] == cfg["login"]["signals"]["new_country"]["points"] * cfg["login"]["thin_history_factor"]


def test_config_validation_rejects_gaps(cfg):
    import copy
    bad = copy.deepcopy(cfg)
    bad["bands"]["high"] = [65, 79]
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.validate(bad)
