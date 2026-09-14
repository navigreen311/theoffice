"""The Idempotency-Key survives the hop from The Office to FunnelForge.

WHY THIS TEST EXISTS, AND WHY IT IS THE FIRST OF ITS KIND
========================================================

    `forge_module_registry.idempotency_support` is a hand-written string in THIS
    repository describing the behaviour of code in ANOTHER one. Sixteen of the twenty
    registered modules carry `verification_method = 'hand'`, and `ModuleShape.is_evidence`
    already says what that means - *"`hand` is a claim. The other two were obtained from
    the Forge."* **Nothing acts on the distinction, and nothing tests any of the sixteen.**

    Seven of them were wrong in both directions at once. They said `at_most_once` after
    FunnelForge shipped an idempotency key (PR #160, 12 September); had they simply been
    flipped to `key`, they would then have been wrong the other way, because this
    adapter read the header and dropped it - the upstream request carried
    `Authorization` and nothing else, so every send reached FunnelForge unkeyed.

    **`key` is a claim about the call path, not about the Forge.** FunnelForge's store
    branches on the header's presence: a caller that supplies no key "never reaches this
    file" and a repeat sends a second email. So the declaration is only true while the
    forwarding holds, and the forwarding is one line that nothing else would notice
    losing.

WHAT THIS ASSERTS, AND WHAT IT CANNOT
=====================================

    It asserts the header leaves this adapter on the upstream request, with the value
    that arrived. That is the half this repository owns and the half that broke.

    **It does not assert FunnelForge honours it.** Nothing in this repository can:
    `docs/forge-adapter.md` trap #4 records that the CapitalForge adapter's unit tests
    asserted the request the adapter *built* and could therefore only confirm the
    assumption they were written from. This test performs the call against a recording
    transport, so it inspects a real outbound request rather than an intention - but the
    other side of the hop is still evidence gathered by reading `idempotency-store.ts`,
    cited in `adapters/funnelforge/modules.py`, and it is a claim until FunnelForge's own
    suite is reachable from here.
"""

from __future__ import annotations

import httpx
import pytest

from adapters.funnelforge.app import HttpUpstream, upstream_base
from adapters.funnelforge.upstream import UpstreamCall
from broker.executor import HEADER_IDEMPOTENCY

KEY = "office-derived-key-7f3a91"


def _recording_client(seen: dict[str, httpx.Headers]) -> httpx.AsyncClient:
    """A client that records the outbound request instead of performing it."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        return httpx.Response(200, json={"ok": True})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_the_idempotency_key_reaches_funnelforge() -> None:
    """The header The Office set arrives on the upstream request, unchanged.

    This is the assertion that makes `idempotency_support="key"` a true statement about
    this call path rather than about FunnelForge alone.
    """
    seen: dict[str, httpx.Headers] = {}
    async with _recording_client(seen) as client:
        upstream = HttpUpstream(client, "tenant-token", KEY)
        await upstream(UpstreamCall(method="POST", path="/api/emails/send", body={}))

    assert HEADER_IDEMPOTENCY in seen["headers"], (
        f"{HEADER_IDEMPOTENCY} did not leave the adapter. FunnelForge branches on this "
        "header's PRESENCE: without it the send path never reaches its idempotency "
        "store and a repeat sends a second email. The registry declares these modules "
        "`key`, and that declaration is only true while this header is forwarded."
    )
    assert seen["headers"][HEADER_IDEMPOTENCY] == KEY, (
        "the key was forwarded but altered. A key that does not match the one The "
        "Office derived claims a different slot in FunnelForge's store, so a retry "
        "carrying the original key would not be recognised as a repeat."
    )
    assert seen["headers"]["Authorization"] == "Bearer tenant-token", (
        "the brokered credential stopped travelling when the header was added"
    )


async def test_no_key_means_no_header_rather_than_an_empty_one() -> None:
    """An absent key sends no header at all.

    `Idempotency-Key: ""` is PRESENT. FunnelForge would take it as a real key, claim a
    slot under the empty string, and then answer every other unkeyed send from that same
    record - which is worse than not participating, because it would deduplicate calls
    that have nothing to do with each other.
    """
    seen: dict[str, httpx.Headers] = {}
    async with _recording_client(seen) as client:
        upstream = HttpUpstream(client, "tenant-token", None)
        await upstream(UpstreamCall(method="POST", path="/api/emails/send", body={}))

    assert HEADER_IDEMPOTENCY not in seen["headers"], (
        "an empty or absent key still sent the header. FunnelForge branches on presence, "
        "so this would claim a store slot under a meaningless key and dedupe unrelated "
        "sends against it."
    )


@pytest.mark.parametrize("blank", ["", None])
async def test_a_blank_key_is_treated_as_absent(blank: str | None) -> None:
    """Empty string and None behave identically, because both mean 'no key derived'."""
    seen: dict[str, httpx.Headers] = {}
    async with _recording_client(seen) as client:
        upstream = HttpUpstream(client, "tenant-token", blank)
        await upstream(UpstreamCall(method="GET", path="/api/funnels", body=None))

    assert HEADER_IDEMPOTENCY not in seen["headers"]


def test_the_upstream_base_is_not_a_host_port() -> None:
    """Guards the transport this test mocks.

    If `upstream_base()` ever became a host port, the recording transport above would
    still pass while the real adapter talked to something else. The base is service DNS
    because FunnelForge's fifteen containers publish no ports.
    """
    assert "://" in upstream_base(), upstream_base()
