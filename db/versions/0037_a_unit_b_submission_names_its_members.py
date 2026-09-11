"""A unit-B submission records which modules composed its basis.

B36 half two. A unit-B run is a department in a Forge, and its
`instruction_content_hash` is `simforge.department_basis_hash(module_hashes)` - a
composite over the set of instruction hashes the department's modules were handed over
under, domain-separated so it cannot collide with a real instruction hash.

The composite is one-way. The sweep holds the hash and needs the `forge_api_version`
those instructions were judged against, and `certified_records_its_basis` refuses a
certified row without one. Unit A recovers it from `forge_operating_instruction` keyed
on the module's own hash; unit B has no single module and no single hash, so the
recovery had nowhere to start and `broker/sweeps.py` gated it on `unit == "A"`.

WHY A CHILD TABLE AND NOT A COLUMN
==================================

    The set is `{module_id: instruction_content_hash}`, not a list of ids. An array
    column would store the members and lose the hashes, and the hashes are the entire
    mechanism - each one resolves to the `forge_operating_instruction` row that carries
    the `forge_api_version` this run was actually judged against. A mapping is a
    relation, so it is stored as one.

WHY NOT THE CHEAPER VARIANT
===========================

    `department` could have been written onto the unit-A rows as well, and the sweep
    could then recover the member set with one query and no new table. It was refused:
    `_record_submission`'s docstring states that `module_id` and `department` ARE the
    unit and its callers pass exactly one of the two, and `submission_unit` is readable
    precisely because that is true. Buying a schema saving with a sentence that stops
    being true is the trade this project keeps declining.

WHAT THIS DOES NOT CHANGE
=========================

    Nothing about unit A, which writes no rows here, and nothing about the parent
    table's shape. `curriculum_submission` still has no unit constraint - the rule lives
    in `submission_unit`, where it always did.

    ON DELETE CASCADE because a member row describes its parent submission and has no
    meaning without it. There is no independent lifecycle to protect.
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE curriculum_submission_module (
            submission_id            uuid NOT NULL
                                     REFERENCES curriculum_submission(submission_id)
                                     ON DELETE CASCADE,
            module_id                text NOT NULL,
            instruction_content_hash text NOT NULL,
            PRIMARY KEY (submission_id, module_id)
        )
        """
    )
    # The sweep's access path: every member of one submission, in one read.
    op.execute(
        "CREATE INDEX ix_submission_member ON curriculum_submission_module "
        "(submission_id)"
    )

    # SELECT and INSERT only, deliberately narrower than the parent table's full DML.
    # A member row records what a department's basis was composed of at the moment it
    # was handed over; editing one would rewrite the basis of a certification that has
    # already been earned, and there is no path in the broker that wants to. This is the
    # `agent_call_ledger` treatment - write once, read forever - applied for the same
    # reason, and the REVOKE is explicit rather than assumed from the absence of a GRANT.
    op.execute(
        "GRANT SELECT, INSERT ON curriculum_submission_module TO office_app"
    )
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON curriculum_submission_module FROM office_app"
    )


def downgrade() -> None:
    """Drops the table and every member row in it.

    Lossless only while nothing has been written. Stated rather than implied: the rows
    describe which modules composed a department's basis, and that set is not
    recoverable from the composite hash afterwards - which is the whole reason this
    table exists.
    """
    op.execute("DROP TABLE IF EXISTS curriculum_submission_module")
