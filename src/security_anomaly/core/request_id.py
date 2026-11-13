"""Identificador de petición y log por petición (FR-000-05, FR-000-06).

Middleware ASGI puro (no ``BaseHTTPMiddleware``): conserva bien los ``ContextVar`` (research R5).
"""

import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER_NAME = "X-Request-ID"
_VALID = re.compile(r"[A-Za-z0-9._-]{1,64}")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("security_anomaly.request")


def is_valid_request_id(value: str) -> bool:
    """Solo caracteres ``[A-Za-z0-9._-]`` y entre 1 y 64 de longitud (sin saltos de línea)."""
    return _VALID.fullmatch(value) is not None


def _incoming_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            return str(value.decode("latin-1"))
    return None


class RequestIdMiddleware:
    """Asigna ``request_id`` a cada petición HTTP, lo devuelve en la respuesta y lo registra."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _incoming_id(scope)
        request_id = incoming if incoming and is_valid_request_id(incoming) else str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[HEADER_NAME] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            fields: dict[str, Any] = {
                "method": scope.get("method", ""),
                "path": scope.get("path", ""),  # sin query string: puede contener secretos
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            logger.info("request", extra={"fields": fields})
            request_id_var.reset(token)
