"""A compliance library entry belongs to a venture, and says whether it is a draft

Revision ID: 0039
Revises: 0038

`compliance_library_entry` was keyed on `entry_ref` alone, portfolio-wide. Two things
followed, and both were known and recorded before this migration existed.

WHOSE ENTRY IS IT
=================

    `broker/compliance_couplings.py` states the first: *"A LIBRARY ENTRY resolves because
    SOME venture loaded it. `compliance_library_entry` is keyed on entry_ref with no
    venture column, so Burkham can overwrite what Greenstone's agents read and V28 stays
    green throughout - it asks whether the ref resolves, not whose entry answered."*
    `scripts/load_compliance_library.py` is blunter: *"NOTHING STRUCTURAL PREVENTS THIS.
    IT IS A KNOWN PROPERTY, NOT AN OVERSIGHT."*

    Today's 21 rows partition cleanly - 19 Burkham refs, 2 Greenstone - so no collision
    has happened. The regimes already overlap though: both ventures carry
    `recording_consent_required` under different ref names, and one venture naming its NV
    entry the way the other did would have overwritten it silently. A live symptom
    already exists a level down: `scripts/derive_capitalforge_instructions.py` inverts
    flag -> ref over an unordered SELECT, and `recording_consent_required` maps to two
    refs, so that dict's value is nondeterministic.

    **The key is now `(venture_id, entry_ref)`.** Gate 6's flag query and V28's resolution
    are scoped with it, which makes both stricter: an entry belonging to another venture
    stops explaining this venture's flag.

A DRAFT MUST NOT READ AS SETTLED
================================

    The second: the table has columns for six fields and the files carry more. `status`,
    `claim_provenance`, `notes` and `depends_on` were never loaded, so
    `compliance/call-recording-consent-v1` - written by hand, tagged
    `draft_pending_claim_library_approval`, with its Nevada claim marked as a
    contradiction between two artifacts and counsel review deferred to state activation -
    read out of the database as an entry like any other.

    Eighteen of the nineteen Burkham entries carry that status. **Ivan's ruling of 15
    September: an entry no lawyer has reviewed must never read as settled.** So `status`
    and `claim_provenance` are columns now, and `counsel_reviewed_at` is the one fact
    neither file nor loader can supply - a person reviews an entry, and until one has,
    that column is NULL and says so.

WHY `status` DEFAULTS TO 'draft' AND THE BACKFILL WRITES 'draft' EVERYWHERE
==========================================================================

    The cautious direction is the whole point of the ruling. A default of 'approved'
    would make every future row read as reviewed until somebody remembered to say
    otherwise, which is the failure this closes rather than a shortcut around it. The
    backfill does not try to read the files: it marks all 21 rows 'draft', and the next
    loader run writes each file's own status. **No existing row is thereby mislabelled -
    one of the 21 says `approved` in its file, and it will say so again the moment it is
    loaded.** Reading as a draft for an hour is survivable; reading as approved when
    nobody approved it is what this exists to prevent.

THE BACKFILL IS LITERAL, AND THE FALLBACK IS LOUD
=================================================

    Nothing in the database can derive which venture an entry belongs to. `authored_by`
    cannot: the Burkham load stamped a smoke fixture's uuid, and the two Greenstone rows
    carry `00000000-0000-5000-8000-00000000aaaa`, which resolves to no account at all.

    So the two Greenstone refs are named literally, and everything else becomes
    `burkham-wickmont` - true of every row that exists here. Any row this migration has
    not heard of is therefore assigned to Burkham, which is a guess, so it is counted and
    raised rather than assumed: if a row is not one of the 21 known refs, the migration
    fails and names it. A wrong venture is the one mistake in this change that would be
    quiet - it would flip a venture's V28 to FAIL with a message that reads like a missing
    entry.

THE DOWNGRADE IS LOSSY AND REFUSES RATHER THAN CHOOSING
=======================================================

    Restoring `PRIMARY KEY (entry_ref)` is impossible once two ventures hold the same
    ref. CI round-trips migrations on an EMPTY database, so it will never meet that case;
    a downgrade that silently dropped one venture's row would be found by whoever lost an
    entry. So it raises, naming the duplicated refs. Everything else is dropped, including
    every status and provenance a load had written - stated here because a downgrade that
    quietly discards the reason an entry was a draft is the same defect one layer down.
"""

from __future__ import annotations

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

#: The two Greenstone refs, named because nothing in the row says so. Everything else in
#: this table is Burkham's; see the docstring for why that is asserted rather than
#: derived, and why an unknown ref stops the migration instead of joining them.
GREENSTONE_REFS = ("compliance/nv-two-party-consent-v1", "compliance/ftc-tsr-v2")

#: Read out of `packs/compliance-library/burkham-wickmont.yaml` and checked against the
#: 19 rows in the database, both. The first draft of this list was written from memory
#: and NINE of the nineteen were wrong - plausible names for entries that do not exist,
#: which is the defect this ledger has recorded more than once. A wrong ref here does not
#: fail: it leaves the row unplaced, and the guard below turns that into a stopped
#: migration rather than a silent reassignment.
BURKHAM_REFS = (
    "compliance/application-authorization-v1",
    "compliance/application-truthfulness-v1",
    "compliance/bureau-report-handling-v1",
    "compliance/call-recording-consent-v1",
    "compliance/card-product-characterisation-v1",
    "compliance/cfpb-1071-boundary-v1",
    "compliance/client-interest-standard-v1",
    "compliance/consumer-privacy-rights-v1",
    "compliance/estimate-not-offer-v1",
    "compliance/facilitator-not-broker-v1",
    "compliance/fair-treatment-in-routing-v1",
    "compliance/fcra-pull-authorization-v1",
    "compliance/glba-plaid-connection-v1",
    "compliance/no-advance-placement-v1",
    "compliance/not-a-credit-repair-organization-v1",
    "compliance/outbound-contact-boundary-v1",
    "compliance/own-claims-and-pricing-v1",
    "compliance/reg-z-advertising-boundary-v1",
    "compliance/tax-advice-boundary-v1",
)


def _in_list(refs: tuple[str, ...]) -> str:
    """`('a', 'b')` for SQL, written out rather than repr'd.

    A tuple's repr renders a one-element tuple as `('a',)`, which is a syntax error in an
    IN list. Both lists here have more than one entry today; the next one might not.
    """
    quoted = ", ".join("'" + ref.replace("'", "''") + "'" for ref in refs)
    return f"({quoted})"


def upgrade() -> None:
    op.execute("ALTER TABLE compliance_library_entry ADD COLUMN venture_id TEXT")

    op.execute(
        "UPDATE compliance_library_entry SET venture_id = 'greenstone' "
        f"WHERE entry_ref IN {_in_list(GREENSTONE_REFS)}"
    )
    op.execute(
        "UPDATE compliance_library_entry SET venture_id = 'burkham-wickmont' "
        f"WHERE entry_ref IN {_in_list(BURKHAM_REFS)}"
    )

    # Loud, not lenient. An unrecognised ref means this table holds something written
    # after the lists above, and guessing its venture is the one quiet mistake available
    # here. The exception names the refs so whoever meets it can say which venture.
    op.execute("""
        DO $$
        DECLARE unknown TEXT;
        BEGIN
          SELECT string_agg(entry_ref, ', ' ORDER BY entry_ref) INTO unknown
          FROM compliance_library_entry WHERE venture_id IS NULL;
          IF unknown IS NOT NULL THEN
            RAISE EXCEPTION
              'compliance_library_entry holds entries migration 0039 cannot place: %. '
              'Add each to GREENSTONE_REFS or BURKHAM_REFS - the venture cannot be '
              'derived from the row, and a wrong guess flips that venture''s V28.',
              unknown;
          END IF;
        END $$
    """)

    op.execute("ALTER TABLE compliance_library_entry ALTER COLUMN venture_id SET NOT NULL")
    op.execute("""
        ALTER TABLE compliance_library_entry
          ADD CONSTRAINT compliance_entry_venture_not_blank
              CHECK (length(trim(venture_id)) > 0)
    """)

    op.execute("ALTER TABLE compliance_library_entry DROP CONSTRAINT compliance_library_entry_pkey")
    op.execute("""
        ALTER TABLE compliance_library_entry
          ADD PRIMARY KEY (venture_id, entry_ref)
    """)

    # Re-cut with the venture leading: every consumer of this index now asks
    # "which flags can THIS venture's library explain", and Gate 6 is the caller.
    op.execute("DROP INDEX ix_compliance_flag")
    op.execute("""
        CREATE INDEX ix_compliance_flag
          ON compliance_library_entry (venture_id, runtime_flag)
          WHERE runtime_flag IS NOT NULL
    """)

    op.execute("""
        ALTER TABLE compliance_library_entry
          ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'
              CHECK (status IN ('draft', 'draft_pending_claim_library_approval',
                                'approved')),
          ADD COLUMN claim_provenance JSONB NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN counsel_reviewed_at TIMESTAMPTZ
    """)

    op.execute("""
        COMMENT ON COLUMN compliance_library_entry.venture_id IS
        'Whose entry this is. The key is (venture_id, entry_ref): before 0039 one '
        'venture could overwrite another''s entry under the same ref and every check '
        'stayed green, because they ask whether a ref resolves and not whose entry '
        'answered.'
    """)
    op.execute("""
        COMMENT ON COLUMN compliance_library_entry.status IS
        'draft | draft_pending_claim_library_approval | approved. Defaults to draft: an '
        'entry nobody has approved must not read as settled, and a default of approved '
        'would assert a review that did not happen.'
    """)
    op.execute("""
        COMMENT ON COLUMN compliance_library_entry.claim_provenance IS
        'The file''s claim_provenance list, verbatim: each claim tagged sourced, '
        'reconstructed or proposed, with its source. Loaded from 0039 onward; before '
        'that the files carried it and the database did not, so an entry written by hand '
        'and never reviewed read exactly like one taken from a statute.'
    """)
    op.execute("""
        COMMENT ON COLUMN compliance_library_entry.counsel_reviewed_at IS
        'When a lawyer read this entry. NULL means none has - the fact no file and no '
        'loader can supply, because it is not a property of the text.'
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        DECLARE dupes TEXT;
        BEGIN
          SELECT string_agg(entry_ref, ', ' ORDER BY entry_ref) INTO dupes
          FROM (SELECT entry_ref FROM compliance_library_entry
                 GROUP BY entry_ref HAVING count(*) > 1) d;
          IF dupes IS NOT NULL THEN
            RAISE EXCEPTION
              'cannot restore a single-key compliance library: % held by more than one '
              'venture. Downgrading would drop one venture''s entry, and which one is '
              'not this migration''s decision to make.', dupes;
          END IF;
        END $$
    """)

    op.execute("DROP INDEX ix_compliance_flag")
    op.execute("ALTER TABLE compliance_library_entry DROP CONSTRAINT compliance_library_entry_pkey")
    op.execute("""
        ALTER TABLE compliance_library_entry
          DROP CONSTRAINT compliance_entry_venture_not_blank,
          DROP COLUMN venture_id,
          DROP COLUMN status,
          DROP COLUMN claim_provenance,
          DROP COLUMN counsel_reviewed_at
    """)
    op.execute("ALTER TABLE compliance_library_entry ADD PRIMARY KEY (entry_ref)")
    op.execute("""
        CREATE INDEX ix_compliance_flag ON compliance_library_entry (runtime_flag)
          WHERE runtime_flag IS NOT NULL
    """)
