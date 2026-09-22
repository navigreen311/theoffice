"""An escalation leaves a record

Revision ID: 0051
Revises: 0050

Ruled 21 September 2026 (Ivan Green):

    *"An escalation leaves a record: raised, by whom, routed to which named human,
    received, and answered, with timestamps. Both escalation paths return a route and
    write nothing. An escalation path cannot be attested verified until it can be shown
    to have been travelled."*

WHAT WAS MEASURED
=================

    `escalation.governance` and `escalation.operational` resolve a recipient and return
    a `Route`. **Neither writes anything**, and neither has a single caller in `broker/`
    or `generators/` - the only references outside that module are
    `generators/appointment.py` declaring a PATH on the artifact and calling
    `assert_path` to check that a governance decision is not addressed to an agent.

    So the two paths have never been travelled, and there was nowhere for the fact to be
    recorded if they had been. The attestation brief of 21 September could say only that
    both resolve.

FIVE FACTS, AND EACH ONE IS A COLUMN
====================================

    raised       `raised_at`, `raised_by`, `raised_by_kind`
    by whom      an agent or a human, named - and `raised_by_kind` says which, because
                 an agent id and a human id are drawn from different tables
    routed to    `routed_to_name` always, `routed_to_human` when the path is GOVERNANCE
    received     `received_at`, `received_by`
    answered     `answered_at`, `answered_by`, `answer`

    Three timestamps, not one. "Raised and answered" with a single stamp cannot tell a
    path that works from one where somebody found the item three days later - and the
    gap between raised and received is the number a drill exists to produce.

WHY RECEIPT IS ITS OWN STEP
===========================

    Because delivery is the thing nobody can currently demonstrate. An escalation that
    was raised and answered by the same process, in the same second, proves the function
    returns - the point of the ruling is that somebody on the other end got it.

    So `received_at` may be NULL with `raised_at` set, and that row is a live finding: an
    escalation nobody has picked up. `answered_at` NULL with `received_at` set is a
    different finding, and the CHECK below keeps them in order rather than letting an
    answer arrive before a receipt.
"""

from __future__ import annotations

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE escalation_record (
          escalation_id   UUID PRIMARY KEY,
          venture_id      TEXT NOT NULL,

          -- NULLABLE, and it is the difference between "this department's path" and
          -- "this venture's". A capacity shortfall is about the venture; a research
          -- agent asking who may widen a radius is about research. Unit B attestation
          -- reads the second kind, so a venture-wide escalation must not count as
          -- evidence that a named department's path works.
          department      TEXT,

          path            TEXT NOT NULL CHECK (path IN ('governance', 'operational')),
          kind            TEXT NOT NULL,
          reason          TEXT NOT NULL,

          raised_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          raised_by       UUID NOT NULL,
          raised_by_kind  TEXT NOT NULL CHECK (raised_by_kind IN ('agent', 'human')),

          -- WHO IT WENT TO, by name, always. A governance route also names the human,
          -- because that one can be held to it; an operational route names a POSITION's
          -- holder, which is an agent and deliberately not a `human_id`.
          routed_to_name  TEXT NOT NULL,
          routed_to_human UUID,

          received_at     TIMESTAMPTZ,
          received_by     UUID,
          answered_at     TIMESTAMPTZ,
          answered_by     UUID,
          answer          TEXT,

          -- A GOVERNANCE ROUTE NAMES A HUMAN. `escalation.governance` resolves through
          -- `attributable_actor`, which refuses a fixture, so a governance row with no
          -- human is a row that could not have been delivered to anybody.
          CONSTRAINT governance_names_a_human CHECK (
            path <> 'governance' OR routed_to_human IS NOT NULL
          ),
          -- IN ORDER. An answer before a receipt is not a path that worked; it is two
          -- timestamps somebody wrote.
          CONSTRAINT received_before_answered CHECK (
            answered_at IS NULL OR (received_at IS NOT NULL AND answered_at >= received_at)
          ),
          CONSTRAINT received_after_raised CHECK (
            received_at IS NULL OR received_at >= raised_at
          ),
          -- An answer is a sentence, not a flag. Same rule `disposition` and
          -- `superseding_a_submission_says_why` already apply.
          CONSTRAINT an_answer_says_something CHECK (
            (answered_at IS NULL) = (answered_by IS NULL)
            AND (answered_at IS NULL OR length(btrim(coalesce(answer, ''))) > 0)
          ),
          CONSTRAINT a_receipt_names_somebody CHECK (
            (received_at IS NULL) = (received_by IS NULL)
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE escalation_record IS
        'Every escalation raised, and what happened to it. Ruled 21 September 2026: an '
        'escalation leaves a record - raised, by whom, routed to which named human, '
        'received, and answered, with timestamps. An escalation path cannot be attested '
        'verified until a complete row exists for it (entry 149).'
    """)
    # `travelled` reads this: the newest complete escalation for a department.
    op.create_index(
        "ix_escalation_record_department",
        "escalation_record",
        ["venture_id", "department", "answered_at"],
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON escalation_record TO office_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS escalation_record")
