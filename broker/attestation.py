"""Unit B by named-human attestation — the stop-gap, and the thing that ends it.

RULED 21 SEPTEMBER 2026 (decisions entry 147)
=============================================

    *"A certification records its basis: attested or tested, the attester by name, and
    the reasons. A reader can always tell them apart."*

    *"Who attests: a human holding founder authority, recorded by name."*

    *"What ends it: when a real hand-over test ships, attested Unit B certifications stop
    counting at Gate 9 and must be re-earned."*

WHAT THIS EXISTS INSTEAD OF
===========================

    Unit B is department CONTEXT certification: that a department's escalation path works
    and that its compliance coupling holds. SimForge opens a unit-B run and The Office
    submits no curriculum to it, because there is nothing on the receiving side to submit
    one to - `ForgeOperationCurriculum.instruction_set_ref` requires a `module_id`, and
    the `unit_type="department_context"` entry its `CertificationUnitRequest` accepts is
    read by nothing in `routers/operation.py::submit_curriculum`.

    So no unit-B verdict has ever been earned by anything running. The three Greenstone
    department units sat at `IN_PROGRESS` for as long as anybody has watched them, and a
    run that never answers resolves to TIMEOUT, which is `in_training` forever.

    **This does not fix that.** It lets a person say, by name and with reasons, what a
    test would otherwise have established - and it makes the difference legible, which is
    the part a note in a document could not do.

WHY APPEND-ONLY
===============

    A correction is a new attestation, never an edit. `audit_log`'s argument, applied to
    a smaller table: a record whose immutability depends on nobody writing the wrong
    statement is not immutable. The trigger in 0050 refuses UPDATE, DELETE and TRUNCATE
    outright, so the one statement that matters - somebody softening a reason after a
    certification has been read - cannot be written at all.

    The consequence is that `current_attestation` is a query and not a column: the latest
    row for a `(venture, department, forge)` triple is the one in force, and every
    earlier one stays readable beside it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import audit, escalation, humans, mfa

#: The role a human must hold to attest. NOT A NEW ROLE, and that is a measurement:
#: `office_human_role` has held `('venture_operator', 'compliance_officer', 'ivan')`
#: since 0010, `ROLE_RANK` puts `ivan` top at 3, and it is the role a Forge-scope
#: revocation already requires. It is named for the founder and it IS founder authority.
FOUNDER_ROLE = "ivan"

#: What SimForge would publish on `/api/version`'s `exam` block once a department
#: hand-over test exists. **It publishes nothing under this name today**, which is the
#: true state and the reason attested units still count.
#:
#: The key is The Office's proposal and has to be agreed on the other side. Entry 144 is
#: the reason it is written down here rather than assumed: the protocol and rubric
#: versions were read as flat top-level keys for a day because this side guessed a shape,
#: and a guess about another system reads as that system's silence. So Gate 9 records the
#: key it looked for, and the guess is visible rather than quiet.
HANDOVER_TEST_KEY = "department_handover_test"


class AttestationError(Exception):
    """A refusal this module made, distinct from an authorisation failure."""


@dataclass(frozen=True, slots=True)
class Attestation:
    attestation_id: uuid.UUID
    venture_id: str
    department: str
    forge_id: str
    attested_by: uuid.UUID
    attested_by_name: str
    attested_at: Any
    escalation_path_verified: bool
    escalation_path_reason: str
    compliance_coupling_verified: bool
    compliance_coupling_reason: str

    @property
    def passed(self) -> bool:
        """Both, or the outcome posted to SimForge is not a pass.

        `DepartmentRunOutcome.passed` defaults to true and the two verified flags default
        to false, so a caller that sent only `passed` would assert a pass over two
        unanswered questions. Derived here instead, from the two facts a person actually
        attested to.
        """
        return self.escalation_path_verified and self.compliance_coupling_verified


async def attest(
    conn: AsyncConnection,
    *,
    venture_id: str,
    department: str,
    forge_id: str,
    human: humans.Human,
    mfa_code: str,
    escalation_path_verified: bool,
    escalation_path_reason: str,
    compliance_coupling_verified: bool,
    compliance_coupling_reason: str,
) -> Attestation:
    """Record one attestation. A named human with founder authority, and two reasons.

    A FALSE VERDICT IS AS RECORDABLE AS A TRUE ONE, and deliberately: "I looked at this
    department's escalation path and it does not work" is a fact somebody should be able
    to write down, and forcing it to be written as silence produces a register in which
    absence means both "nobody looked" and "somebody looked and it failed".

    Both reasons are required whichever way the verdicts go, and the CHECK in 0050 backs
    it. A verdict without a reason is the shape this project keeps refusing - the same
    rule `superseding_a_submission_says_why` and `disposition` already apply.
    """
    if not escalation_path_reason.strip() or not compliance_coupling_reason.strip():
        raise AttestationError(
            "an attestation gives a reason for each of its two verdicts; the database "
            "refuses one without, and so does this"
        )

    # Founder authority, at every venture. `venture_id=None` because `ivan` is held
    # unscoped on this database and a founder decision binds every venture - the same
    # language `forge_module_exclusion` uses about itself.
    role = humans.authorize(human, required_role=FOUNDER_ROLE, venture_id=None)

    # A SECOND FACTOR, VERIFIED NOW. Ruled 21 September 2026, entry 155.
    #
    # An attestation is a named human saying a department's escalation path works when
    # no test can establish it. Its entire value is that somebody's name is on it, and a
    # bearer token is a credential that can be copied - so until entry 155 the strongest
    # claim in this system rested on the weakest evidence in it.
    #
    # AFTER `authorize`, for the same reason the travelled-path check is: telling a
    # caller their code is missing when they were never allowed to attest answers the
    # wrong question.
    await mfa.assert_verified(
        conn, me=human, code=mfa_code,
        act=f"attesting {venture_id}/{department}",
    )

    # AN ESCALATION PATH CANNOT BE ATTESTED VERIFIED UNTIL IT HAS BEEN TRAVELLED.
    # Ruled 21 September 2026, entry 149.
    #
    # AFTER the authorisation, and that ordering is deliberate: telling somebody their
    # evidence is missing when they were never allowed to attest at all answers the
    # wrong question, and it tells a caller without founder authority what evidence
    # would have worked.
    #
    # This is the one place the stop-gap is allowed to be strict, and it is the place it
    # has to be: an attestation exists because no test can establish that a department's
    # escalation path works, and "I looked at it" is not the same claim as "somebody
    # raised one and somebody answered it". The second is now recordable, so the first
    # stops being enough.
    #
    # ONLY THE TRUE VERDICT IS GATED. `escalation_path_verified=False` needs no evidence
    # and is refused nothing - "I looked and it does not work" is a fact somebody should
    # be able to write down, and requiring a successful drill before you may report a
    # failure would be the register forcing a lie.
    if escalation_path_verified:
        travelled = await escalation.travelled(
            conn, venture_id=venture_id, department=department
        )
        if travelled is None:
            raise AttestationError(
                f"no escalation for {venture_id}/{department} has been raised, received "
                "and answered, so its path cannot be attested verified. An escalation "
                "path is a delivery, and what this register would otherwise hold is "
                "somebody's reading of a route that resolves. Raise one "
                "(`escalation.raise_escalation`), have it received and answered, and "
                "attest against that."
            )

    attestation_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO department_attestation "
            "  (attestation_id, venture_id, department, forge_id, attested_by, "
            "   attested_by_name, escalation_path_verified, escalation_path_reason, "
            "   compliance_coupling_verified, compliance_coupling_reason) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                attestation_id, venture_id, department, forge_id, human.human_id,
                # CAPTURED, not joined. See 0050: the name is what the ruling asks for,
                # and it has to survive a renamed or closed account.
                human.display_name,
                escalation_path_verified, escalation_path_reason.strip(),
                compliance_coupling_verified, compliance_coupling_reason.strip(),
            ),
        )
    await conn.commit()

    await audit.write_event(
        event_type="department_attested",
        actor_type="human", actor_id=human.human_id, venture_id=venture_id,
        subject={
            "attestation_id": str(attestation_id),
            "department": department,
            "forge_id": forge_id,
            "role_attested_as": role,
            "escalation_path_verified": escalation_path_verified,
            "compliance_coupling_verified": compliance_coupling_verified,
            # THE REASONS ARE IN THE EVENT TOO. The table is append-only and the audit
            # chain is hash-linked, so the two together mean a reason cannot be altered
            # in either place without the other disagreeing.
            "escalation_path_reason": escalation_path_reason.strip(),
            "compliance_coupling_reason": compliance_coupling_reason.strip(),
        },
    )

    found = await current_attestation(
        conn, venture_id=venture_id, department=department, forge_id=forge_id
    )
    assert found is not None and found.attestation_id == attestation_id
    return found


async def current_attestation(
    conn: AsyncConnection, *, venture_id: str, department: str, forge_id: str
) -> Attestation | None:
    """The attestation in force for one (venture, department, Forge), or None.

    The LATEST by `attested_at`, with `attestation_id` breaking a tie so two rows written
    in the same transaction cannot make this answer depend on row order. Earlier rows stay
    readable; nothing supersedes anything, because nothing is ever edited.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM department_attestation "
            " WHERE venture_id = %s AND department = %s AND forge_id = %s "
            " ORDER BY attested_at DESC, attestation_id DESC LIMIT 1",
            (venture_id, department, forge_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return Attestation(
        attestation_id=row["attestation_id"],
        venture_id=row["venture_id"],
        department=row["department"],
        forge_id=row["forge_id"],
        attested_by=row["attested_by"],
        attested_by_name=row["attested_by_name"],
        attested_at=row["attested_at"],
        escalation_path_verified=row["escalation_path_verified"],
        escalation_path_reason=row["escalation_path_reason"],
        compliance_coupling_verified=row["compliance_coupling_verified"],
        compliance_coupling_reason=row["compliance_coupling_reason"],
    )


async def history(
    conn: AsyncConnection, *, venture_id: str
) -> list[Attestation]:
    """Every attestation a venture holds, newest first. The append-only record, read."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM department_attestation "
            " WHERE venture_id = %s ORDER BY attested_at DESC, attestation_id DESC",
            (venture_id,),
        )
        rows = await cur.fetchall()
    return [
        Attestation(
            attestation_id=r["attestation_id"], venture_id=r["venture_id"],
            department=r["department"], forge_id=r["forge_id"],
            attested_by=r["attested_by"], attested_by_name=r["attested_by_name"],
            attested_at=r["attested_at"],
            escalation_path_verified=r["escalation_path_verified"],
            escalation_path_reason=r["escalation_path_reason"],
            compliance_coupling_verified=r["compliance_coupling_verified"],
            compliance_coupling_reason=r["compliance_coupling_reason"],
        )
        for r in rows
    ]


def handover_test_available(forge_build: dict[str, Any] | None) -> bool | None:
    """Whether SimForge says a department hand-over test exists. `None` when it did not say.

    **THE THING THAT ENDS THE STOP-GAP**, ruled 21 September 2026: when a real hand-over
    test ships, attested unit-B certifications stop counting at Gate 9 and must be
    re-earned.

    Read off the `forge_build` block Gate 8 already recorded, never by a live call - Gate
    9's own rule, in its own words: *"Not a live call to SimForge, deliberately. A
    Readiness Gate verdict reaches The Office by being recorded as a certification, and
    the certification is what the call path enforces."* The build that set the exams is
    the build whose capabilities decide what those exams were worth.

    THREE ANSWERS, AND ONLY ONE OF THEM ENDS ANYTHING
    =================================================

        True   the test exists. Attested units stop counting. They are not deleted and
               not demoted - Gate 9 refuses them, and a run has to earn them again.
        False  SimForge says it has no such test. The stop-gap stands.
        None   SimForge did not say, which is every deployment today. The stop-gap
               stands, and Gate 9 names the key it looked for so the silence is visible.

    `None` and `False` lead to the same behaviour and are kept apart anyway, because they
    call for different responses: one is a Forge to ask, the other is a field to add.
    """
    if not forge_build or not forge_build.get("reachable"):
        return None
    value = forge_build.get(HANDOVER_TEST_KEY)
    return bool(value) if isinstance(value, bool) else None
