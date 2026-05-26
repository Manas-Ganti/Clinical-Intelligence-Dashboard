"""Patient domain model — a person receiving care."""
from datetime import date
from enum import Enum

from pydantic import field_validator

from domain.models.base import DomainBase


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class Patient(DomainBase):
    # MRN is the clinical identifier humans use; kept distinct from
    # source_record_id because the same MRN can arrive from several systems and
    # we reconcile those into one canonical Patient by MRN + birth_date later.
    mrn: str
    given_name: str
    family_name: str
    birth_date: date
    sex: Sex
    deceased: bool = False

    @field_validator("birth_date")
    @classmethod
    def birth_date_not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("birth_date cannot be in the future")
        return v
