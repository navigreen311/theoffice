"""A named human verified a human-held obligation, and here is until when.

    A document filed in a vault is evidence. It is not a state a rule can read.

Entry 26 declares `referral_fee_permitted_in_state` human-held: the obligation is real,
and no position in the Pack has a duty that touches a payout. `HumanHeld(why=...)` says
so in the Pack. This table is the other half — whether the obligation was actually
discharged, by whom, against what, and until when.

Without it, `HumanHeld` is a cheap escape. That is not a hypothetical: with the type
landed and V34 unwritten, Burkham validated at 32 PASS / 0 FAIL and Gate 2 cleared for a
venture whose referral obligation nobody had verified. See `docs/decisions.md` entry 26.

WHY A TABLE AND NOT A FLAG
==========================
"Written verification filed in the Compliance Evidence Vault" is a document. A boolean
somebody flips by hand is `venture_forge_manifest`'s shape — a state that looks
configured and was hand-placed, indistinguishable afterwards from one that was earned.

A discharge IS a human act, so a human-written row is the correct provenance. What makes
it a record rather than a flag is that it carries who, when, against what, until when,
and on what basis — and it cannot be confused with something a generator produced,
because no generator writes this table.

The shape follows `signoff_record`, which already models "a named human did a thing,
against a hashed artifact": the paper is the evidence, the row is the fact. The artifact
is referenced by hash and never stored here.

WHY EVERY COLUMN IS REQUIRED EXCEPT `superseded_at`
===================================================
`basis` most of all. A discharge without a sentence saying what was verified is the
accidental-empty problem `NoFramework` was built to refuse: nothing can tell a
considered discharge from a row somebody added to make a rule go quiet.

`superseded_at` is the one nullable column because the table is append-only. A discharge
is never edited or deleted — a new one supersedes it, and the old row stays readable, so
"verified in 2026" and "verified" remain distinguishable after the fact.

THE THREE REFRESH TRIGGERS ARE NOT TIME-BASED, AND THAT IS WHY SCOPE IS A COLUMN
===============================================================================
`expires_at` is a twelve-month backstop, not the mechanism. The events that actually
invalidate a discharge are:

  new state            `jurisdiction_scope` is what the verification covers. If the
                       venture's footprint exceeds it, the discharge no longer covers,
                       and V34 can name the uncovered jurisdiction rather than reporting
                       a vague staleness.

  statute amended      `library_entry_ref` cites what was verified against. If that
                       library entry's `updated_at` is later than `verified_at`, the
                       discharge is stale. This reuses the mechanism that already flips
                       a certification stale when its instruction is superseded.

  relationship changes a human act; it supersedes the row.

A discharge that cannot express its own scope is a discharge that silently keeps
covering ground it never examined.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "obligation_discharge",
        sa.Column("discharge_id", sa.Uuid(), primary_key=True),
        sa.Column("venture_id", sa.Text(), nullable=False),
        # The runtime flag, not the framework name. V22's own comment: only the flag
        # propagates through positions, bindings and the ledger; the framework name
        # never appears at runtime.
        sa.Column("runtime_flag", sa.Text(), nullable=False),
        # What this verification actually covers. The mechanical basis for "new state".
        sa.Column("jurisdiction_scope", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("library_entry_ref", sa.Text(), nullable=False),
        sa.Column("citation", sa.Text(), nullable=False),
        # A real office_human row. An absent id would name nobody, which is the
        # `origin=human` problem: an actor recorded as though it acted.
        sa.Column("discharged_by", sa.Uuid(), nullable=False),
        sa.Column("role_discharged_as", sa.Text(), nullable=False),
        # The vault document, referenced not stored — as signoff_record does.
        sa.Column("artifact_kind", sa.Text(), nullable=False),
        sa.Column("artifact_hash", sa.Text(), nullable=False),
        # What was actually verified. Required, and refused when blank.
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["discharged_by"], ["office_human.human_id"]),
        # A blank basis is the accidental-empty problem. Refused in the schema rather
        # than in a code path somebody can forget to call.
        sa.CheckConstraint("length(btrim(basis)) > 0", name="ck_discharge_basis_nonempty"),
        sa.CheckConstraint(
            "cardinality(jurisdiction_scope) > 0", name="ck_discharge_scope_nonempty"
        ),
        sa.CheckConstraint("expires_at > verified_at", name="ck_discharge_expiry_after"),
    )
    # V34 asks one question: is there a current discharge for this venture and flag.
    op.create_index(
        "ix_obligation_discharge_current",
        "obligation_discharge",
        ["venture_id", "runtime_flag"],
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    # V34 reads it; nothing in the agent path writes it. A discharge is filed by a
    # named human through an operator surface, never by a broker call, so office_app
    # gets SELECT and nothing more - the same shape as forge_module_exclusion.
    op.execute("GRANT SELECT ON obligation_discharge TO office_app")


def downgrade() -> None:
    op.drop_index("ix_obligation_discharge_current", table_name="obligation_discharge")
    op.drop_table("obligation_discharge")
