"""D4-D8 - the Vault resolver, and the ways it must refuse.

`credential_ref` holds a vault path and never a value. That sentence is in the schema
comment, the module docstring and the master prompt, and until now it described a class
that raised. This is the code that makes it true, so these tests are mostly about the
refusals rather than the happy path: a resolver that reads a secret correctly and also
falls back to the environment when Vault is down is a resolver that stores secrets in
the environment.

The stub is deliberately hostile in places, in the shape `tests/golden/stub_simforge.py`
established: a checker that has only ever seen well-formed input proves the input was
well formed.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from broker.credentials import (
    Credential,
    EnvCredentialResolver,
    VaultCredentialResolver,
    build_resolver,
)
from broker.errors import CredentialUnavailable

# Named so it is obviously not a credential, and valued so the committed-secrets gate
# can tell. It flagged the first version of this line, which was named SECRET - that is
# exactly the shape the check exists to find, and widening the allowlist to accommodate
# a test fixture is how a scanner stops catching the real thing.
FIXTURE_VALUE = "vault-fixture-value-not-a-secret"
REF = "vault://secret/forges/capitalforge#token"

KV2_OK = {
    "data": {
        "data": {"token": FIXTURE_VALUE, "other": "unrelated"},
        "metadata": {"version": 3},
    }
}

# KV v1 answers with the value at `data`, not `data.data`. A resolver that reached for
# `data` and got a dict of secrets would return one of them by accident.
KV1_SHAPE = {"data": {"token": FIXTURE_VALUE}}


def stub_vault(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.fixture
def patch_client(monkeypatch):
    """Point the resolver's httpx client at a stub, without touching its code."""

    def install(handler):
        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", factory)

    return install


# ------------------------------------------------------------------ happy path

async def test_it_reads_a_kv2_secret(patch_client):
    """D4 - and asks the right URL, with the token in the right header."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("x-vault-token")
        return httpx.Response(200, json=KV2_OK)

    patch_client(handler)
    resolver = VaultCredentialResolver("https://vault.invalid:8200", "s.roottoken")
    credential = await resolver.resolve(REF)

    assert credential.reveal() == FIXTURE_VALUE
    assert seen["url"] == "https://vault.invalid:8200/v1/secret/data/forges/capitalforge"
    assert seen["token"] == "s.roottoken"


async def test_the_named_key_is_the_one_returned(patch_client):
    """The `#key` is not decoration: a path can hold several secrets."""
    patch_client(lambda request: httpx.Response(200, json=KV2_OK))
    resolver = VaultCredentialResolver("https://vault.invalid", "t")
    other = await resolver.resolve("vault://secret/forges/capitalforge#other")
    assert other.reveal() == "unrelated"


# --------------------------------------------------------------- strict parsing

@pytest.mark.parametrize(
    ("ref", "fragment"),
    [
        ("vault://secret/forges/capitalforge", "names no key"),
        ("vault://#token", "malformed"),
        ("vault://secret#token", "malformed"),
        ("vault://secret/path#", "malformed"),
        ("env://CAPITALFORGE_TOKEN", "not a Vault ref"),
        ("secret/forges/capitalforge#token", "not a Vault ref"),
    ],
)
def test_a_malformed_ref_is_refused_never_guessed(ref, fragment):
    """D5 - the failure mode a lenient parser creates.

    A ref with no `#key` could plausibly default to `value`, or to the only key when a
    path happens to hold one. Either turns a typo into a working setup that reads the
    wrong secret, and it works right up until a second key appears at that path.
    """
    with pytest.raises(CredentialUnavailable) as exc:
        VaultCredentialResolver.parse_ref(ref)
    assert fragment in str(exc.value)
    assert exc.value.context.get("credential_ref") == ref


# ------------------------------------------------------------- no fallback ever

@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(lambda r: httpx.Response(404, json={"errors": []}), id="missing"),
        pytest.param(lambda r: httpx.Response(403, json={"errors": []}), id="forbidden"),
        pytest.param(lambda r: httpx.Response(503, json={"errors": []}), id="sealed"),
        pytest.param(lambda r: httpx.Response(200, json=KV1_SHAPE), id="kv1_shape"),
        pytest.param(lambda r: httpx.Response(200, text="not json"), id="garbage"),
        pytest.param(lambda r: httpx.Response(200, json={"data": {"data": {}}}), id="empty"),
        pytest.param(
            lambda r: httpx.Response(200, json={"data": {"data": {"token": ""}}}),
            id="blank_value",
        ),
    ],
)
async def test_no_error_path_falls_back_to_the_environment(
    patch_client, monkeypatch, handler
):
    """D6 - the test this whole module exists for.

    The environment is primed with a value that would resolve if anything reached for
    it. Every one of these failures must raise instead. A silent fallback is how a
    deployment reads secrets from its own process environment while its configuration
    says Vault, and nothing in its logs disagrees.
    """
    monkeypatch.setenv("CAPITALFORGE_TOKEN", "the-env-value-that-must-not-be-used")
    patch_client(handler)

    resolver = VaultCredentialResolver("https://vault.invalid", "t")
    with pytest.raises(CredentialUnavailable) as exc:
        await resolver.resolve(REF)

    assert "the-env-value-that-must-not-be-used" not in str(exc.value)


async def test_an_unreachable_vault_raises_rather_than_degrading(patch_client, monkeypatch):
    """A network failure is the case an operator is most tempted to make lenient."""
    monkeypatch.setenv("CAPITALFORGE_TOKEN", "env-value")

    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    patch_client(explode)
    resolver = VaultCredentialResolver("https://vault.invalid", "t")
    with pytest.raises(CredentialUnavailable) as exc:
        await resolver.resolve(REF)
    assert "unreachable" in str(exc.value)


def test_build_resolver_has_no_vault_with_env_fallback_mode():
    """The absent capability, asserted rather than assumed.

    An operator who wants the environment backend says so in configuration, where it is
    visible in a diff, rather than getting it because Vault happened to be down.
    """
    assert isinstance(build_resolver("env"), EnvCredentialResolver)
    with pytest.raises(CredentialUnavailable):
        build_resolver("vault_with_env_fallback")
    with pytest.raises(CredentialUnavailable):
        build_resolver("")


def test_a_vault_backend_with_no_vault_refuses_at_construction(monkeypatch):
    """Fail at startup, not on the first call that was about to touch a Forge."""
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    with pytest.raises(CredentialUnavailable) as exc:
        build_resolver("vault")
    assert "VAULT_ADDR" in str(exc.value)


# --------------------------------------------------------- the token never leaks

async def test_the_vault_token_never_reaches_a_repr_a_log_or_an_exception(
    patch_client, caplog
):
    """D7, D8 - failures name the ref, which is a path, and never a value.

    The resolver holds the one credential that unlocks every other credential. A stack
    frame repr in a traceback, an `f"{resolver}"` in a debug line, or an exception
    message carrying the request URL would each put it somewhere it is kept forever.
    """
    token = "s.thisTokenMustNeverAppear"
    patch_client(lambda request: httpx.Response(500, json={"errors": ["boom"]}))
    resolver = VaultCredentialResolver("https://vault.invalid", token)

    assert token not in repr(resolver)
    assert token not in str(resolver)
    assert token not in f"{resolver}"

    with caplog.at_level(logging.DEBUG), pytest.raises(CredentialUnavailable) as exc:
        await resolver.resolve(REF)

    assert token not in str(exc.value)
    assert token not in json.dumps(exc.value.context, default=str)
    assert token not in caplog.text
    assert exc.value.context.get("credential_ref") == REF


async def test_a_resolved_credential_still_prints_redacted(patch_client):
    """The wrapper that already existed, still doing its job on this path."""
    patch_client(lambda request: httpx.Response(200, json=KV2_OK))
    resolver = VaultCredentialResolver("https://vault.invalid", "t")
    credential = await resolver.resolve(REF)

    assert isinstance(credential, Credential)
    assert FIXTURE_VALUE not in repr(credential)
    assert FIXTURE_VALUE not in f"{credential}"
    assert FIXTURE_VALUE not in str(credential)
    assert credential.reveal() == FIXTURE_VALUE
