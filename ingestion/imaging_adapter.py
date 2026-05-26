"""Imaging file ingestion — reads .dcm (pydicom) / .nii (nibabel) and splits each
file into metadata (-> ImagingStudy) and pixel bytes (-> object storage).

DICOM headers embed PHI next to the pixels, so we de-identify before storing the
bytes; the canonical patient_id linkage lives only in our DB. PHI burned into the
pixels themselves is a known, deferred gap (would need OCR redaction). This is the
plug-in point for real .dcm/.nii datasets — see ARCHITECTURE.md Phase 4b.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable, Iterator
from uuid import uuid4

import nibabel as nib
import pydicom

from domain.models.base import SourceSystem
from domain.models.imaging_study import ImageFormat, ImagingStudy, Modality
from ingestion.base import IngestionAdapter, logger
from ingestion.blob_store import FilesystemBlobStore

# DICOM tags that carry PHI; cleared before the file is stored.
_PHI_TAGS = [
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientAddress",
    "OtherPatientIDs",
    "PatientTelephoneNumbers",
]


def _to_modality(code: str) -> Modality:
    try:
        return Modality(code)
    except ValueError:
        return Modality.OTHER


def _parse_dicom_date(value) -> datetime:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


class ImagingFileAdapter(IngestionAdapter[ImagingStudy]):
    source_name = "imaging_files"
    source_system = SourceSystem.PACS

    def __init__(
        self,
        files: Iterable[tuple[str | Path, str]],  # (path, patient_mrn)
        patient_id_by_mrn: dict[str, str],
        blob_store: FilesystemBlobStore | None = None,
    ):
        self.files = [(Path(p), mrn) for p, mrn in files]
        self.patient_id_by_mrn = patient_id_by_mrn
        self.blob_store = blob_store or FilesystemBlobStore()

    def read(self) -> Iterator[ImagingStudy]:
        for path, mrn in self.files:
            pid = self.patient_id_by_mrn.get(mrn or "")
            if pid is None:
                logger.warning(
                    "record_skipped", reason="unknown_patient_mrn",
                    source="imaging", patient_mrn=mrn,
                )
                continue
            if path.suffix.lower() == ".dcm":
                yield self._ingest_dicom(path, pid)
            else:
                yield self._ingest_nifti(path, pid)

    def _envelope(self, source_record_id: str, quality: float = 1.0) -> dict:
        now = datetime.now(timezone.utc)
        return dict(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            source_system=self.source_system,
            source_record_id=source_record_id,
            data_quality_score=quality,
        )

    def _ingest_dicom(self, path: Path, patient_id: str) -> ImagingStudy:
        ds = pydicom.dcmread(str(path))
        modality = str(ds.get("Modality", "OTHER")).upper()
        study_date = ds.get("StudyDate")
        body_part = ds.get("BodyPartExamined") or None
        series = int(ds.get("SeriesNumber", 1) or 1)

        # De-identify PHI tags BEFORE the bytes leave for the blob store.
        for tag in _PHI_TAGS:
            if tag in ds:
                ds[tag].value = ""
        buf = BytesIO()
        ds.save_as(buf, enforce_file_format=True)
        uri = self.blob_store.put(f"{patient_id}/{path.name}", buf.getvalue())
        logger.info(
            "imaging_ingested", format="dicom", modality=modality,
            deidentified=True, patient_id=patient_id,
        )
        return ImagingStudy(
            **self._envelope(path.name),
            patient_id=patient_id,
            modality=_to_modality(modality),
            body_part=str(body_part) if body_part else None,
            study_date=_parse_dicom_date(study_date),
            series_count=max(series, 1),
            image_uri=uri,
            source_format=ImageFormat.DICOM,
        )

    def _ingest_nifti(self, path: Path, patient_id: str) -> ImagingStudy:
        img = nib.load(str(path))
        shape = img.shape
        series = shape[3] if len(shape) > 3 else 1
        uri = self.blob_store.put(f"{patient_id}/{path.name}", path.read_bytes())
        # NIfTI carries almost no clinical metadata, so modality/date are assumed
        # -> a lower data_quality_score flags that for downstream consumers.
        logger.info("imaging_ingested", format="nifti", patient_id=patient_id, assumed_modality="MR")
        return ImagingStudy(
            **self._envelope(path.name, quality=0.6),
            patient_id=patient_id,
            modality=Modality.MR,
            body_part=None,
            study_date=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
            series_count=int(series),
            image_uri=uri,
            source_format=ImageFormat.NIFTI,
        )
