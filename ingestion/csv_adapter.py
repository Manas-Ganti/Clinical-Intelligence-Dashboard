"""CSV ingestion adapter — reads a patient CSV and emits Patient domain objects.

Demonstrates the core ingestion responsibility: every value that has to be
reshaped (date formats, sex codes, null spellings) is normalized AND logged, and
each coercion lowers the record's ``data_quality_score`` so downstream layers can
see how clean the data was. A row that can't yield a valid Patient is skipped,
not emitted half-formed.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from pydantic import ValidationError

from domain.models.base import SourceSystem
from domain.models.patient import Patient, Sex
from ingestion.base import IngestionAdapter, clean_null, logger

# Penalty applied to data_quality_score per coerced field, clamped at 0.0.
_COERCION_PENALTY = 0.1

_SEX_MAP = {
    "m": Sex.MALE,
    "male": Sex.MALE,
    "f": Sex.FEMALE,
    "female": Sex.FEMALE,
    "o": Sex.OTHER,
    "other": Sex.OTHER,
}
_TRUE_TOKENS = {"true", "yes", "y", "1"}
_FALSE_TOKENS = {"false", "no", "n", "0"}

# Source date formats we accept, tried in order. ISO first because it's the only
# unambiguous one; the others are logged as coercions when they hit.
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y")


class CSVPatientAdapter(IngestionAdapter[Patient]):
    source_name = "csv_upload"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> Iterator[Patient]:
        with self.path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                patient = self._row_to_patient(row)
                if patient is not None:
                    yield patient

    # -- record mapping --------------------------------------------------- #
    def _row_to_patient(self, row: dict[str, str]) -> Patient | None:
        source_id = clean_null(row.get("patient_id")) or "unknown"
        quality = 1.0

        # birth_date is required by the domain model; a row we can't date is
        # unusable, so we skip it rather than emit an invalid Patient.
        birth_date, date_quality = self._parse_date(row.get("dob"), source_id)
        if birth_date is None:
            logger.warning(
                "record_skipped",
                reason="unparseable_dob",
                source_record_id=source_id,
                raw=row.get("dob"),
            )
            return None
        quality = min(quality, date_quality)

        sex, sex_coerced = self._parse_sex(row.get("gender"), source_id)
        if sex_coerced:
            quality -= _COERCION_PENALTY

        deceased, dec_coerced = self._parse_bool(clean_null(row.get("deceased")))
        if dec_coerced:
            quality -= _COERCION_PENALTY

        now = datetime.now(timezone.utc)
        try:
            return Patient(
                # Canonical UUID; the source's own id is kept as mrn /
                # source_record_id so reconciliation can match it later.
                id=str(uuid4()),
                created_at=now,
                updated_at=now,
                source_system=SourceSystem.CSV_UPLOAD,
                source_record_id=source_id,
                data_quality_score=max(quality, 0.0),
                mrn=source_id,
                given_name=clean_null(row.get("first_name")) or "",
                family_name=clean_null(row.get("last_name")) or "",
                birth_date=birth_date,
                sex=sex,
                deceased=deceased,
            )
        except ValidationError as exc:
            logger.warning(
                "record_skipped",
                reason="validation_error",
                source_record_id=source_id,
                error_count=exc.error_count(),
            )
            return None

    # -- field coercions -------------------------------------------------- #
    def _parse_date(self, raw: str | None, source_id: str) -> tuple[date | None, float]:
        value = clean_null(raw)
        if value is None:
            return None, 1.0
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(value, fmt).date()
            except ValueError:
                continue
            if fmt != "%Y-%m-%d":
                logger.info(
                    "field_coerced",
                    field="birth_date",
                    original=value,
                    coerced=parsed.isoformat(),
                    rule=f"{fmt} -> ISO",
                    source_record_id=source_id,
                )
                return parsed, 1.0 - _COERCION_PENALTY
            return parsed, 1.0
        return None, 0.0

    def _parse_sex(self, raw: str | None, source_id: str) -> tuple[Sex, bool]:
        value = clean_null(raw)
        if value is None:
            logger.info(
                "field_coerced",
                field="sex",
                original=raw,
                coerced=Sex.UNKNOWN.value,
                rule="null -> unknown",
                source_record_id=source_id,
            )
            return Sex.UNKNOWN, True
        mapped = _SEX_MAP.get(value.lower())
        if mapped is None:
            logger.warning(
                "field_coerced",
                field="sex",
                original=value,
                coerced=Sex.UNKNOWN.value,
                rule="unrecognized -> unknown",
                source_record_id=source_id,
            )
            return Sex.UNKNOWN, True
        if value.lower() != mapped.value:  # e.g. "M" or "F" -> full enum value
            logger.info(
                "field_coerced",
                field="sex",
                original=value,
                coerced=mapped.value,
                rule="normalized",
                source_record_id=source_id,
            )
            return mapped, True
        return mapped, False

    def _parse_bool(self, value: str | None) -> tuple[bool, bool]:
        if value is None:
            return False, True  # default to False, but flag the ambiguity
        low = value.lower()
        if low in _TRUE_TOKENS:
            return True, False
        if low in _FALSE_TOKENS:
            return False, False
        return False, True
