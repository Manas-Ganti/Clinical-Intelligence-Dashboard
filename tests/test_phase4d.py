"""Phase 4d tests: the audited alert acknowledge workflow.

Core invariant (CLAUDE.md #5): acknowledging an alert writes an audit entry in
the same transaction; re-acknowledging conflicts; missing alerts 404.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401
from backend.bootstrap import seed_if_empty
from backend.db import Base, get_db
from backend.main import app
from backend.services import alert_service
from backend.services.exceptions import ConflictError, NotFoundError


@pytest.fixture
def ctx():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    seed = TestSession()
    seed_if_empty(seed)
    seed.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestSession, TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


def _an_active_alert_id(client):
    alerts = client.get("/alerts").json()
    return next(a["id"] for a in alerts if a["status"] == "active")


def test_acknowledge_writes_audit_entry(ctx):
    TestSession, _ = ctx
    db = TestSession()
    alert_id = alert_service.list_alerts(db)[0].id

    updated = alert_service.acknowledge(db, alert_id, "dr.smith", note="reviewed")
    assert updated.status.value == "acknowledged"
    assert len(updated.audit_trail) == 1
    assert updated.audit_trail[0].acknowledged_by == "dr.smith"
    assert updated.audit_trail[0].prior_status.value == "active"
    db.close()


def test_double_acknowledge_conflicts(ctx):
    TestSession, _ = ctx
    db = TestSession()
    alert_id = alert_service.list_alerts(db)[0].id
    alert_service.acknowledge(db, alert_id, "dr.smith")
    with pytest.raises(ConflictError):
        alert_service.acknowledge(db, alert_id, "dr.jones")
    db.close()


def test_acknowledge_missing_raises(ctx):
    TestSession, _ = ctx
    db = TestSession()
    with pytest.raises(NotFoundError):
        alert_service.acknowledge(db, "nope", "dr.smith")
    db.close()


def test_acknowledge_endpoint(ctx):
    _, client = ctx
    alert_id = _an_active_alert_id(client)

    r = client.post(f"/alerts/{alert_id}/acknowledge", json={"acknowledged_by": "nurse.j"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "acknowledged"
    assert body["audit_trail"][0]["acknowledged_by"] == "nurse.j"

    # re-acknowledge -> 409
    r2 = client.post(f"/alerts/{alert_id}/acknowledge", json={"acknowledged_by": "x"})
    assert r2.status_code == 409


def test_acknowledge_endpoint_404(ctx):
    _, client = ctx
    r = client.post("/alerts/ghost/acknowledge", json={"acknowledged_by": "x"})
    assert r.status_code == 404
