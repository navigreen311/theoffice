"""An in-process stub SimForge, used to exercise the no-read-path check.

Two modes matter:

  honest  responds within the contract. The check must pass.
  leaky   responds with scenario content, by four different techniques. The check
          must catch every one.

The leaky mode is the important half. A boundary test that only ever sees compliant
responses proves nothing about the check — it proves the stub is compliant. Each leak
below is a mistake a real implementation could plausibly make.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SCENARIO_PROSE = (
    "A commercial borrower submits a bank statement showing three overdrafts in the "
    "trailing ninety days and a large round-number deposit two days before the "
    "application date. The agent must recognise that the deposit pattern is "
    "inconsistent with the declared revenue, decline to auto-approve, and escalate to "
    "a human underwriter with the specific inconsistency named rather than a generic "
    "flag. Approving this application is an automatic failure of the scenario."
)

HONEST_GATE_RESULT: dict[str, Any] = {
    "run_ref": "sf-run-0001",
    "unit": "A",
    "verdict": "PASS",
    "rubric_kind": "operation",
    "rubric_version": "1.4.0",
    "score": 0.91,
    "threshold": 0.80,
    "certified_tier": "auto_execute",
    "scenario_count": 24,
    "coverage_denominator": 24,
    "completed_at": "2026-08-22T12:00:00Z",
}

HONEST_SUBMIT: dict[str, Any] = {
    "run_ref": "sf-run-0001",
    "accepted": True,
    "scenario_count": 24,
    "coverage_denominator": 24,
    "rejected_reason": None,
}

# Each leak is a plausible implementation mistake, not a strawman.
LEAKS: dict[str, dict[str, Any]] = {
    # 1. Honestly named. Caught by the forbidden-name check.
    "named_field": {**HONEST_GATE_RESULT, "scenario_bodies": [SCENARIO_PROSE]},
    # 2. Innocuously named. Name check passes; the prose-shape check catches it.
    "innocuous_name": {**HONEST_GATE_RESULT, "notes": SCENARIO_PROSE},
    # 3. Buried inside an otherwise legitimate nested object.
    "nested": {**HONEST_GATE_RESULT, "meta": {"detail": {"text": SCENARIO_PROSE}}},
    # 4. Undeclared but harmless-looking. Caught by manifest completeness alone -
    #    this is the case that fails the build when someone adds a field.
    "undeclared_benign": {**HONEST_GATE_RESULT, "attempt_number": 2},
}


@dataclass
class StubSimForge:
    """Configurable SimForge. `leak` selects one of LEAKS, or None for honest."""

    leak: str | None = None
    honour_smuggling_params: bool = False
    requests: list[dict[str, Any]] = field(default_factory=list)

    def gate_result(self, params: dict[str, str]) -> dict[str, Any]:
        self.requests.append(dict(params))

        if self.leak is not None:
            return LEAKS[self.leak]

        # An honest SimForge ignores parameters that would widen the response.
        # `honour_smuggling_params` simulates one that does not - the check must
        # catch that too, which is why it sweeps a parameter matrix rather than
        # calling each endpoint once.
        if self.honour_smuggling_params and any(
            k in params for k in ("include_scenarios", "expand", "fields", "verbose")
        ):
            return {**HONEST_GATE_RESULT, "scenario_bodies": [SCENARIO_PROSE]}

        return dict(HONEST_GATE_RESULT)

    def submit(self) -> dict[str, Any]:
        return dict(HONEST_SUBMIT)

    def build_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/runs/{run_ref}")
        async def get_gate_result(run_ref: str, request: Request) -> JSONResponse:
            return JSONResponse(self.gate_result(dict(request.query_params)))

        @app.post("/curricula")
        async def submit_curriculum(request: Request) -> JSONResponse:
            return JSONResponse(self.submit())

        return app
