"""Natural-language query route: POST /query {question} -> typed QueryResult.

The configured model decides which credential is required — `ANTHROPIC_API_KEY`
for Claude, `VTARC_API_KEY` for the models VT ARC hosts. If it is missing the
route returns 503 naming the one that is actually needed, so the rest of the
dashboard works without any LLM credentials configured.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.llm.models import default_model, missing_credential, resolve
from backend.llm.query_engine import QueryEngine, QueryResult

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    question: str


class ModelInfo(BaseModel):
    model: str
    provider: str
    max_context: int
    available: bool
    missing_credential: str | None = None


@router.get("/query/model", response_model=ModelInfo)
def query_model() -> ModelInfo:
    """What the Ask bar is wired to right now — shown in the UI, and the quickest
    way to confirm an LLM_MODEL change took effect without spending a request."""
    spec = resolve(default_model())
    missing = missing_credential(spec)
    return ModelInfo(
        model=spec.id,
        provider=spec.provider,
        max_context=spec.max_context,
        available=missing is None,
        missing_credential=missing,
    )


@router.post("/query", response_model=QueryResult)
def query(body: QueryRequest, db: Session = Depends(get_db)) -> QueryResult:
    spec = resolve(default_model())
    missing = missing_credential(spec)
    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Natural-language query requires {missing} on the server "
                f"(model {spec.id!r}, provider {spec.provider!r})."
            ),
        )
    return QueryEngine(db, model=spec.id).ask(body.question)
