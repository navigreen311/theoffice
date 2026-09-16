"""A daily total belongs to the person, not to a venture's Pack

Revision ID: 0041
Revises: 0040

Every hours figure in this system is declared inside one venture's Pack, and no venture's
Pack can see another. So Ivan Green is declared for six hours in Greenstone and six in
Burkham, and **nothing anywhere has ever added them up** - decisions entry 94 §5 recorded
sixteen hours a day for one person and noted that no rule refuses it, because no rule can
reach across Packs.

V39 is that rule. It needs one number a Pack cannot supply: how many hours the person
actually has.

WHY ON THE ACCOUNT AND NOT IN A PACK
====================================

    A total is a fact about a person. Putting it in a Pack would mean every Pack
    declaring the same number and the rule believing whichever it read first - the shape
    B24 is about, where a gate verdict turned on YAML order. Worse, it would let a venture
    raise its own founder's total to make its own check pass, which is the one thing a
    cross-venture rule exists to stop.

    `office_human` already carries what is true of the person rather than of a venture:
    the display name two Packs resolve against, the auth method, the status. The total
    belongs beside them.

NULLABLE, AND THAT IS NOT A DEFAULT
===================================

    `NULL` means "this person has not declared a daily total", and V39 says so by name
    rather than assuming twenty-four or eight. A default here would be the constant 8 one
    table over: a number nobody chose, deciding a verdict.

    `ck_daily_total_hours_sane` refuses zero and anything past twenty-four. Zero is not a
    declaration of no capacity - it is an empty field with a number in it - and a total
    above twenty-four is an arithmetic error, not a commitment.

WRITTEN THROUGH ONE ROUTE
=========================

    `POST /api/humans/{id}/daily-total`, `ivan` only, writing `console_human_daily_total_set`
    with the old value and the new. The same shape and the same reason as the rename in
    0040: a number that decides whether a venture may provision is an act, and an act
    without an audit row is a change nobody can find afterwards.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "office_human",
        sa.Column("daily_total_hours", sa.Numeric(4, 2), nullable=True),
    )
    op.create_check_constraint(
        "ck_daily_total_hours_sane",
        "office_human",
        "daily_total_hours IS NULL OR (daily_total_hours > 0 "
        "AND daily_total_hours <= 24)",
    )
    op.execute("""
        COMMENT ON COLUMN office_human.daily_total_hours IS
        'How many hours a day this person has, across every venture. NULL means not '
        'declared, and V39 reports that by name rather than assuming a number. Set only '
        'through POST /api/humans/{id}/daily-total, which writes '
        'console_human_daily_total_set.'
    """)


def downgrade() -> None:
    op.drop_constraint("ck_daily_total_hours_sane", "office_human", type_="check")
    op.drop_column("office_human", "daily_total_hours")
