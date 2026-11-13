"""FR-000-06: identificador de correlación por petición."""

import asyncio
import re
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.types import Message

from security_anomaly.api.main import create_app
from security_anomaly.core.config import load_settings
from security_anomaly.core.request_id import (
    RequestIdMiddleware,
    is_valid_request_id,
    request_id_var,
)

SETTINGS = load_settings({"DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:1/db"})


class _Body(BaseModel):
    number: int


def _app() -> FastAPI:
    app = create_app(SETTINGS)

    @app.post("/_test/validate")
    def validate(body: _Body) -> dict[str, int]:
        return {"number": body.number}

    @app.get("/_test/boom")
    def boom() -> None:
        raise RuntimeError("fallo")

    return app


@pytest.mark.parametrize("value", ["abc-123", "A", "a.b_c-D", "x" * 64, str(uuid.uuid4())])
def test_valid_ids_are_accepted(value: str) -> None:
    assert is_valid_request_id(value)


@pytest.mark.parametrize(
    "value",
    ["", " ", "has space", "x" * 65, "abc\n", "abc\r\nSet-Cookie: x", "ñandú", "a/b", "a;b"],
)
def test_invalid_ids_are_rejected(value: str) -> None:
    assert not is_valid_request_id(value)


def test_id_is_generated_when_missing() -> None:
    response = TestClient(_app()).get("/health")
    assert uuid.UUID(response.headers["X-Request-ID"]).version == 4


def test_valid_id_is_preserved() -> None:
    response = TestClient(_app()).get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


@pytest.mark.parametrize("bad", ["has space", "x" * 65, ""])
def test_invalid_id_is_replaced(bad: str) -> None:
    response = TestClient(_app()).get("/health", headers={"X-Request-ID": bad})
    new = response.headers["X-Request-ID"]
    assert new != bad
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,64}", new)


def test_header_is_present_on_error_responses() -> None:
    client = TestClient(_app(), raise_server_exceptions=False)
    responses = [
        client.get("/no-existe", headers={"X-Request-ID": "id-404"}),
        client.post("/_test/validate", json={"number": "x"}, headers={"X-Request-ID": "id-422"}),
        client.get("/_test/boom", headers={"X-Request-ID": "id-500"}),
    ]
    for response, expected in zip(responses, ["id-404", "id-422", "id-500"], strict=True):
        assert response.headers["X-Request-ID"] == expected
        assert response.json()["request_id"] == expected


def test_context_is_set_inside_and_reset_after_the_request() -> None:
    seen: list[str | None] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(request_id_var.get())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def run() -> list[Message]:
        sent: list[Message] = []

        async def send(message: Message) -> None:
            sent.append(message)

        async def receive() -> Message:
            return {"type": "http.request"}

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"x-request-id", b"ctx-1")],
        }
        assert request_id_var.get() is None
        await RequestIdMiddleware(inner)(scope, receive, send)
        assert request_id_var.get() is None
        return sent

    sent = asyncio.run(run())
    assert seen == ["ctx-1"]
    assert (b"x-request-id", b"ctx-1") in sent[0]["headers"]
