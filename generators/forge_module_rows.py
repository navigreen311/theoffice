"""`forge_module_registry` rows, derived from two sources that must agree.

WHY THIS EXISTS
===============

`forge_module_registry` rows have always been *rows a human typed* - the phrase is
`docs/forge-adapter.md`'s own. That is the reason V6 compares two claims and can only
find a typo; it is why `property_lookup` sat recorded `is_mutating: TRUE` for months
while being a search; and it is why V31 will not PASS on a
`verification_method = 'hand'` row at all.

Nothing produced these rows. So *"never hand-write data a generator is supposed to
produce"* had no generator to point at, and every new Forge paid the same price.

WHAT IT DERIVES FROM, AND WHY IT IS TWO SOURCES RATHER THAN ONE
==============================================================

    the adapter's dispatch map   `sorted(MODULES)` and the shape stated at each binding.
                                 DERIVED: a name is there if and only if a handler is
                                 bound. This is the naming authority - spelling and
                                 shape both come from here and from nowhere else.

    the Pack's modules_expected  a human's declaration that The Office intends to make
                                 this module grantable. DECLARED.

**A row is written only where both agree**, and the two disagreements are reported
rather than resolved:

    dispatched, not declared     no row. `scripts/verify_forge_modules.py` states the
                                 principle and this generator keeps it: *"a Forge does
                                 not enlarge its own agent-facing surface."* Deriving
                                 rows from the adapter alone would mean adding a handler
                                 is enough to make it grantable, which inverts the point.

    declared, not dispatched     no row, and this is the `lender_match` shape. The
                                 Burkham Pack declared twelve modules, three did not
                                 exist, and V6 passed on all twelve because somebody had
                                 written twelve rows. A generator that wrote a row for a
                                 declared-but-absent name would reproduce that exactly.

So: the human decides *whether*, the adapter decides *what*. Neither can act alone, and
the artefact records which half came from where.

WHAT A ROW FROM HERE MEANS, AND WHAT IT DOES NOT
================================================

`verification_method` is `adapter_manifest` and `verified_at` is set, because the shape
was read from a dispatch map. That is the same standard `scripts/verify_forge_modules.py`
applies, and it is deliberately the same: a row is either evidence or a claim, and there
is no third grade for "generated carefully".

It still does not mean the handler works, or that it does what the name says.
`readiness_score` is bound, answers 200, mutates nothing, and scores a business from
query parameters it never reads. Nothing here will ever find that; reading the handler
will, and the finding goes in `forge_module_exclusion`.

**`apply()` never deletes.** `agent_forge_grant` has a foreign key into this table, and
removing the row a live grant points at is not a thing a generator does as a side effect.
A module that has stopped being dispatched is reported; somebody revokes the grant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from psycopg import AsyncConnection

#: The three `forge_module_registry.idempotency_support` accepts, restated from
#: `broker/forge_modules.IDEMPOTENCY_SUPPORT`. Restated rather than imported because a
#: generator importing the broker inverts the dependency the rest of this package keeps;
#: `test_idempotency_values_match_the_broker` fails if the two ever differ.
IDEMPOTENCY_SUPPORT = frozenset({"key", "natural", "at_most_once"})


@dataclass(frozen=True, slots=True)
class ModuleRow:
    """One `forge_module_registry` row, with its two halves labelled."""

    forge_id: str
    module_id: str
    module_name: str
    is_mutating: bool
    idempotency_support: str
    compliance_flags_implied: tuple[str, ...]
    verified_against: str
    """`{forge_id}@{api_version} via adapter_manifest` - the same string
    `broker.forge_modules.ForgeModules.provenance` builds, so a row written here and a
    row stamped by the verifier are indistinguishable afterwards, which they should be."""


@dataclass(frozen=True, slots=True)
class ModuleRows:
    """What to write, and the two disagreements that produced no row."""

    forge_id: str
    api_version: str
    rows: tuple[ModuleRow, ...] = ()
    dispatched_not_declared: tuple[str, ...] = ()
    declared_not_dispatched: tuple[str, ...] = ()
    rejected: tuple[str, ...] = field(default=())
    """Entries the adapter stated that this generator will not turn into a row -
    an idempotency value outside the three, or a reserved `_` prefix. Not silently
    dropped: a manifest this cannot read is a finding about the manifest."""

    @property
    def blocked(self) -> str | None:
        """Why nothing should be written, or None.

        A rejected entry blocks the whole run rather than the one row. A manifest with an
        unreadable entry is a manifest whose author and this generator disagree about the
        contract, and writing the readable subset would leave that disagreement recorded
        nowhere while looking like a successful run.
        """
        if self.rejected:
            return (
                f"{len(self.rejected)} manifest entr"
                f"{'y is' if len(self.rejected) == 1 else 'ies are'} unreadable: "
                f"{'; '.join(self.rejected)}. Fix the adapter's declaration; this "
                "generator will not write the rest around it."
            )
        return None


def generate(
    forge_id: str,
    api_version: str,
    manifest: dict[str, Any],
    declared: set[str],
    *,
    module_names: dict[str, str] | None = None,
    compliance_flags: dict[str, tuple[str, ...]] | None = None,
) -> ModuleRows:
    """Pure. `manifest` is the adapter's `/_modules` answer, verbatim.

    `declared` is the Pack's `modules_expected` for this Forge - the human half.

    `compliance_flags_implied` is neither derived nor declared by the adapter, and it is
    not guessed here. It is passed in, defaulting to empty, because
    `broker/compliance_couplings.py` records what happens when it is written in one pass
    for the wrong reason: `record_consent` was given
    `per_connection_authorization_required`, which exists, resolves against the Pack, and
    passes every check there is - and is GLBA, on a module that is not. A wrong flag that
    resolves is worse than an absent one, so absent is the default.
    """
    entries = manifest.get("modules")
    if not isinstance(entries, list):
        return ModuleRows(
            forge_id=forge_id,
            api_version=api_version,
            rejected=("manifest has no 'modules' list",),
        )

    names = module_names or {}
    flags = compliance_flags or {}
    provenance = f"{forge_id}@{api_version} via adapter_manifest"

    rows: list[ModuleRow] = []
    dispatched: set[str] = set()
    rejected: list[str] = []

    for entry in entries:
        if not isinstance(entry, dict):
            rejected.append(f"{entry!r} is not an object; serve the three-field shape")
            continue
        module_id = entry.get("module_id")
        is_mutating = entry.get("is_mutating")
        idempotency = entry.get("idempotency_support")
        if not isinstance(module_id, str) or not module_id:
            rejected.append(f"{entry!r} has no module_id")
            continue
        if module_id.startswith("_"):
            rejected.append(
                f"{module_id!r} uses the reserved '_' prefix, which belongs to the "
                "adapter's own endpoints"
            )
            continue
        if not isinstance(is_mutating, bool):
            rejected.append(f"{module_id}: is_mutating is not a boolean")
            continue
        if idempotency not in IDEMPOTENCY_SUPPORT:
            rejected.append(
                f"{module_id}: idempotency_support {idempotency!r} is not one of "
                f"{sorted(IDEMPOTENCY_SUPPORT)}"
            )
            continue

        dispatched.add(module_id)
        if module_id not in declared:
            continue
        rows.append(
            ModuleRow(
                forge_id=forge_id,
                module_id=module_id,
                module_name=names.get(module_id) or module_id.replace("_", " ").title(),
                is_mutating=is_mutating,
                idempotency_support=idempotency,
                compliance_flags_implied=flags.get(module_id, ()),
                verified_against=provenance,
            )
        )

    return ModuleRows(
        forge_id=forge_id,
        api_version=api_version,
        rows=tuple(sorted(rows, key=lambda r: r.module_id)),
        dispatched_not_declared=tuple(sorted(dispatched - declared)),
        declared_not_dispatched=tuple(sorted(declared - dispatched)),
        rejected=tuple(rejected),
    )


async def apply(
    conn: AsyncConnection, generated: ModuleRows, *, confirmed: bool = False
) -> list[str]:
    """Write the rows. Refuses without confirmation; never deletes; returns what changed.

    Idempotent by construction rather than by a bolted-on `ON CONFLICT`: the primary key
    is `(forge_id, module_id)` and the row's whole content is derived from the manifest,
    so a second run over an unchanged manifest computes the same values and updates them
    to what they already are.
    """
    if not confirmed:
        raise ValueError(
            "apply() writes rows that make modules grantable and will not run without "
            "confirmed=True. Call generate() and read its report first."
        )
    blocked = generated.blocked
    if blocked is not None:
        raise ValueError(blocked)

    now = datetime.now(UTC)
    written: list[str] = []
    async with conn.cursor() as cur:
        for row in generated.rows:
            await cur.execute(
                """
                INSERT INTO forge_module_registry
                  (forge_id, module_id, module_name, idempotency_support, is_mutating,
                   compliance_flags_implied, api_version_introduced,
                   verified_at, verified_against, verification_method)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'adapter_manifest')
                ON CONFLICT (forge_id, module_id) DO UPDATE SET
                  module_name              = EXCLUDED.module_name,
                  idempotency_support      = EXCLUDED.idempotency_support,
                  is_mutating              = EXCLUDED.is_mutating,
                  compliance_flags_implied = EXCLUDED.compliance_flags_implied,
                  verified_at              = EXCLUDED.verified_at,
                  verified_against         = EXCLUDED.verified_against,
                  verification_method      = 'adapter_manifest'
                """,
                (
                    row.forge_id,
                    row.module_id,
                    row.module_name,
                    row.idempotency_support,
                    row.is_mutating,
                    list(row.compliance_flags_implied),
                    generated.api_version,
                    now,
                    row.verified_against,
                ),
            )
            written.append(f"{row.forge_id}/{row.module_id}")
    return written
