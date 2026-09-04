"""What a Forge actually dispatches, asked of the Forge.

WHAT THIS PROVES, AND WHAT IT DOES NOT
======================================

    **It proves a handler is bound to a name.** It does not prove the handler works,
    and it does not prove it does what the name says.

    This automates the half of the conformance question that was already being done by
    hand — does the module exist at all — and does not touch the other half. A module
    that answers 200 with invented figures, or that scores a business from query
    parameters it never reads, is bound exactly like one that does its job. That class
    is found by reading the handler, and it lives in `forge_module_exclusion`, not here.

    Every report this module produces carries `SCOPE` for that reason. A conformance
    result that does not state its own limits is the same overclaim it exists to catch.

WHY THE REGISTRY IS NOT THE ANSWER
==================================

    `forge_module_registry` rows are rows a human wrote, and a Pack's
    `modules_expected` is a list a human wrote. V6 compares those two, which finds a
    typo and nothing else: if both sides are assertions, the check compares two claims.

    An adapter's `GET {base_url}/_modules` is different in one specific way. It returns
    `sorted(MODULES)` over the dispatch map, so a name is in the answer if and only if
    a handler is bound to it — you cannot add the name without adding the function.
    That is the only artefact in the path that is derived rather than asserted, and it
    is why this asks the Forge instead of asking the database.

THE NAMING AUTHORITY
====================

    The adapter's keys are the spelling of record for a Forge. The registry rows, a
    Pack's `modules_expected` and `broker.module_exclusions` must all use them or they
    do not resolve against the Forge — and an exclusion that does not resolve is an
    endpoint that quietly becomes grantable under a second name. `docs/module-exclusions.md`
    names that as the one way an exclusion can be defeated by accident; resolving
    against the manifest closes it mechanically instead of by memory.

THE PROBE IS A FALLBACK AND USUALLY CANNOT ANSWER
=================================================

    Where a Forge has an adapter but no manifest, `OPTIONS {base_url}/{module_id}`
    separates bound from unbound on some route tables: a bound path answers 405 or 200
    and an unbound one answers 404, and no handler runs either way. An authenticated
    POST would answer the same question by *executing the module*, which is not a thing
    to do to a mutating one, so OPTIONS is the only shape of probe worth having.

    It is calibrated on every run against a sentinel id that cannot exist. **If the
    sentinel does not 404, the probe reports NOT_RUN, never PASS.** That is not a
    theoretical guard: an adapter built on the CRE template routes every module through
    one `POST /{module_id}` handler, so every id matches the path template and nothing
    404s. On that shape the probe is structurally unable to tell bound from unbound,
    and saying so is the whole point. An uncalibrated probe is a green light generator.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker.config import get_settings
from broker.credentials import CredentialResolver, build_resolver
from broker.errors import CredentialUnavailable

#: Stated on every report. See the module docstring.
SCOPE = (
    "this proves a handler is bound to the name, not that it works or that it does "
    "what the name says"
)

#: The adapter's own endpoints live under `_`, which is therefore not a legal module id.
MANIFEST_PATH = "_modules"

#: The three `forge_module_registry.idempotency_support` accepts. A fourth value from
#: an adapter is a manifest this cannot read, not a new kind of module.
IDEMPOTENCY_SUPPORT = frozenset({"key", "natural", "at_most_once"})

#: How long an answer is trusted. Short, because the thing being measured is whether a
#: Forge still dispatches something, and a stale yes is the answer that misleads.
TTL = timedelta(minutes=5)

Method = Literal["adapter_manifest", "probe"]


@dataclass(frozen=True, slots=True)
class DispatchShape:
    """How a module behaves when it is called twice, as the adapter states it.

    **Weaker than the module list, and the difference matters.** A name is in
    `ForgeModules.modules` because a handler is bound to it — derived, and not
    something anyone can assert. These two fields are declared at the binding
    site: they travel with the handler rather than living in another system's
    table, and the adapter refuses at runtime a module that declares
    `is_mutating=False` and then writes, but they are still somebody's word.

    Better evidence than a registry row, which is somebody's word in a place
    where nothing can check it. Not the same thing as derived.
    """

    is_mutating: bool
    idempotency_support: str


@dataclass(frozen=True, slots=True)
class ForgeModules:
    """What a Forge answered, and how it was asked."""

    forge_id: str
    modules: frozenset[str]
    method: Method
    api_version: str
    observed_at: datetime
    entries: tuple[dict[str, Any], ...] | None = None
    """The manifest's own entries, verbatim, where it answered with objects.

    `modules` and `shapes` carry the three fields `forge_module_registry` has
    columns for. An adapter may state more - `capitalforge` states which
    operating instruction describes each module - and a reader that needs one of
    those should not have to fetch the manifest a second time to get it.

    `None` when the manifest answered with a list of names, or when the answer
    came from the probe. Not an empty tuple: nothing was stated, which is
    different from stating nothing.
    """

    shapes: dict[str, DispatchShape] | None = None
    """`is_mutating` and `idempotency_support` per module, where the adapter says.

    `None` when it does not — an older adapter answering with a list of names, or
    a probe, which can only ever establish that a path exists. `None` is not
    "no shapes"; it means the question was not answered, and the verifier leaves
    those registry columns alone rather than overwriting them with a guess.
    """

    def missing(self, wanted: set[str]) -> list[str]:
        return sorted(wanted - self.modules)

    @property
    def provenance(self) -> str:
        """What goes in `forge_module_registry.verified_against`."""
        return f"{self.forge_id}@{self.api_version} via {self.method}"


@dataclass(frozen=True, slots=True)
class Unread:
    """Why no answer could be obtained. Never a substitute for an empty answer.

    An empty `ForgeModules` would say the Forge dispatches nothing, which is a claim
    about the Forge. Being unable to ask is a fact about the connection.
    """

    forge_id: str
    reason: str


@dataclass
class _Cached:
    answer: ForgeModules
    at: datetime


_cache: dict[str, _Cached] = {}


def forget(forge_id: str | None = None) -> None:
    """Drop cached answers. `None` drops all of them."""
    if forge_id is None:
        _cache.clear()
    else:
        _cache.pop(forge_id.lower(), None)


async def _registration(conn: AsyncConnection, forge_id: str) -> dict[str, Any] | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT r.forge_id, r.base_url, r.api_version, r.auth_model,
                   c.credential_ref
            FROM forge_registry r
            LEFT JOIN forge_tenant_credential c ON c.forge_id = r.forge_id
            WHERE lower(r.forge_id) = %s
            """,
            (forge_id.lower(),),
        )
        return await cur.fetchone()


def _auth_headers(auth_model: str, secret: str) -> dict[str, str]:
    """Same two shapes the executor sends, from the same registry column."""
    if auth_model == "bearer":
        return {"Authorization": f"Bearer {secret}"}
    return {"X-Api-Key": secret}


async def read(
    conn: AsyncConnection,
    forge_id: str,
    *,
    candidates: set[str] | None = None,
    resolver: CredentialResolver | None = None,
    http: httpx.AsyncClient | None = None,
    force: bool = False,
) -> ForgeModules | Unread:
    """Ask a Forge what it dispatches. Manifest first, probe only as a fallback.

    `candidates` is what the probe would test; without it the probe is skipped, because
    a probe has nothing to enumerate — it can only answer about ids it is given.
    """
    key = forge_id.lower()
    cached = _cache.get(key)
    if cached and not force and datetime.now(UTC) - cached.at < TTL:
        return cached.answer

    row = await _registration(conn, forge_id)
    if row is None:
        return Unread(forge_id, "not in forge_registry")
    if row["credential_ref"] is None:
        return Unread(
            forge_id,
            "no tenant credential, so the Forge cannot be asked what it dispatches",
        )

    resolver = resolver or build_resolver(get_settings().credential_backend)
    try:
        credential = await resolver.resolve(row["credential_ref"])
    except CredentialUnavailable as exc:
        return Unread(forge_id, f"tenant credential unavailable: {exc}")

    headers = _auth_headers(row["auth_model"], credential.reveal())
    base = row["base_url"].rstrip("/")
    timeout = get_settings().forge_timeout_seconds

    owned = http is None
    client = http or httpx.AsyncClient()
    try:
        answer = await _via_manifest(client, base, headers, timeout, row)
        if isinstance(answer, Unread) and candidates:
            answer = await _via_probe(client, base, headers, timeout, row, candidates)
    finally:
        if owned:
            await client.aclose()

    if isinstance(answer, ForgeModules):
        _cache[key] = _Cached(answer, datetime.now(UTC))
    return answer


async def _via_manifest(
    client: httpx.AsyncClient,
    base: str,
    headers: dict[str, str],
    timeout: float,
    row: dict[str, Any],
) -> ForgeModules | Unread:
    try:
        res = await client.get(f"{base}/{MANIFEST_PATH}", headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        return Unread(row["forge_id"], f"unreachable: {exc.__class__.__name__}")

    if res.status_code in (404, 405):
        return Unread(row["forge_id"], "adapter serves no /_modules manifest")
    if res.status_code != 200:
        return Unread(row["forge_id"], f"manifest answered {res.status_code}")

    try:
        modules = res.json()["modules"]
    except (ValueError, KeyError, TypeError):
        return Unread(row["forge_id"], "manifest did not answer with a modules list")
    if not isinstance(modules, list):
        return Unread(row["forge_id"], "manifest modules is not a list")

    # Two shapes accepted. A list of names is what an adapter written before the
    # shape fields existed answers, and it is still a real answer to the question
    # this rule asks - the module list is the derived half. Reading it as an
    # error would make an older Forge unverifiable for a reason that has nothing
    # to do with whether its modules exist.
    names, shapes = _parse_modules(modules)
    entries = (
        tuple(m for m in modules if isinstance(m, dict))
        if any(isinstance(m, dict) for m in modules)
        else None
    )
    if names is None:
        return Unread(
            row["forge_id"],
            "manifest modules is neither a list of names nor a list of "
            "{module_id, is_mutating, idempotency_support}",
        )

    return ForgeModules(
        forge_id=row["forge_id"],
        modules=frozenset(names),
        method="adapter_manifest",
        api_version=row["api_version"],
        observed_at=datetime.now(UTC),
        entries=entries,
        shapes=shapes,
    )


def _parse_modules(
    modules: list[Any],
) -> tuple[list[str] | None, dict[str, DispatchShape] | None]:
    """(names, shapes). `shapes` is None when the adapter did not state them."""
    if all(isinstance(m, str) for m in modules):
        return list(modules), None

    names: list[str] = []
    shapes: dict[str, DispatchShape] = {}
    for entry in modules:
        if not isinstance(entry, dict):
            return None, None
        module_id = entry.get("module_id")
        is_mutating = entry.get("is_mutating")
        idempotency = entry.get("idempotency_support")
        if not isinstance(module_id, str) or not isinstance(is_mutating, bool):
            return None, None
        if idempotency not in IDEMPOTENCY_SUPPORT:
            return None, None
        names.append(module_id)
        shapes[module_id] = DispatchShape(is_mutating, idempotency)
    return names, shapes


async def _via_probe(
    client: httpx.AsyncClient,
    base: str,
    headers: dict[str, str],
    timeout: float,
    row: dict[str, Any],
    candidates: set[str],
) -> ForgeModules | Unread:
    """OPTIONS per candidate, calibrated against an id that cannot exist.

    Nothing here executes a module. OPTIONS is answered by the route table, not by the
    handler, which is the only reason probing a mutating module is defensible at all.
    """
    sentinel = f"_probe_{uuid.uuid4().hex}"
    try:
        calibration = await client.options(f"{base}/{sentinel}", headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        return Unread(row["forge_id"], f"unreachable: {exc.__class__.__name__}")

    if calibration.status_code != 404:
        return Unread(
            row["forge_id"],
            f"probe is not calibrated: an id that cannot exist answered "
            f"{calibration.status_code} rather than 404, so a bound module and an "
            "unbound one are indistinguishable here. A catch-all dispatcher has this "
            "shape. Serve /_modules instead",
        )

    found: set[str] = set()
    for module_id in sorted(candidates):
        try:
            res = await client.options(f"{base}/{module_id}", headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:
            return Unread(row["forge_id"], f"unreachable: {exc.__class__.__name__}")
        if res.status_code != 404:
            found.add(module_id)

    return ForgeModules(
        forge_id=row["forge_id"],
        modules=frozenset(found),
        method="probe",
        api_version=row["api_version"],
        observed_at=datetime.now(UTC),
    )
