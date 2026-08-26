"""Domain errors.

The business layer raises these; it never imports ``fastapi`` or constructs an
``HTTPException``. The API layer translates them to status codes in exactly one
place — ``api.app.register_domain_error_handlers`` — which is what keeps the
transport boundary visible and keeps HTTP semantics out of the domain.
"""


class JustHireMeError(Exception):
    """Base class for domain-level errors."""


class NotFoundError(JustHireMeError):
    """The requested entity does not exist. -> 404"""


class ValidationError(JustHireMeError):
    """The request is malformed or missing required input. -> 400"""


class UnprocessableError(JustHireMeError):
    """Well-formed, but the domain refuses it (wrong kind, unmet precondition). -> 422"""


class ConflictError(JustHireMeError):
    """The entity is in a state that forbids this operation. -> 409"""


class LeadNotFoundError(NotFoundError):
    pass


class ProfileNotFoundError(NotFoundError):
    pass


class IngestionError(JustHireMeError):
    pass


class ScoringError(JustHireMeError):
    pass


class GenerationError(JustHireMeError):
    pass


class DiscoveryError(JustHireMeError):
    pass


class ConfigurationError(JustHireMeError):
    pass


#: Domain error -> HTTP status. The API layer owns this mapping, not the domain.
HTTP_STATUS_BY_ERROR: dict[type[JustHireMeError], int] = {
    NotFoundError: 404,
    ValidationError: 400,
    UnprocessableError: 422,
    ConflictError: 409,
}


def http_status_for(error: BaseException) -> int:
    """Best-matching status for a domain error; 500 for anything unmapped."""
    for error_type in type(error).__mro__:
        if error_type in HTTP_STATUS_BY_ERROR:
            return HTTP_STATUS_BY_ERROR[error_type]
    return 500
