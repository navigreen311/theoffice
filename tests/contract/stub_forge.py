"""An in-process stub Forge.

Runs through `httpx.ASGITransport` — no ports, no sleeps, no flaky teardown. It
records every request it receives so tests can assert on what the broker actually
sent, rather than on what the broker believes it sent.

It also exposes `audit_count_at_request`, a callback the test wires to count
`audit_log` rows at the moment the Forge is reached. That is the only honest way
to assert "audit was written BEFORE the call" — checking afterwards cannot
distinguish before from after.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse


@dataclass
class RecordedRequest:
    module_id: str
    headers: dict[str, str]
    body: Any
    audit_rows_at_request: int | None = None


@dataclass
class StubForge:
    """Configurable fake Forge."""

    status_code: int = 200
    response_body: dict[str, Any] = field(default_factory=lambda: {"ok": True})
    forge_request_id: str = "forge-req-001"
    requests: list[RecordedRequest] = field(default_factory=list)
    audit_counter: Callable[[], int] | None = None
    fail_with: Exception | None = None

    @property
    def last(self) -> RecordedRequest:
        assert self.requests, "stub forge received no requests"
        return self.requests[-1]

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def build_app(self) -> FastAPI:
        app = FastAPI()

        @app.post("/{module_id}")
        async def handle(module_id: str, request: Request) -> Response:
            if self.fail_with is not None:
                raise self.fail_with

            try:
                body = await request.json()
            except Exception:
                body = None

            count = self.audit_counter() if self.audit_counter else None
            self.requests.append(
                RecordedRequest(
                    module_id=module_id,
                    headers=dict(request.headers),
                    body=body,
                    audit_rows_at_request=count,
                )
            )
            return JSONResponse(
                self.response_body,
                status_code=self.status_code,
                headers={"X-Forge-Request-Id": self.forge_request_id},
            )

        return app
