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
    """Placeholder for Phase 0.3.

    Deliberately raises rather than falling back to the env resolver. A silent
    fallback is how a production deployment ends up reading secrets from the
    process environment while its config says Vault.
    """

    def __init__(self, addr: str, token: str) -> None:
        self._addr = addr
        self._token = token

    async def resolve(self, credential_ref: str) -> Credential:
        raise CredentialUnavailable(
            "Vault backend not implemented - Phase 0.3 requires a Vault instance",
            credential_ref=credential_ref,
        )


def build_resolver(backend: str) -> CredentialResolver:
    if backend == "env":
        return EnvCredentialResolver()
    if backend == "vault":
        addr = os.environ.get("VAULT_ADDR", "")
        token = os.environ.get("VAULT_TOKEN", "")
        return VaultCredentialResolver(addr, token)
    raise CredentialUnavailable(f"unknown credential backend: {backend!r}")
