"""A bootstrap certification's hash must name a live instruction

Revision ID: 0038
Revises: 0037

`certification.instruction_content_hash` is the answer to "certified on what, exactly".
Until the bootstrap was corrected it wrote `sha256("phase0.8:<forge>:<module>:<api>")` - a
hash of a LABEL. Fifteen rows carried one. Nothing was wrong with the rows' shape; their
subject did not exist.

WHY `invalid_hash` AND NOT `stale_instructions`
===============================================

    `stale_instructions` means the text moved: there was a document, an agent was examined
    on it, and it has since changed. The fix is to re-certify, and the prior certification
    was real.

    A hash naming no instruction is a different fact. **Nothing moved, because there was
    never anything there.** Filing it as stale says an examination happened against a
    document that has since been revised, and invites the same remedy - which would
    re-certify against whatever is live now and quietly ratify the original claim.

WHY A TRIGGER AND NOT A CHECK
=============================

    A CHECK constraint cannot contain a subquery, and this invariant is across two tables:
    the hash on `certification` must appear as a live `content_hash` in
    `forge_operating_instruction`. So it is a BEFORE INSERT OR UPDATE trigger, the same
    shape `forge_module_exclusion` already uses to keep an excluded module ungrantable -
    and named in the same spirit, so a refusal says which rule refused.

    **Unit B is exempt, and it is not the same loophole.** A unit-B certification is
    department x forge and carries `module_id IS NULL` by design, so there is no single
    instruction it could name. `recompute_staleness` exempts it for exactly this reason.

WHAT IT DOES TO THE FIFTEEN
===========================

    They are restated as `invalid_hash`, not deleted. The row is the only record that a
    bootstrap was performed and what it claimed; removing it would destroy the evidence of
    the defect along with the defect. `certified_records_its_basis` still holds - the hash,
    api_version and tier are all still present - because the row is no longer `certified`.
"""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE certification DROP CONSTRAINT certification_state_check")
    op.execute(
        """
        ALTER TABLE certification ADD CONSTRAINT certification_state_check
        CHECK (state = ANY (ARRAY[
            'certified', 'provisional', 'stale_instructions', 'stale_forge',
            'in_training', 'never_certified', 'failed', 'revoked', 'invalid_hash'
        ]))
        """
    )

    # Restate before the trigger exists, or the trigger refuses the restatement.
    #
    # **Keyed on "no instruction row at all", not "no LIVE one" - the two select different
    # rows and only the first is this defect.** A genuinely stale certification names an
    # instruction that has since been superseded; that row is still in the table, with
    # `superseded_at` set, and the certification's subject therefore still exists. Keying on
    # liveness would sweep those up too and restate a real examination as a hash naming
    # nothing.
    #
    # It also makes this idempotent across a downgrade and re-upgrade. `invalid_hash` does not
    # exist at 0037, so `downgrade` has to map it onto something and maps it to
    # `stale_instructions` - lossy, and stated as such below. Keyed on the source state, the
    # re-upgrade would then skip those rows and the round trip would silently lose the
    # distinction this migration exists to draw. Keyed on the hash, it recovers them.
    op.execute(
        """
        UPDATE certification c SET state = 'invalid_hash', updated_at = now()
        WHERE c.unit = 'A' AND c.state IN ('certified', 'stale_instructions')
          AND NOT EXISTS (
            SELECT 1 FROM forge_operating_instruction i
            WHERE i.forge_id = c.forge_id AND i.module_id = c.module_id
              AND i.content_hash = c.instruction_content_hash
          )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION bootstrap_hash_is_live() RETURNS trigger AS $$
        BEGIN
            IF NEW.unit <> 'A' OR NEW.state <> 'certified' THEN
                RETURN NEW;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM forge_operating_instruction i
                WHERE i.forge_id = NEW.forge_id AND i.module_id = NEW.module_id
                  AND i.superseded_at IS NULL
                  AND i.content_hash = NEW.instruction_content_hash
            ) THEN
                RAISE EXCEPTION
                    'bootstrap_hash_is_live: certification for %/% names instruction_content_hash '
                    '%, which is not the content_hash of any live operating instruction. A '
                    'certification records the text an agent was examined on; this one names no '
                    'text.', NEW.forge_id, NEW.module_id, NEW.instruction_content_hash;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER bootstrap_hash_is_live
        BEFORE INSERT OR UPDATE ON certification
        FOR EACH ROW EXECUTE FUNCTION bootstrap_hash_is_live()
        """
    )


def downgrade() -> None:
    """Lossy on purpose, and the loss is recoverable.

    `invalid_hash` does not exist at 0037, so these rows have to become something. They become
    `stale_instructions`, which is the wrong fact - but re-upgrading recovers them, because the
    restatement above keys on the hash rather than on the state it is replacing.
    """
    op.execute("DROP TRIGGER IF EXISTS bootstrap_hash_is_live ON certification")
    op.execute("DROP FUNCTION IF EXISTS bootstrap_hash_is_live()")
    op.execute(
        "UPDATE certification SET state = 'stale_instructions' WHERE state = 'invalid_hash'"
    )
    op.execute("ALTER TABLE certification DROP CONSTRAINT certification_state_check")
    op.execute(
        """
        ALTER TABLE certification ADD CONSTRAINT certification_state_check
        CHECK (state = ANY (ARRAY[
            'certified', 'provisional', 'stale_instructions', 'stale_forge',
            'in_training', 'never_certified', 'failed', 'revoked'
        ]))
        """
    )
