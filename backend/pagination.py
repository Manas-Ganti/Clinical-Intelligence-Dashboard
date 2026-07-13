"""Shared pagination contract for the list endpoints.

Real data forced this: a Synthea load is ~150k findings and ~53k encounters, and
the original unbounded ``GET /findings`` would have serialized every one of them
into a single response. The service layer can still be called unbounded from
inside the process (seeding, analytics); the *API* never is.

Responses stay a plain JSON array — paging metadata rides in the ``X-Total-Count``
header — so a client that doesn't care about paging needs no changes.
"""
from typing import Annotated

from fastapi import Query, Response

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

Limit = Annotated[
    int,
    Query(ge=1, le=MAX_LIMIT, description=f"Page size (max {MAX_LIMIT})."),
]
Offset = Annotated[int, Query(ge=0, description="Rows to skip.")]


def set_total(response: Response, total: int) -> None:
    """Advertise the unpaged total so a client knows how far it can page."""
    response.headers["X-Total-Count"] = str(total)
