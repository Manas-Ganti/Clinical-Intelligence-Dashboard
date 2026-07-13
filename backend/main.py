"""FastAPI application: wires routers, creates tables, seeds sample data on boot."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import backend.db_models  # noqa: F401  registers ORM tables on Base.metadata
from backend.bootstrap import seed_if_empty
from backend.db import Base, SessionLocal, engine
from backend.routers import alerts, encounters, findings, imaging, patients, query

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seeded = seed_if_empty(db)
        if seeded:
            logger.info("sample_data_seeded", **seeded)
    finally:
        db.close()
    yield


app = FastAPI(title="Clinical Intelligence Dashboard API", lifespan=lifespan)

# The React dev server runs on a different origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this the browser hides X-Total-Count from cross-origin JS, and the
    # frontend's page-walker would stop after one page — silently truncating a
    # patient's findings instead of failing loudly.
    expose_headers=["X-Total-Count"],
)

app.include_router(patients.router)
app.include_router(encounters.router)
app.include_router(findings.router)
app.include_router(imaging.router)
app.include_router(alerts.router)
app.include_router(query.router)


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
