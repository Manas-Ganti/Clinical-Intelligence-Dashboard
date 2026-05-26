"""Phase 2 service tests: persistence round-trips and the not-found path,
against an in-memory SQLite DB so no external service is required.
"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401  register tables on Base.metadata
from backend.db import Base
from backend.services import patient_service
from backend.services.exceptions import NotFoundError
from ingestion.csv_adapter import CSVPatientAdapter

SAMPLE = Path(__file__).parent.parent / "ingestion" / "sample_data" / "patients.csv"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection keeps the in-memory DB alive
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_create_and_get_round_trip(db):
    p = next(CSVPatientAdapter(SAMPLE).read())
    patient_service.create_patient(db, p)

    fetched = patient_service.get_by_id(db, p.id)
    assert fetched.mrn == p.mrn
    assert fetched.sex == p.sex  # enum survives the ORM round-trip
    assert fetched.source_system == p.source_system


def test_list_returns_all_seeded(db):
    patients = list(CSVPatientAdapter(SAMPLE).read())
    inserted = patient_service.bulk_create(db, patients)
    assert inserted == 6
    assert len(patient_service.list_patients(db)) == 6


def test_get_missing_raises_not_found(db):
    with pytest.raises(NotFoundError):
        patient_service.get_by_id(db, "does-not-exist")
