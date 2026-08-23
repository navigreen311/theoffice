"""Credential resolution.

`forge_tenant_credential.credential_ref` holds a **vault path, never a secret**.
This module is the only place a credential value exists in the process, and the
value must not escape it: not into a log line, not into an exception message, not
into an audit `subject`, not into a ledger row, not into a response body.

`Credential` wraps the value so that an accidental f-string or repr in a log
statement prints a redaction rather than the secret. That is a guardrail against
the realistic mistake, not a security boundary - anything holding the object can
still call `.reveal()`. The point is that revealing it has to be deliberate and
greppable.
"""

from __future__ import annotations

import os
from typing import Protocol

import httpx

from broker.errors import CredentialUnavailable


class Credential:
    """A resolved secret. Prints redacted; `reveal()` is the only way out."""

    __slots__ = ("_value", "ref")

    def __init__(self, ref: str, value: str) -> None:
        self.ref = ref
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"<Credential ref={self.ref!r} value=REDACTED>"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:
        return self.__repr__()


class CredentialResolver(Protocol):
    """Swapping the backend must not touch the call path.

    Master prompt 1.6: migrating a Forge from a brokered tenant key to a native
    per-agent credential is configuration, not rearchitecture. That holds only if
    every caller depends on this protocol rather than on a concrete backend.
    """

    async def resolve(self, credential_ref: str) -> Credential: ...


class EnvCredentialResolver:
    """Development backend. Reads `credential_ref` from the environment.

    A ref of `env://CAPITALFORGE_TOKEN` reads `CAPITALFORGE_TOKEN`. Refs that are
    not `env://` are rejected rather than guessed at - a resolver that silently
    accepted a vault path in development would make a misconfiguration look like
    a working setup until it reached an environment that mattered.
    """

    scheme = "env://"

    async def resolve(self, credential_ref: str) -> Credential:
        if not credential_ref.startswith(self.scheme):
            raise CredentialUnavailable(
                f"EnvCredentialResolver only handles {self.scheme!r} refs",
                credential_ref=credential_ref,
            )
        var = credential_ref[len(self.scheme) :]
        value = os.environ.get(var)
        if not value:
            raise CredentialUnavailable(
                "credential ref did not resolve", credential_ref=credential_ref
            )
        return Credential(credential_ref, value)


class VaultCredentialResolver:
    """HashiCorp Vault, KV version 2.

    `forge_tenant_credential.credential_ref` holds a vault path and never a value, and
    this is the resolver that makes that split real rather than aspirational.

    Refs look like `vault://secret/forges/capitalforge#token`:

        vault://<mount>/<path>#<key>

    **Parsed strictly, never guessed at.** A ref missing its `#key` is refused rather
    than defaulting to something like `value` or to the single key when there happens to
    be one - a resolver that guesses turns a typo into a working setup that reads the
    wrong secret, and the day it matters is the day two secrets live at one path.

    **There is no fallback to the environment, on any path.** Not on a malformed ref,
    not on a 404, not on a network error, not on a Vault that is sealed. A silent
    fallback is how a production deployment ends up reading secrets from its own process
    environment while its configuration says Vault, and nothing in its logs disagrees.

    The Vault token is held here and appears nowhere else: not in a log line, not in an
    exception message, not in `__repr__`. Failures name the **ref**, which is a path and
    is safe to print, and never the value.
    """

    scheme = "vault://"

    def __init__(
        self,
        addr: str,
        token: str,
        *,
        namespace: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        if not addr:
            raise CredentialUnavailable(
                "VAULT_ADDR is empty. Refusing to start with a Vault backend and no "
                "Vault - the alternative is a resolver that fails on first use, in "
                "production, on a call that was about to touch a Forge."
            )
        if not token:
            raise CredentialUnavailable("VAULT_TOKEN is empty")
        self._addr = addr.rstrip("/")
        self._token = token
        self._namespace = namespace
        self._timeout = timeout

    def __repr__(self) -> str:
        # The token must not reach a log line through a stack frame repr.
        return f"<VaultCredentialResolver addr={self._addr!r} token=REDACTED>"

    __str__ = __repr__

    @staticmethod
    def parse_ref(credential_ref: str) -> tuple[str, str, str]:
        """`vault://mount/path#key` -> (mount, path, key). Strict on every part."""
        if not credential_ref.startswith(VaultCredentialResolver.scheme):
            raise CredentialUnavailable(
                f"not a Vault ref; expected {VaultCredentialResolver.scheme!r}",
                credential_ref=credential_ref,
            )
        body = credential_ref[len(VaultCredentialResolver.scheme) :]
        if "#" not in body:
            raise CredentialUnavailable(
                "Vault ref names no key. Use vault://<mount>/<path>#<key> - a resolver "
                "that guessed the key would read the wrong secret the first time two "
                "of them share a path.",
                credential_ref=credential_ref,
            )
        location, _, key = body.partition("#")
        mount, _, path = location.partition("/")
        if not mount or not path or not key:
            raise CredentialUnavailable(
                "Vault ref is malformed; expected vault://<mount>/<path>#<key>",
                credential_ref=credential_ref,
            )
        return mount, path, key

    async def resolve(self, credential_ref: str) -> Credential:
        mount, path, key = self.parse_ref(credential_ref)
        url = f"{self._addr}/v1/{mount}/data/{path}"
        headers = {"X-Vault-Token": self._token}
        if self._namespace:
            headers["X-Vault-Namespace"] = self._namespace

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            # `type(exc).__name__` and not `str(exc)`: httpx puts the request URL in
            # the message, and a URL that has ever been built with a token in a query
            # string would land in a log. It never is here, and this does not depend
            # on that staying true.
            raise CredentialUnavailable(
                f"Vault is unreachable ({type(exc).__name__})",
                credential_ref=credential_ref,
            ) from exc

        if response.status_code == 403:
            raise CredentialUnavailable(
                "Vault refused the token for this path",
                credential_ref=credential_ref,
            )
        if response.status_code == 404:
            raise CredentialUnavailable(
                "no secret at this Vault path", credential_ref=credential_ref
            )
        if response.status_code >= 400:
            raise CredentialUnavailable(
                f"Vault answered {response.status_code}",
                credential_ref=credential_ref,
            )

        try:
            data = response.json()["data"]["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise CredentialUnavailable(
                "Vault answered in a shape this resolver does not recognise; KV v2 is "
                "required and KV v1 responds differently",
                credential_ref=credential_ref,
            ) from exc

        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise CredentialUnavailable(
                f"the secret at this path has no non-empty {key!r} key",
                credential_ref=credential_ref,
            )
        return Credential(credential_ref, value)


def build_resolver(backend: str) -> CredentialResolver:
    """One backend, chosen once, with no path that quietly becomes another.

    There is deliberately no "vault, falling back to env" mode. An operator who wants
    the environment backend says so in configuration, where it is visible, rather than
    getting it because Vault happened to be down.
    """
    if backend == "env":
        return EnvCredentialResolver()
    if backend == "vault":
        return VaultCredentialResolver(
            os.environ.get("VAULT_ADDR", ""),
            os.environ.get("VAULT_TOKEN", ""),
            namespace=os.environ.get("VAULT_NAMESPACE") or None,
        )
    raise CredentialUnavailable(f"unknown credential backend: {backend!r}")
