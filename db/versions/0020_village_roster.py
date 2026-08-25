"""The Village roster, so a denominator can be real.

The Agents page shows the agents that hold an Office identity - seven of them - and a
reader concludes the Village has seven people. It does not. The blueprint describes 106,
and The Office has never had anywhere to record that: `office_agent_identity` is a list
of agents The Office has *appointed*, which is a different set and a smaller one.

The Compliance page hit this first and refused to invent the number:

    No denominator is hardcoded. The master prompt describes a Village of 106 agents
    and a portfolio of several ventures; The Office knows about the agents and ventures
    that have actually reached it. Reporting "0 of 106" against a roster of seven would
    invent a denominator, on the page whose own copy insists on real ones.

That was right, and it left the roster gap unfixable rather than merely unreported. This
table is the fix: somewhere for the Village's roster to live, so "7 of 106" is a fact
this database can support rather than a number typed into a template. Until a roster is
imported the page says the roster is unknown, which is true and is not the same as
saying the Village has seven agents.

`village_agent_ref` is the Village's own identifier and the join key to
`office_agent_identity`. A row here means the Village has this agent. An identity row
means The Office can appoint it. The gap between the two counts is the thing the page
exists to show.

`status` records agents the Village has since removed. They are kept rather than
deleted: an agent that departed while holding grants is a revocation somebody has to
perform, and a roster that silently dropped the row would take the evidence with it.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE village_agent (
          village_agent_ref TEXT PRIMARY KEY,
          agent_name        TEXT NOT NULL,
          department        TEXT NOT NULL,
          status            TEXT NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'departed')),
          first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          departed_at       TIMESTAMPTZ,
          -- Where the row came from. A roster imported from a file and one typed in by
          -- hand are different kinds of evidence, and the page says which.
          source            TEXT NOT NULL DEFAULT 'import'
                              CHECK (source IN ('import', 'manual'))
        )
    """)
    op.execute("""
        COMMENT ON TABLE village_agent IS
        'The Village roster. A row here means the Village has this agent; a row in '
        'office_agent_identity means The Office can appoint it. The gap between the two '
        'is what the Agents page exists to show, and it cannot be shown without this.'
    """)
    op.execute("CREATE INDEX ix_village_agent_department ON village_agent (department)")

    # SELECT, INSERT and UPDATE. No DELETE: a departed agent is marked, never removed -
    # an agent that left while holding grants is the row somebody needs to find
    # afterwards, and the identity that points at it would lose its join target.
    op.execute("GRANT SELECT, INSERT, UPDATE ON village_agent TO office_app")

    # The roster is the source of truth for who exists, so an identity should point at a
    # roster row. Not enforced as a foreign key: identities predate this table, and
    # refusing to load the console until somebody backfills them would be a worse
    # failure than an identity whose roster row has not been imported yet. The page
    # reports those as `no roster row` rather than hiding them.
    op.execute("""
        COMMENT ON COLUMN office_agent_identity.village_agent_ref IS
        'The Village''s own identifier, and the join key to village_agent. Not a foreign '
        'key: identities exist that predate the roster table, and they are reported as '
        'unmatched rather than dropped.'
    """)


def downgrade() -> None:
    op.execute("DROP TABLE village_agent")
