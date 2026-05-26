"""Natural-language query route: POST /query {question} -> typed QueryResult.

Returns 503 if the server has no ANTHROPIC_API_KEY, so the rest of the dashboard
works without LLM credentials configured.
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.llm.query_engine import QueryEngine, QueryResult

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    question: str


@router.post("/query", response_model=QueryResult)
def query(body: QueryRequest, db: Session = Depends(get_db)) -> QueryResult:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Natural-language query requires ANTHROPIC_API_KEY on the server.",
        )
    return QueryEngine(db).ask(body.question)
