"""A handover that shows the agent different text mints a different ref.

RULED 23 SEPTEMBER 2026 (decisions entry 176)
=============================================

    *"A run ref names what the exam showed. The instruction sections in the handover
    are part of the ref derivation, so a handover that shows the agent different text
    mints a different ref. Measured: showing all four sections for the first time
    collided with six existing refs, and the collision is silent - open_run returns
    the graded row and the battery skips it, so Gate 8 would report success and the
    old verdicts would return as new."*

THE ONE THAT CARRIES THE RULING
===============================

    `test_showing_the_four_sections_mints_a_different_ref` - the exact transition
    measured on run 4637b946: no sections, then four, same everything else.

WHY THIS IS NOT THE SCENARIO HASH IN A HAT
==========================================

    `test_the_key_hash_does_not_move_when_only_the_prose_does` is the load-bearing
    half. The keys cite the same four section NAMES in both payloads, so
    `scenario_set_hash` is byte-identical; what changed is the PROSE behind those
    names. If that test ever fails, this segment is redundant and should go.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import uuid

from broker.simforge import mint_run_ref, scenario_set_hash, sections_shown_hash

#: The four every Greenstone module's keys cite, measured 22 September 2026.
CITED = ("correct_sequence", "failure_signatures", "inputs", "retry_vs_escalate")

AGENT = uuid.UUID("11111111-2222-3333-4444-555555555555")

PROSE = {name: f"The prose of {name}." for name in CITED}


def _payload(sections: dict[str, str] | None) -> dict:
    """A curriculum payload of the shape Gate 8 builds, cut to what the hashes read."""
    ref: dict = {
        "forge_id": "cre-forge",
        "module_id": "property_lookup",
        "content_hash": "c" * 64,
    }
    if sections:
        ref["sections"] = sections
    return {
        "instruction_set_ref": ref,
        "operation_scenarios": [
            {
                "scenario_class": "happy_path",
                "instruction_section": name,
                "module_id": "property_lookup",
                "expected_behavior": "answer",
                "expected_escalation": None,
            }
            for name in CITED
        ],
        "module_not_applicable": {},
    }


def _ref(payload: dict) -> str:
    return mint_run_ref(
        venture_id="greenstone",
        forge_id="cre-forge",
        module_id="property_lookup",
        content_hash=payload["instruction_set_ref"]["content_hash"],
        office_agent_id=AGENT,
        scenario_hash=scenario_set_hash(payload),
        sections_hash=sections_shown_hash(payload),
        protocol_version="6.0.0",
        rubric_version="0.5.0",
    )


# ======================================================== the ruling

def test_showing_the_four_sections_mints_a_different_ref():
    """**THE RULING**, and the exact collision measured on run `4637b946`.

    Six modules, six refs, six identical to refs already carrying verdicts. Same
    instruction, same keys, same agents, same protocol, same rubric - and four
    sections of prose in the room that had never been there before.
    """
    before = _ref(_payload(None))
    after = _ref(_payload(PROSE))

    assert before != after, (
        "showing four sections for the first time still mints the graded run's ref"
    )


def test_the_new_segment_is_the_only_difference():
    """Nothing else about the ref moved, which is why the collision was invisible."""
    before = _ref(_payload(None)).split(":")
    after = _ref(_payload(PROSE)).split(":")

    added = [s for s in after if s not in before]
    assert len(added) == 1
    assert added[0].startswith("s")
    assert [s for s in before if s not in after] == []


def test_the_key_hash_does_not_move_when_only_the_prose_does():
    """**Load-bearing.** The segment is not redundant with the one beside it.

    The keys cite the same four section NAMES either way, so `scenario_set_hash` -
    which reads `instruction_section` off every row - is byte-identical. The prose
    behind those names is what changed, and no existing segment can see it.
    """
    bare = _payload(None)
    shown = _payload(PROSE)

    assert scenario_set_hash(bare) == scenario_set_hash(shown)
    assert bare["instruction_set_ref"]["content_hash"] == (
        shown["instruction_set_ref"]["content_hash"]
    )
    assert sections_shown_hash(bare) != sections_shown_hash(shown)


def test_editing_one_section_mints_a_different_ref():
    """The ongoing case, after today's transition is spent."""
    edited = dict(PROSE)
    edited["inputs"] = "query is required, and it is a string."

    assert _ref(_payload(PROSE)) != _ref(_payload(edited))


def test_the_same_sections_mint_the_same_ref():
    """Idempotence is the property the whole minter exists for.

    A re-run of Gate 8 against an unchanged handover must land on the run already
    open rather than starting a second window - `mint_run_ref`'s own argument, and
    this segment must not break it.
    """
    assert _ref(_payload(PROSE)) == _ref(_payload(PROSE))
    assert _ref(_payload(dict(reversed(list(PROSE.items()))))) == _ref(_payload(PROSE))


# ======================================================== the absent case

def test_a_handover_showing_nothing_keeps_its_old_shape():
    """**Every ref already open still resolves.**

    The rule the agent segment and the answer-key segment were both added under: an
    absent fact mints no segment, so a run opened before this ruling is addressed by
    the ref it was opened under.
    """
    assert sections_shown_hash(_payload(None)) is None
    assert ":s" not in _ref(_payload(None))


def test_an_empty_map_is_the_same_as_none():
    """`_curriculum_payload` omits the key entirely, but a caller could send `{}`.

    Both mean the same thing - nothing was shown - and they must mint the same ref
    or the two spellings would be two exams.
    """
    empty = _payload(None)
    empty["instruction_set_ref"]["sections"] = {}
    assert sections_shown_hash(empty) is None
    assert _ref(empty) == _ref(_payload(None))


def test_a_payload_with_no_instruction_set_ref_does_not_raise():
    """Defensive, because the minter must never be the thing that fails a handover."""
    assert sections_shown_hash({}) is None
    assert sections_shown_hash({"instruction_set_ref": None}) is None


# ======================================================== unit B

def test_a_department_ref_carries_no_sections_segment():
    """A department run submits no curriculum, so it shows no sections.

    The reason the answer-key segment is unit A only, one field over: a hash here
    would be a claim that something was shown to a run that was handed nothing.
    """
    ref = mint_run_ref(
        venture_id="greenstone",
        forge_id="cre-forge",
        module_id=None,
        department="acquisitions",
        content_hash="d" * 64,
        sections_hash="e" * 64,
        protocol_version="6.0.0",
        rubric_version="0.5.0",
    )
    assert ":s" not in ref
    assert "dept:acquisitions" in ref


# ======================================================== the segment itself

def test_the_segment_carries_no_prose():
    """A ref travels in log lines. Twelve characters of a digest, and nothing else."""
    ref = _ref(_payload(PROSE))
    for name in CITED:
        assert name not in ref
    assert "The prose of" not in ref

    digest = sections_shown_hash(_payload(PROSE))
    assert digest is not None
    assert f"s{digest[:12]}" in ref.split(":")


def test_the_digest_is_domain_separated():
    """It must not be mistakable for an instruction hash.

    `department_basis_hash` is prefixed for the same reason, and says so: a value
    that looks like a `forge_operating_instruction.content_hash` and is not one will
    eventually be looked up as one.
    """
    plain = hashlib.sha256(
        json.dumps(PROSE, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert sections_shown_hash(_payload(PROSE)) != plain


def test_the_hash_reads_the_payload_rather_than_rebuilding_it():
    """Hash the thing itself, so the hash cannot drift from what it names.

    `scenario_set_hash`'s argument, and the reason `_sections_cited_by` is not
    called a second time here: two spellings of one rule agree until one moves.
    """
    # The docstring names the alternative it rejected, so read the body alone.
    body = inspect.getsource(sections_shown_hash).split('"""')[-1]
    assert '"instruction_set_ref"' in body
    assert "_sections_cited_by" not in body
