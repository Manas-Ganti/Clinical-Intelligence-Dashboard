"""Phase 3 tests: the four patient-linked objects ingest, persist, link to their
patient by MRN, and serve over filtered API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401  register tables
from backend.bootstrap import seed_if_empty
from backend.db import Base, get_db
from backend.main import app


@pytest.fixture
def seeded():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    seed_session = TestSession()
    counts = seed_if_empty(seed_session, source="sample")
    seed_session.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), counts
    app.dependency_overrides.clear()
    engine.dispose()


def test_seed_counts(seeded):
    _, counts = seeded
    # 6 from CSV + 2 new from FHIR (Marie, Rosalind); Ada is reconciled (deduped).
    assert counts["patients"] == 8
    assert counts["patients_reconciled"] == 1
    assert counts["encounters"] == 5
    assert counts["findings"] == 10
    assert counts["alerts"] == 3
    assert counts["imaging"] == 2


def test_findings_filtered_by_patient(seeded):
    client, _ = seeded
    patients = client.get("/patients").json()
    ada = next(p for p in patients if p["mrn"] == "1001")
    findings = client.get(f"/findings?patient_id={ada['id']}").json()
    assert len(findings) == 4  # Ada has four hemoglobin readings
    assert all(f["patient_id"] == ada["id"] for f in findings)
    # ordered by observed_at — the trend the chart will plot
    assert [f["value"] for f in findings] == [9.1, 9.8, 11.2, 12.6]


def test_secondary_endpoints(seeded):
    client, _ = seeded
    assert len(client.get("/encounters").json()) == 5
    assert len(client.get("/alerts").json()) == 3
    imaging = client.get("/imaging").json()
    assert {i["source_format"] for i in imaging} == {"dicom", "nifti"}
    # imaging carries PACS provenance, distinct from the CSV-sourced rows
    assert {i["source_system"] for i in imaging} == {"pacs"}


def test_alerts_seeded_active_without_audit(seeded):
    client, _ = seeded
    alerts = client.get("/alerts").json()
    assert all(a["status"] == "active" for a in alerts)
    assert all(a["audit_trail"] == [] for a in alerts)


def test_unknown_mrn_row_skipped(seeded, tmp_path):
    # An encounter referencing a non-existent patient MRN must be skipped.
    from ingestion.csv_clinical import EncounterCSVAdapter

    csv_text = (
        "patient_mrn,class,status,start,end,reason\n"
        "GHOST,inpatient,finished,2026-01-01T00:00:00,2026-01-02T00:00:00,x\n"
    )
    path = tmp_path / "e.csv"
    path.write_text(csv_text)
    rows = list(EncounterCSVAdapter(path, {"1001": "real-id"}).read())
    assert rows == []
