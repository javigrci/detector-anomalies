"""Sobre de error único y manejadores globales (FR-000-10, SPEC §6.2)."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from security_anomaly.core.request_id import request_id_var

logger = logging.getLogger(__name__)

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    503: "service_unavailable",
}


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any]


def current_request_id(request: Request | None = None) -> str:
    """Identificador de la petición actual: contexto, estado de la petición o 'unknown'."""
    value = request_id_var.get()
    if value is None and request is not None:
        value = request.scope.get("state", {}).get("request_id")
    return value or "unknown"


def error_response(
    request: Request | None,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = current_request_id(request)
    envelope = ErrorEnvelope(
        code=code, message=message, request_id=request_id, details=details or {}
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(),
        headers={"X-Request-ID": request_id},
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    message = str(exc.detail) if isinstance(exc.detail, str) else "Error de la solicitud."
    return error_response(request, exc.status_code, code, message)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = [
        {"loc": [str(part) for part in err["loc"]], "type": err["type"], "msg": err["msg"]}
        for err in exc.errors()
    ]
    return error_response(
        request, 422, "validation_error", "La solicitud no es válida.", {"errors": errors}
    )


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Este manejador corre fuera del middleware: se restablece el contexto para el log.
    token = request_id_var.set(current_request_id(request))
    try:
        logger.error("unhandled_exception", exc_info=exc)
    finally:
        request_id_var.reset(token)
    return error_response(request, 500, "internal_error", "Error interno del servidor.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
