"""Tests for the intake-to-analysis queue and worker execution."""
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

from app.db import reset_db, SessionLocal
from app.engine.counter import reset_cross_user_counter, get_cross_user_counter
from app.engine.queue import AnalysisQueue, IngestBatch
from app.engine.types import LoginEvent
from app.models import CaseRow, LoginRow


@pytest.fixture(autouse=True)
def clean_state():
    reset_db()
    reset_cross_user_counter()
    yield
    reset_cross_user_counter()


def test_queue_enqueue_and_process():
    """Verify queue accepts events and worker pool scores logins and opens cases."""
    q = AnalysisQueue()
    q.start(num_workers=2)
    now = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)

    # u-rohan has a suspicious login (high-risk country/device/IP anomaly)
    events = [
        LoginEvent(user_id="u-rohan", ts=now, ip="198.51.100.9", country="BR", city="Sao Paulo",
                   device="linux|firefox", success=True)
    ]
    batch = q.enqueue(events)
    assert batch.id.startswith("batch-")
    assert not batch.done.is_set()

    # Drain queue
    assert q.drain(timeout=5.0)
    assert batch.done.is_set()
    assert batch.error is None

    # Check database state
    with SessionLocal() as db:
        login = db.scalar(select(LoginRow).where(LoginRow.user_id == "u-rohan"))
        assert login is not None
        assert login.ip == "198.51.100.9"

        # Cross user counter was updated
        counter = get_cross_user_counter()
        assert counter.get_ip_user_count("198.51.100.9", as_of=now) == 1

    q.stop()


def test_queue_burst_intake():
    """Verify queue handles a rapid burst of multiple batches across workers."""
    q = AnalysisQueue()
    q.start(num_workers=3)
    now = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)

    batches = []
    for i in range(10):
        evs = [
            LoginEvent(user_id=f"u-burst-{i}", ts=now, ip=f"198.51.100.{i % 4}",
                       country="IN", city="Mumbai", device="windows|chrome", success=True)
        ]
        batches.append(q.enqueue(evs))

    assert q.drain(timeout=10.0)
    for b in batches:
        assert b.done.is_set()

    stats = q.stats
    assert stats["processed_events"] >= 10
    q.stop()
