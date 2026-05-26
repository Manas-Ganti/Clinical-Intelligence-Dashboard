"""ImagingStudy domain model — metadata for a medical imaging study.

Pixel data is deliberately NOT stored here: ``image_uri`` points to the bytes in
object storage (see ARCHITECTURE.md Phase 4b). Keeping the model to metadata only
means studies stay small, queryable, and cheap to serialize over the API, while
the tens-to-hundreds of MB of pixels stream from a blob store on demand.
"""
from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator

from domain.models.base import DomainBase


class Modality(str, Enum):
    CT = "CT"
    MR = "MR"
    US = "US"
    XR = "XR"
    PET = "PET"
    NM = "NM"
    OTHER = "OTHER"


class ImageFormat(str, Enum):
    DICOM = "dicom"
    NIFTI = "nifti"


class ImagingStudy(DomainBase):
    patient_id: str
    encounter_id: str | None = None
    modality: Modality
    body_part: str | None = None
    study_date: datetime
    series_count: int = Field(ge=1)  # a study always has at least one series
    image_uri: str  # pointer to pixels in object storage — never the bytes
    source_format: ImageFormat

    @field_validator("image_uri")
    @classmethod
    def image_uri_has_scheme(cls, v: str) -> str:
        # Require a scheme (s3://, file://, https://...) so a study can never
        # carry a bare path we can't resolve to a real blob location.
        if "://" not in v:
            raise ValueError(
                "image_uri must include a scheme, e.g. s3:// or file://"
            )
        return v
