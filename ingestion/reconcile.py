"""Cross-source identity reconciliation.

Matches patients across sources on a deterministic key (MRN + birth_date), which
is auditable and explainable — what clinical data demands. Probabilistic matching
(mistyped MRNs/DOBs) is explicitly out of scope (see ARCHITECTURE.md Phase 4a).
"""
from __future__ import annotations

from datetime import date

from domain.models.patient import Patient
from ingestion.base import logger


def _key(p: Patient) -> tuple[str, date]:
    return (p.mrn.strip().lower(), p.birth_date)


def reconcile(
    existing: list[Patient], incoming: list[Patient]
) -> tuple[list[Patient], int]:
    """Return (genuinely new patients, count merged into existing).

    An incoming patient whose (MRN, birth_date) matches an existing one is the
    SAME person arriving from another source — deduped to one canonical record,
    not duplicated.
    """
    index = {_key(p): p for p in existing}
    new: list[Patient] = []
    matched = 0
    for p in incoming:
        k = _key(p)
        if k in index:
            matched += 1
            logger.info(
                "patient_reconciled",
                mrn=p.mrn,
                canonical_id=index[k].id,
                incoming_source=p.source_system.value,
            )
        else:
            index[k] = p
            new.append(p)
    return new, matched
