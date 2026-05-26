"""Ingestion foundations: the adapter contract and shared helpers.

Every data source (CSV now; FHIR, SQL, imaging later) is read by an
``IngestionAdapter`` whose only job is to turn messy source records into valid
domain objects, logging each transformation it makes along the way. Keeping this
interface uniform is what lets a new source be a *new adapter* rather than a
pipeline rewrite (see ARCHITECTURE.md).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Iterator, TypeVar

import structlog

from domain.models.base import DomainBase

logger = structlog.get_logger()

T = TypeVar("T", bound=DomainBase)

# The many spellings different source systems use to mean "no value". Normalizing
# these to None in one place keeps every adapter from re-deciding what empty means.
_NULL_TOKENS = {"", "n/a", "na", "null", "none", "nan", "-"}


def clean_null(value: str | None) -> str | None:
    """Collapse the many source spellings of 'no value' down to None."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped.lower() in _NULL_TOKENS:
        return None
    return stripped


class IngestionAdapter(ABC, Generic[T]):
    """Base class for every source adapter.

    Subclasses implement ``read()`` to yield validated domain objects, one per
    source record. Records that cannot be turned into a valid object are skipped
    and logged, never half-formed.
    """

    source_name: str  # set by subclasses; used in logs and provenance

    @abstractmethod
    def read(self) -> Iterator[T]:
        """Yield validated domain objects, one per source record."""
        raise NotImplementedError
