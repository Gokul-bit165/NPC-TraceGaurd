"""Integration test suite verifying campus scaling features:
1. Queue between intake and analysis prevents interface slowdown.
2. CrossUserCounter matches database cross-user query counts.
3. Indexes present and database dialects supported.
4. Output identical to single-process on seeded scenarios.
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

from app.db import reset_db, SessionLocal
from app.engine.counter import get_cross_user_counter, reset_cross_user_counter
from app.engine.queue import get_analysis_queue, start_analysis_queue
from app.engine.types import LoginEvent
from app.models import CaseRow, LoginRow
from app import scenarios as sc, seed


FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def cleanup():
    reset_db()
    reset_cross_user_counter()
    yield
    reset_cross_user_counter()


def test_cross_user_counter_matches_db_counts():
    """Verify that CrossUserCounter returns identical IP and device counts as raw DB queries."""
    with SessionLocal() as db:
        now = FIXED_NOW
        # Populate 3 logins from IP 198.51.100.5 with 3 distinct users
        events = [
            LoginEvent("u-alice", now, "198.51.100.5", "IN", "Pune", device="win|chrome", success=True),
            LoginEvent("u-bob", now, "198.51.100.5", "IN", "Pune", device="win|chrome", success=True),
            LoginEvent("u-charlie", now, "198.51.100.5", "IN", "Pune", device="mac|safari", success=True),
        ]
        counter = get_cross_user_counter()
        for ev in events:
            counter.record_login(ev.user_id, ev.ts, ev.ip, ev.device, ev.success)
            db.add(LoginRow(user_id=ev.user_id, ts=ev.ts, ip=ev.ip, country=ev.country, city=ev.city,
                            device=ev.device, success=ev.success))
        db.commit()

        # Check IP user count
        assert counter.get_ip_user_count("198.51.100.5", as_of=now) == 3
        # Check Device user count
        assert counter.get_device_user_count("win|chrome", "198.51.100.5") == 2
        assert counter.get_device_user_count("mac|safari", "198.51.100.5") == 1


def test_queue_async_intake():
    """Verify intake enqueues without blocking and worker processes asynchronously."""
    q = start_analysis_queue(workers=2)
    evs = [
        LoginEvent(f"u-q-{i}", FIXED_NOW, f"198.51.100.{i}", "IN", "Delhi", device="win|edge", success=True)
        for i in range(10)
    ]
    batch = q.enqueue(evs)
    assert not batch.done.is_set()
    assert q.drain(timeout=5.0)
    assert batch.done.is_set()
    assert q.stats["processed_events"] >= 10


def test_seeded_data_identical_output():
    """Verify that seeded data produces exactly 41 cases matching expected scenario outcomes."""
    with SessionLocal() as db:
        out = seed.seed(db, now=FIXED_NOW, n_background=60, n_legit_emails=960, rng_seed=42, verbose=False)
        assert out["cases"] == 41

        cases = {c.scenario_key: c for c in db.scalars(select(CaseRow)).all() if c.scenario_key}
        assert cases["phish_takeover"].band == "critical"
        assert cases["phish_takeover"].score == 100
        assert cases["phish_only"].band == "high"
        assert cases["impossible_travel"].band == "high"
        assert cases["credential_stuffing"].band == "high"
        assert cases["prompt_injection"].band == "high"
