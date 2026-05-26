"""SQLAlchemy ORM tables — the persistence representation.

These are deliberately separate from the Pydantic domain models: the service
layer maps between the two, so the ORM never leaks past the service boundary and
the domain models stay free of persistence concerns. Every table shares the
``EnvelopeMixin`` columns, mirroring the DomainBase envelope.
"""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class EnvelopeMixin:
    """The DomainBase envelope as ORM columns (identity + provenance + quality)."""

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    source_system: Mapped[str] = mapped_column(String)
    source_record_id: Mapped[str] = mapped_column(String)
    data_quality_score: Mapped[float] = mapped_column(Float)


class PatientORM(EnvelopeMixin, Base):
    __tablename__ = "patients"

    mrn: Mapped[str] = mapped_column(String, index=True)
    given_name: Mapped[str] = mapped_column(String)
    family_name: Mapped[str] = mapped_column(String, index=True)
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String)
    deceased: Mapped[bool] = mapped_column(Boolean, default=False)


class EncounterORM(EnvelopeMixin, Base):
    __tablename__ = "encounters"

    patient_id: Mapped[str] = mapped_column(String, index=True)
    encounter_class: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    period_start: Mapped[datetime] = mapped_column(DateTime)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)


class FindingORM(EnvelopeMixin, Base):
    __tablename__ = "findings"

    patient_id: Mapped[str] = mapped_column(String, index=True)
    encounter_id: Mapped[str | None] = mapped_column(String, nullable=True)
    code: Mapped[str] = mapped_column(String)
    display: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
    abnormal_flag: Mapped[str] = mapped_column(String)
    reference_range_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_range_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    raw_value: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_unit: Mapped[str | None] = mapped_column(String, nullable=True)


class ImagingStudyORM(EnvelopeMixin, Base):
    __tablename__ = "imaging_studies"

    patient_id: Mapped[str] = mapped_column(String, index=True)
    encounter_id: Mapped[str | None] = mapped_column(String, nullable=True)
    modality: Mapped[str] = mapped_column(String)
    body_part: Mapped[str | None] = mapped_column(String, nullable=True)
    study_date: Mapped[datetime] = mapped_column(DateTime)
    series_count: Mapped[int] = mapped_column(Integer)
    image_uri: Mapped[str] = mapped_column(String)
    source_format: Mapped[str] = mapped_column(String)


class AlertORM(EnvelopeMixin, Base):
    __tablename__ = "alerts"

    patient_id: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    triggered_at: Mapped[datetime] = mapped_column(DateTime)
    finding_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # audit_trail stored as JSON for Phase 3 seeding (all seeded alerts are
    # ACTIVE, so empty). Phase 4d adds the acknowledge workflow that writes here.
    audit_trail: Mapped[list] = mapped_column(JSON, default=list)
