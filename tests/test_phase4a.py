"""Phase 4a tests: FHIR + SQL adapters and deterministic reconciliation."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401
from backend.bootstrap import seed_if_empty
from backend.db import Base, get_db
from backend.main import app
from domain.models.base import SourceSystem
from domain.models.patient import Sex
from ingestion.csv_adapter import CSVPatientAdapter
from ingestion.fhir_adapter import FHIRPatientAdapter
from ingestion.reconcile import reconcile
from ingestion.sql_adapter import SQLPatientAdapter

DATA = Path(__file__).parent.parent / "ingestion" / "sample_data"


def test_fhir_adapter_maps_patients():
    patients = list(FHIRPatientAdapter(DATA / "fhir_bundle.json").read())
    assert len(patients) == 3
    marie = next(p for p in patients if p.mrn == "7007")
    assert marie.family_name == "Curie"
    assert marie.sex is Sex.FEMALE
    assert marie.source_system is SourceSystem.FHIR_API
    assert marie.deceased is True


def test_reconcile_dedupes_matching_patient():
    csv_patients = list(CSVPatientAdapter(DATA / "patients.csv").read())
    fhir_patients = list(FHIRPatientAdapter(DATA / "fhir_bundle.json").read())
    new, merged = reconcile(csv_patients, fhir_patients)
    assert merged == 1  # Ada (1001, 1815-12-10) matches across both sources
    assert {p.mrn for p in new} == {"7007", "8008"}  # the two genuinely new ones


def test_sql_adapter_reads_external_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE legacy_patients (patient_id TEXT, given_name TEXT, "
                "family_name TEXT, birth_date TEXT, sex TEXT, deceased INTEGER)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO legacy_patients VALUES "
                "('9009','Charles','Babbage','1791-12-26','m',1)"
            )
        )
    patients = list(SQLPatientAdapter(engine).read())
    assert len(patients) == 1
    assert patients[0].family_name == "Babbage"
    assert patients[0].source_system is SourceSystem.EHR


def test_seed_includes_reconciled_fhir_patients():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    seed = TestSession()
    counts = seed_if_empty(seed, source="sample")
    seed.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    patients = client.get("/patients").json()
    assert len(patients) == 8
    by_source: dict[str, int] = {}
    for p in patients:
        by_source[p["source_system"]] = by_source.get(p["source_system"], 0) + 1
    assert by_source["csv_upload"] == 6
    assert by_source["fhir_api"] == 2  # Marie + Rosalind, FHIR-sourced
    assert counts["patients_reconciled"] == 1

    app.dependency_overrides.clear()
    engine.dispose()
