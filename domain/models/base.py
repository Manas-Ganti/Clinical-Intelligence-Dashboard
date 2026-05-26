"""Shared base model and provenance types for all domain objects.

Every top-level domain object inherits ``DomainBase`` so that identity,
provenance, and a data-quality signal travel with the data through every layer of
the pipeline — ingestion can never produce an object that has lost track of where
it came from or how clean it was.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SourceSystem(str, Enum):
    """Which upstream system/adapter produced a record (provenance)."""

    EHR = "ehr"
    FHIR_API = "fhir_api"
    CSV_UPLOAD = "csv_upload"
    PACS = "pacs"  # radiology archive; pairs with ImagingStudy.source_format


class DomainBase(BaseModel):
    """Common envelope carried by every top-level domain object."""

    id: str  # canonical internal ID (UUID4 as string), assigned at ingestion
    created_at: datetime
    updated_at: datetime
    source_system: SourceSystem
    source_record_id: str  # the record's original ID in its source system
    # 0.0-1.0 confidence the record ingested cleanly. The ingestion layer lowers
    # this each time a field needs coercion, so downstream layers can flag or
    # filter shaky records instead of trusting every record equally.
    data_quality_score: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(from_attributes=True)
