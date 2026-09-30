from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Raised by services for validation failures. Mapped to HTTP 422 below."""

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        self.code = code
        self.message = message
        self.field = field
        super().__init__(message)


class NotFoundError(DomainError):
    """Mapped to HTTP 404. `code` defaults to "not_found" per docs/04-api.md."""

    def __init__(self, message: str, code: str = "not_found") -> None:
        super().__init__(code, message)


class ConflictError(DomainError):
    """Mapped to HTTP 409. `code` defaults to "conflict" per docs/04-api.md."""

    def __init__(self, message: str, code: str = "conflict") -> None:
        super().__init__(code, message)


_STATUS_BY_TYPE = {
    NotFoundError: 404,
    ConflictError: 409,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status_code = _STATUS_BY_TYPE.get(type(exc), 422)
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": exc.code, "message": exc.message, "field": exc.field}},
        )
