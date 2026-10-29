import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Isolated database and model directory for the whole test session.
_tmp = tempfile.mkdtemp(prefix="traceguard-test-")
os.environ["TRACEGUARD_DB"] = f"sqlite:///{_tmp}/test.db"
os.environ["TRACEGUARD_MODEL_DIR"] = f"{_tmp}/models"

FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def cfg():
    from app.engine import config
    return config.get()


@pytest.fixture(scope="session")
def scenarios():
    from app import scenarios as sc
    return sc.build_all(FIXED_NOW)


@pytest.fixture(scope="session")
def ctx(scenarios, cfg):
    from app import scenarios as sc
    from app.engine.pipeline import build_context
    return build_context(sc.all_logins(scenarios), cfg["login"]["window_hours"], sc.anchor_time(FIXED_NOW))


@pytest.fixture(scope="session")
def results(scenarios, cfg, ctx):
    from app import scenarios as sc
    from app.engine.pipeline import analyze_case
    A = sc.anchor_time(FIXED_NOW)
    return {s.key: analyze_case(s.person.id, s.emails, s.logins, cfg, ctx, as_of=A) for s in scenarios}


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.db import reset_db, SessionLocal
    from app.main import app
    from app import seed
    reset_db()
    with SessionLocal() as db:
        seed.seed(db, now=FIXED_NOW, n_background=20, n_legit_emails=120, verbose=False)
    with TestClient(app) as c:
        yield c
