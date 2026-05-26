"""Domain models — the typed contract shared by every layer.

Import from here (``from domain.models import Patient``) rather than reaching into
the individual modules, so the public surface of the domain layer stays explicit.
"""
from domain.models.alert import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AuditEntry,
)
from domain.models.base import DomainBase, SourceSystem
from domain.models.encounter import (
    Encounter,
    EncounterClass,
    EncounterStatus,
)
from domain.models.finding import AbnormalFlag, Finding
from domain.models.imaging_study import ImageFormat, ImagingStudy, Modality
from domain.models.patient import Patient, Sex

__all__ = [
    # base / provenance
    "DomainBase",
    "SourceSystem",
    # patient
    "Patient",
    "Sex",
    # encounter
    "Encounter",
    "EncounterClass",
    "EncounterStatus",
    # finding
    "Finding",
    "AbnormalFlag",
    # imaging
    "ImagingStudy",
    "Modality",
    "ImageFormat",
    # alert
    "Alert",
    "AlertSeverity",
    "AlertStatus",
    "AuditEntry",
]
