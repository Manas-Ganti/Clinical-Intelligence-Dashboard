"""Service-layer exceptions, translated to HTTP status codes at the API boundary."""


class ServiceError(Exception):
    """Base class for service-layer errors."""


class NotFoundError(ServiceError):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity: str, entity_id: str):
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id} not found")


class ConflictError(ServiceError):
    """Raised when an operation conflicts with current state (e.g. re-acknowledge)."""
