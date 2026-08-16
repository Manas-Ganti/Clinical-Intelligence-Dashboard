"""Finding service — the only place finding SQL lives."""
import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db_models import FindingORM
from domain.models.finding import Finding

logger = structlog.get_logger()

# Newest first, ties broken on id so the order is total (see patient_service:
# a page boundary landing inside a group of equal timestamps could otherwise
# repeat or skip rows). Synthea stamps a whole panel with one observed_at, so
# ties here are the rule, not the exception.
_ORDER = (FindingORM.observed_at.desc(), FindingORM.id)


def _to_orm(f: Finding) -> FindingORM:
    return FindingORM(
        id=f.id,
        created_at=f.created_at,
        updated_at=f.updated_at,
        source_system=f.source_system.value,
        source_record_id=f.source_record_id,
        data_quality_score=f.data_quality_score,
        patient_id=f.patient_id,
        encounter_id=f.encounter_id,
        code=f.code,
        display=f.display,
        value=f.value,
        unit=f.unit,
        abnormal_flag=f.abnormal_flag.value,
        reference_range_low=f.reference_range_low,
        reference_range_high=f.reference_range_high,
        observed_at=f.observed_at,
        raw_value=f.raw_value,
        raw_unit=f.raw_unit,
    )


def list_findings(
    db: Session,
    patient_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    *,
    abnormal_flag: str | None = None,
    code_contains: str | None = None,
) -> list[Finding]:
    """List findings, newest first, optionally filtered and paged.

    ``limit=None`` is unbounded and exists for internal callers (seeding,
    analytics) that legitimately want every row. The API layer never passes None
    — a real Synthea load is ~150k findings, and serializing that into one
    response would be a denial of service on our own frontend.

    abnormal_flag/code_contains filter in SQL rather than in the caller: the LLM
    tool layer used to pull all 150k findings into Python and filter the list
    there, which is a full table scan on every natural-language question.

    On ordering: this used to sort *ascending* despite the docstring, which made
    every capped result a window onto the oldest rows in the table. Asked which
    labs were critical, the model got 100 findings from 1965-71 — all Creatinine,
    by coincidence of what Synthea generates early in a life — and reported that
    all 995 critical results were Creatinine. 252 of them are not. The rows a
    caller can afford to look at should be the most recent ones, for the model
    and the UI alike.
    """
    stmt = select(FindingORM).order_by(*_ORDER)
    if patient_id:
        stmt = stmt.where(FindingORM.patient_id == patient_id)
    if abnormal_flag:
        stmt = stmt.where(FindingORM.abnormal_flag == abnormal_flag)
    if code_contains:
        # Nobody types "718-7", and nobody types the exact display name either.
        # Match either, case-insensitively.
        needle = f"%{code_contains.lower()}%"
        stmt = stmt.where(
            func.lower(FindingORM.display).like(needle)
            | func.lower(FindingORM.code).like(needle)
        )
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return [Finding.model_validate(r) for r in db.scalars(stmt).all()]


def count_findings(
    db: Session,
    patient_id: str | None = None,
    *,
    abnormal_flag: str | None = None,
    code_contains: str | None = None,
) -> int:
    """Total matching findings, so a paged client knows how many there are.

    The LLM layer needs this too — it sees a capped page, so without a true count
    it cannot answer "how many?" without inferring it from the page size.
    """
    stmt = select(func.count()).select_from(FindingORM)
    if patient_id:
        stmt = stmt.where(FindingORM.patient_id == patient_id)
    if abnormal_flag:
        stmt = stmt.where(FindingORM.abnormal_flag == abnormal_flag)
    if code_contains:
        needle = f"%{code_contains.lower()}%"
        stmt = stmt.where(
            func.lower(FindingORM.display).like(needle)
            | func.lower(FindingORM.code).like(needle)
        )
    return db.scalar(stmt) or 0


def bulk_create(db: Session, items: list[Finding]) -> int:
    db.add_all([_to_orm(f) for f in items])
    db.commit()
    logger.info("findings_bulk_created", count=len(items))
    return len(items)
