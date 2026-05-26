"""Phase 2 API tests: the routes return the right shapes and status codes,
using FastAPI's TestClient against an in-memory DB injected via dependency
override. The client is created without a `with` block so the app lifespan
(which would create/seed the real configured DB) never runs.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401  register tables on Base.metadata
from backend.db import Base, get_db
from backend.main import app
from backend.services import patient_service
from ingestion.csv_adapter import CSVPatientAdapter

SAMPLE = Path(__file__).parent.parent / "ingestion" / "sample_data" / "patients.csv"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    # Seed the test DB directly through the service layer.
    seed_session = TestSession()
    patient_service.bulk_create(seed_session, list(CSVPatientAdapter(SAMPLE).read()))
    seed_session.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_patients(client):
    r = client.get("/patients")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 6
    # response shape mirrors the Pydantic Patient contract
    assert {"id", "mrn", "given_name", "sex", "source_system"} <= body[0].keys()


def test_get_patient_by_id(client):
    listed = client.get("/patients").json()
    target = listed[0]
    r = client.get(f"/patients/{target['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == target["id"]


def test_get_missing_patient_returns_404(client):
    r = client.get("/patients/nope")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()
