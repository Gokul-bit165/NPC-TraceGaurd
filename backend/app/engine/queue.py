"""Intake-to-Analysis Queue for asynchronous login scoring and case reanalysis.

Decouples high-volume intake (e.g. bursts from campus IdP or SIEM) from the CPU/DB-intensive
scoring and case correlation pipeline. Allows the intake endpoint and analyst interface to
remain sub-millisecond responsive during heavy login traffic.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from sqlalchemy.orm import Session

from . import config as cfgmod
from .counter import get_cross_user_counter
from .types import LoginEvent


@dataclass
class IngestBatch:
    id: str
    events: list[LoginEvent]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    done: threading.Event = field(default_factory=threading.Event)
    result_cases: list[dict] = field(default_factory=list)
    error: Optional[Exception] = None


class AnalysisQueue:
    """Multi-worker priority queue separating login intake from analysis."""

    def __init__(self, maxsize: int = 50000) -> None:
        self._q: queue.Queue[Optional[IngestBatch]] = queue.Queue(maxsize=maxsize)
        self._workers: list[threading.Thread] = []
        self._running = False
        self._lock = threading.Lock()
        self._processed_events = 0
        self._processed_batches = 0

    def start(self, num_workers: int = 2) -> None:
        """Start worker threads to consume and analyze batches from the queue."""
        with self._lock:
            if self._running:
                return
            self._running = True
            for i in range(num_workers):
                t = threading.Thread(target=self._worker_loop, name=f"tg-analysis-worker-{i}", daemon=True)
                t.start()
                self._workers.append(t)

    def stop(self, drain: bool = True) -> None:
        """Stop queue workers, optionally draining any remaining work."""
        if drain:
            self.drain()
        with self._lock:
            if not self._running:
                return
            self._running = False
            for _ in self._workers:
                self._q.put(None)  # Sentinel to terminate workers
            for t in self._workers:
                t.join(timeout=2.0)
            self._workers.clear()

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def qsize(self) -> int:
        return self._q.qsize()

    def enqueue(self, events: list[LoginEvent]) -> IngestBatch:
        """Enqueue a batch of login events for asynchronous analysis."""
        batch = IngestBatch(id=f"batch-{time.time_ns()}", events=events)
        self._q.put(batch)
        return batch

    def drain(self, timeout: float = 10.0) -> bool:
        """Wait until all queued items have been processed."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._q.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._q.unfinished_tasks == 0

    def process_batch(self, batch: IngestBatch, db_factory: Optional[Callable[[], Session]] = None) -> list[dict]:
        """Process a batch of login events: update counter, score logins, reanalyze cases."""
        from .. import services
        from ..db import SessionLocal

        factory = db_factory or SessionLocal
        cfg = cfgmod.get()
        counter = get_cross_user_counter()
        touched: set[str] = set()
        opened: list[dict] = []

        with factory() as db:
            if not counter.is_warmed():
                counter.warmup_from_db(db)

            for ev in sorted(batch.events, key=lambda x: x.ts):
                services.upsert_user(db, ev.user_id)
                # Stream into shared cross-user counter
                counter.record_login(ev.user_id, ev.ts, ev.ip, ev.device, ev.success)
                # Score new login
                risk, band, flags = services.score_new_login(db, ev, cfg)
                services.add_login(db, ev, risk, band, flags)
                touched.add(ev.user_id)

            db.flush()

            # Reanalyze affected users
            for uid in touched:
                c = services.reanalyze_user(db, uid, actor="ingest")
                if c and c.band != "low":
                    opened.append({"case_id": c.id, "user_id": uid, "band": c.band, "score": c.score})

            db.commit()

        with self._lock:
            self._processed_events += len(batch.events)
            self._processed_batches += 1

        batch.result_cases = opened
        batch.done.set()
        return opened

    def _worker_loop(self) -> None:
        while self._running:
            try:
                batch = self._q.get(timeout=0.2)
            except queue.Empty:
                continue

            if batch is None:
                self._q.task_done()
                break

            try:
                self.process_batch(batch)
            except Exception as exc:
                batch.error = exc
                batch.done.set()
            finally:
                self._q.task_done()

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "workers": len(self._workers),
                "queued_batches": self._q.qsize(),
                "processed_batches": self._processed_batches,
                "processed_events": self._processed_events,
            }


_GLOBAL_QUEUE: Optional[AnalysisQueue] = None
_GLOBAL_QUEUE_LOCK = threading.Lock()


def get_analysis_queue() -> AnalysisQueue:
    global _GLOBAL_QUEUE
    if _GLOBAL_QUEUE is None:
        with _GLOBAL_QUEUE_LOCK:
            if _GLOBAL_QUEUE is None:
                _GLOBAL_QUEUE = AnalysisQueue()
    return _GLOBAL_QUEUE


def start_analysis_queue(workers: Optional[int] = None) -> AnalysisQueue:
    q = get_analysis_queue()
    if not q.is_running():
        n = workers or int(os.environ.get("TRACEGUARD_WORKERS", "2"))
        q.start(num_workers=n)
    return q
