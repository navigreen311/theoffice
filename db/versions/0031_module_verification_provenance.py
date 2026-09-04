"""Where a `forge_module_registry` row came from.

    A row in this table is a claim until something checked it.

`forge_module_exclusion` has carried its evidence since 0030 — the file and symbol
that justify each exclusion, reviewable in a diff by whoever decides whether it still
holds. The registry never got that, and the registry is the table `agent_forge_grant`
has a foreign key into. A grant resolves against a row somebody typed.

Three columns, so a reader can tell a checked row from an asserted one:

  verified_at          when the Forge last answered about this module
  verified_against     what answered, and how: `cre-forge@1.4.0 via adapter_manifest`
  verification_method  adapter_manifest | probe | hand

`hand` is the default and is not a slur on the row. It is what every existing row is,
and saying so is the point: a check that counts a hand-written row as evidence of
conformance is comparing two claims and calling it verification.

WHY THE DEFAULT IS NOT `adapter_manifest`
=========================================

    A column defaulted to the strongest value would silently upgrade twenty rows
    nobody checked. The migration is the moment the distinction is introduced, and
    every row that predates it is by definition unverified.

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

METHODS = ("adapter_manifest", "probe", "hand")


def upgrade() -> None:
    op.execute("""
        ALTER TABLE forge_module_registry
          ADD COLUMN verified_at         TIMESTAMPTZ,
          ADD COLUMN verified_against    TEXT,
          ADD COLUMN verification_method TEXT NOT NULL DEFAULT 'hand'
            CHECK (verification_method IN ('adapter_manifest', 'probe', 'hand'))
    """)

    # A method that is not `hand` is a claim that something was asked and answered.
    # Without a timestamp there is nothing to say when, and "verified" with no date is
    # the shape of a claim that ages into a lie.
    op.execute("""
        ALTER TABLE forge_module_registry
          ADD CONSTRAINT verification_is_dated CHECK (
            verification_method = 'hand' OR verified_at IS NOT NULL
          )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT verification_is_dated ON forge_module_registry IS
        'A machine-obtained verification carries the moment it was obtained. A Forge '
        'can stop dispatching a module the morning after it was checked, so an '
        'undated verification cannot be reasoned about at all.'
    """)

    # This is the comment for whoever is about to write a row for a new Forge.
    op.execute("""
        COMMENT ON TABLE forge_module_registry IS
        'Modules The Office believes a Forge exposes. THE ADAPTER IS THE NAMING '
        'AUTHORITY: module_id must be spelled exactly as the key in the Forge '
        'adapter''s dispatch map, which GET {base_url}/_modules reports. A Pack''s '
        'modules_expected, these rows and forge_module_exclusion all resolve against '
        'that one set of keys, so a row written under a second spelling for the same '
        'endpoint does not merely fail to match - it makes the exclusion for that '
        'endpoint miss, and the module becomes grantable under the new name. See '
        'docs/module-exclusions.md and docs/forge-adapter.md. Run '
        'scripts/verify_forge_modules.py rather than filling verification_method by '
        'hand.'
    """)
    op.execute("""
        COMMENT ON COLUMN forge_module_registry.verification_method IS
        'adapter_manifest: the Forge listed this module in its own dispatch map, which '
        'is derived from bound handlers and is the only non-declaration in the path. '
        'probe: the route table answered that the path exists (calibrated per run; an '
        'uncalibrated probe reports NOT_RUN and writes nothing). hand: somebody typed '
        'it, which is a claim and must never be counted as conformance. None of the '
        'three says the handler works or does what the name says.'
    """)
    op.execute("""
        COMMENT ON COLUMN forge_module_registry.verified_against IS
        'What answered and how, e.g. cre-forge@1.4.0 via adapter_manifest. The api '
        'version matters: a module verified against 1.4.0 says nothing about 2.0.0.'
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE forge_module_registry "
        "DROP CONSTRAINT IF EXISTS verification_is_dated"
    )
    op.execute("""
        ALTER TABLE forge_module_registry
          DROP COLUMN IF EXISTS verified_at,
          DROP COLUMN IF EXISTS verified_against,
          DROP COLUMN IF EXISTS verification_method
    """)
