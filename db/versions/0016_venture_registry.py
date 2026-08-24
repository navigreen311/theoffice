"""A venture registry, for the two things an engagement cannot derive.

A venture has always been an engagement rather than a table - `/api/ventures` derives one
from grants, manifest rows or a budget, which is why the directory could exist before
anything was provisioned. That was right and mostly stays true.

It cannot support two things the console now needs.

**A draft venture.** Named and created, with no Pack yet. `BusinessPack` is `Strict` and
rejects anything incomplete, so a stub Pack would mean inventing a dozen required values
- including `monthly_usd_cap`, which is precisely the field V18 exists to stop a venture
reaching production without. An invented cap is worse than an absent one because it
looks like a decision.

**`archived` and `winding_down`.** Nothing derives them. A venture with no grants and no
Pack is indistinguishable from one somebody deliberately retired, and those need
different answers.

So this table holds **only what cannot be derived**: the slug, the human's declared name
and category, the environment, the lifecycle state, and who created it. Everything the
Pack declares stays the Pack's to answer - when one exists, `identity.venture_name` wins
over the copy here, which is what a draft has before there is a Pack to read.

`slug` is the primary key and immutable by construction: every venture-scoped table in
this schema keys on `venture_id` as text, and changing it would orphan grants, ledger
rows and audit entries that name it.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE venture (
          slug           TEXT PRIMARY KEY
                           CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
          display_name   TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
          category       TEXT NOT NULL CHECK (length(trim(category)) > 0),
          environment    TEXT NOT NULL DEFAULT 'sandbox'
                           CHECK (environment IN ('sandbox','production')),
          lifecycle_state TEXT NOT NULL DEFAULT 'draft'
                           CHECK (lifecycle_state IN
                             ('draft','active','winding_down','archived')),
          created_by     UUID NOT NULL,
          created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          archived_at    TIMESTAMPTZ,
          archived_by    UUID,

          CONSTRAINT archival_names_who CHECK (
            lifecycle_state <> 'archived'
            OR (archived_at IS NOT NULL AND archived_by IS NOT NULL)
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE venture IS
        'Only what an engagement cannot derive: the human intent behind a venture and '
        'its lifecycle. Grants, manifest rows and budgets still derive everything else, '
        'and a Pack overrides the name and category copies here the moment one exists.'
    """)
    op.execute("""
        COMMENT ON COLUMN venture.slug IS
        'Immutable. Every venture-scoped table keys on this as text, so changing it '
        'would orphan grants, ledger rows and audit entries that name it. The regex is '
        'the control: a slug with a space or a capital would be a different key from '
        'the one somebody typed.'
    """)
    op.execute("""
        COMMENT ON COLUMN venture.lifecycle_state IS
        'draft: created, no Pack yet - cannot receive grants because there is nothing '
        'to generate a runtime config from. archived is terminal until explicitly '
        'reopened, and both transitions are audited.'
    """)

    op.execute("GRANT SELECT, INSERT, UPDATE ON venture TO office_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS venture")
