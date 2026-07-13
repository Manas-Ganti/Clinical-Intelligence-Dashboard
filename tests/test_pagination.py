"""Pagination tests for the list endpoints.

Real data forced pagination into existence: a Synthea load is ~150k findings, and
the original unbounded ``GET /findings`` would have serialized every one of them
into a single response. These tests pin the contract that stops that regressing.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.db_models  # noqa: F401  register tables
from backend.bootstrap import seed_if_empty
from backend.db import Base, get_db
from backend.main import app
from backend.pagination import MAX_LIMIT


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    seed = TestSession()
    seed_if_empty(seed, source="sample")
    seed.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.mark.parametrize(
    "path", ["/patients", "/encounters", "/findings", "/alerts", "/imaging"]
)
def test_total_count_header_reports_the_unpaged_total(client, path):
    """A paged client has to know how far it can page."""
    full = client.get(path, params={"limit": MAX_LIMIT})
    assert full.status_code == 200
    total = len(full.json())
    assert full.headers["X-Total-Count"] == str(total)

    page = client.get(path, params={"limit": 2})
    assert len(page.json()) <= 2
    # The header is the total, not the page size.
    assert page.headers["X-Total-Count"] == str(total)


@pytest.mark.parametrize(
    "path", ["/patients", "/encounters", "/findings", "/alerts", "/imaging"]
)
def test_offset_walks_without_repeating_or_skipping(client, path):
    everything = client.get(path, params={"limit": MAX_LIMIT}).json()

    walked = []
    for offset in range(0, len(everything), 2):
        walked.extend(client.get(path, params={"limit": 2, "offset": offset}).json())

    assert [r["id"] for r in walked] == [r["id"] for r in everything]


def test_limit_is_capped(client):
    """A client cannot ask for the whole 150k-row table in one response."""
    over = client.get("/findings", params={"limit": MAX_LIMIT + 1})
    assert over.status_code == 422

    assert client.get("/findings", params={"limit": 0}).status_code == 422
    assert client.get("/findings", params={"offset": -1}).status_code == 422


def test_findings_still_filter_by_patient_while_paged(client):
    patient_id = client.get("/patients").json()[0]["id"]
    resp = client.get("/findings", params={"patient_id": patient_id, "limit": 5})

    assert resp.status_code == 200
    assert all(f["patient_id"] == patient_id for f in resp.json())
    # The total reflects the filter, not the whole table.
    assert resp.headers["X-Total-Count"] == str(
        len(client.get("/findings", params={"patient_id": patient_id,
                                            "limit": MAX_LIMIT}).json())
    )


def test_patient_order_is_total_so_paging_cannot_repeat_or_skip(client):
    """Patients sort by family_name, which is not unique — there are 14 Abbotts.

    If ties broke arbitrarily, two requests for the same offset could return
    different rows, and paging could show a patient twice or skip them entirely.
    Ties break on id, so the order is total and stable across requests.
    """
    first = client.get("/patients", params={"limit": MAX_LIMIT}).json()
    again = client.get("/patients", params={"limit": MAX_LIMIT}).json()
    assert [p["id"] for p in first] == [p["id"] for p in again]

    # And the same order holds when the list is walked a page at a time.
    walked = []
    for offset in range(0, len(first), 2):
        walked.extend(
            client.get("/patients", params={"limit": 2, "offset": offset}).json()
        )
    ids = [p["id"] for p in walked]
    assert ids == [p["id"] for p in first]
    assert len(ids) == len(set(ids))  # nobody appears twice
