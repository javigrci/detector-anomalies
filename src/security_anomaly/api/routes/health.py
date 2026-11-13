"""Sondas de salud y disponibilidad (FR-000-07, FR-000-08, FR-000-09).

Quedan fuera del prefijo /api/v1 y son públicas (SPEC §6).
"""

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from security_anomaly.api.errors import ErrorEnvelope, error_response
from security_anomaly.storage.database import check_database

router = APIRouter(tags=["sondas"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadyChecks(BaseModel):
    database: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    checks: ReadyChecks


@router.get("/health", summary="Proceso vivo (no depende de la base de datos)")
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Listo para recibir tráfico (base de datos accesible)",
    responses={503: {"model": ErrorEnvelope, "description": "No disponible"}},
)
def ready(request: Request) -> ReadyResponse | JSONResponse:
    # Función `def`: FastAPI la ejecuta en un hilo y no bloquea el event loop.
    if check_database(request.app.state.engine):
        return ReadyResponse(status="ready", checks=ReadyChecks(database="ok"))
    return error_response(
        request,
        503,
        "not_ready",
        "El servicio no está listo.",
        {"checks": {"database": "unavailable"}},
    )
