"""A verdict set from a key that has since changed is read, reported and not written.

RULED 21 SEPTEMBER 2026 (entry 142)
===================================

    *"Ingest also refuses a verdict whose submission's scenario-set hash differs from
    the currently approved key's."*

WHAT MADE IT A RULING
=====================

    The first run of `sweep_verdict_ingest`, on 20 September, ingested four PASS
    verdicts from the run abandoned the night before. Every one was graded against
    answer keys entries 137 and 140 had since corrected - including `property_lookup`,
    on the exact text the first operation spec obliged a change to.

    All four were overwritten inside the same pass, because `overdue_submissions`
    orders by `submitted_at` and the live run's exams for those modules came back
    IN_PROGRESS afterwards. **That is loop order, not a control.** Reverse the arrival
    times and the four would have stood.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_the_approved_key_hashes_to_what_gate_8_would_send`. Every other test here
    compares two hashes; if the hash this side derives is not the one Gate 8 puts on
    the wire, they all still pass and the sweep refuses every verdict in the system for
    a reason that was never true.

    The second is `test_a_matching_hash_is_not_stale`. A `_stale_key` that returned a
    value unconditionally would satisfy every refusal test in this file.
"""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path

import pytest

from broker import provisioning, simforge, sweeps
from generators import curriculum as curriculum_gen
from generators import scenario_content as sc
from tests.approval import approved_header

#: A real Greenstone module with an approved key, so the fixtures are not the only
#: thing this file has ever seen. Its hash is read, never written here.
#:
#: **Was `property_lookup` until 21 September**, when that key went back to draft for
#: three rewrites - and a draft has no approved hash to compare a ref against, which is
#: `_stale_key`'s third answer rather than a failure. `buyer_match` is the approved key
#: whose live ref segment (`k0049a8e5ddab`) is on the submissions of 21 September.
LIVE_MODULE = "buyer_match"

_BODY = """
scenarios:
  - scenario_class: happy_path
    derivation: reproducible
    situation: A caller asks for a thing and the module returns it.
    expected_behavior: Report what came back and nothing further.
    expected_escalation: None fires; the call answered completely.
not_applicable:
  malformed_input: Nothing a caller sends to this module can be wrong.
  partial_failure: Every response is total; there is no partial shape.
  rate_limited: This Forge cannot return 429 on a module call.
  permission_denied: There is no permission boundary on this module.
  escalation_required: There is no juncture at which this module hands over.
  recovery_after_failure: The only recovery is the free retry.
"""

_EDITED = _BODY.replace(
    "Report what came back and nothing further.",
    "Report what came back, and name the page the count describes.",
)


def _key(tmp_path: Path, body: str, *, status: str = "approved") -> Path:
    """One answer key on disk, module `thing`, approved against its own body."""
    if status == "approved":
        head = approved_header(body, approved_by="Ivan Green", approved_on="2026-09-21")
    else:
        head = "module_id: thing\nforge_id: cre-forge\nstatus: draft"
    path = tmp_path / "thing.yaml"
    path.write_text(textwrap.dedent(head).strip() + "\n" + body, encoding="utf-8")
    return path


def _submission(**over):
    """The columns `_ingest_one` reads off a row, and nothing else."""
    sub = {
        "submission_id": uuid.uuid4(),
        "module_id": "thing",
        "scenario_set_hash": "a" * 64,
        "simforge_run_ref": "office:v:cre-forge:thing@agent:hash:kaaaaaaaaaaaa",
        "hours_waiting": 2.0,
    }
    sub.update(over)
    return sub


def _findings():
    return {
        "examined": 0, "ingested": 0, "rows_written": 0, "still_open": 0,
        "timed_out": 0, "by_verdict": {}, "basis_unrecoverable": [], "refused": [],
        "no_grant_holders": [], "unreadable": [],
        "scenario_set_stale": [], "scenario_set_unverifiable": [],
        "_approved_hashes": {},
    }


# ----------------------------------------------- the hash this side derives is the one sent

def test_the_approved_key_hashes_to_what_gate_8_would_send(tmp_path):
    """**The load-bearing test.**

    `approved_scenario_set_hash` claims to produce the identity Gate 8 puts on the
    wire. It is only a staleness check if that is true: a second spelling of the
    payload rows would drift, every submission would read as stale, and the sweep would
    refuse verdicts over its own arithmetic.

    So the key is loaded, the curriculum rows are built, and `_curriculum_payload` -
    the real one, the function Gate 8 calls - is asked for the payload. The two hashes
    must be the same value.
    """
    content = sc.load_module(_key(tmp_path, _BODY))
    rows = curriculum_gen.module_scenarios("thing", content)

    class _Instruction:
        forge_id = "cre-forge"
        module_id = "thing"
        instruction_version = "1.0.0"
        forge_api_version = "1.4.0"
        content_hash = "c" * 64

        @property
        def content(self) -> dict:
            return {}

    payload = provisioning._curriculum_payload(
        instruction=_Instruction(), scenarios=rows, candidates=[],
        modules_in_forge=5, modules_uncovered=[], venture_id="greenstone",
    )
    assert simforge.scenario_set_hash(payload) == simforge.approved_scenario_set_hash(
        "thing", root=tmp_path
    )


def test_a_live_greenstone_key_produces_the_hash_its_run_ref_carries():
    """Against the tree, not a fixture.

    `mint_run_ref` appends `k` and the first twelve characters of this hash, and the
    live 20 September submissions for `property_lookup` carry `k7102df614610`. This
    asserts the derivation agrees with the value Gate 8 actually minted - which is the
    same claim as the test above, made against real approved text rather than a
    six-line fixture.
    """
    digest = simforge.approved_scenario_set_hash(LIVE_MODULE)
    assert digest is not None, f"{LIVE_MODULE} has no approved key"
    assert simforge.mint_run_ref(
        venture_id="greenstone", forge_id="cre-forge", module_id=LIVE_MODULE,
        content_hash="d" * 64, scenario_hash=digest,
    ).endswith(f"k{digest[:12]}")


# --------------------------------------------------------------------- the comparison

def test_a_matching_hash_is_not_stale(tmp_path):
    """**The second load-bearing test**: a `_stale_key` that always refused would pass
    every other test in this file and stop certification on the platform."""
    assert simforge.approved_scenario_set_hash("thing", root=tmp_path) is None

    digest = simforge.approved_scenario_set_hash("thing", root=_root(tmp_path, _BODY))
    findings = _findings()
    findings["_approved_hashes"]["thing"] = digest

    assert sweeps._stale_key(_submission(scenario_set_hash=digest), findings) is None
    assert findings["scenario_set_stale"] == []
    assert findings["scenario_set_unverifiable"] == []


def test_an_edited_key_makes_the_older_submission_stale(tmp_path):
    """The case that happened: the key was corrected after the exam was set.

    Both hashes are DERIVED, neither is written down - so this asserts that editing one
    sentence of an approved answer key changes the identity, rather than asserting a
    constant somebody typed.
    """
    was = simforge.approved_scenario_set_hash("thing", root=_root(tmp_path, _BODY))
    now = simforge.approved_scenario_set_hash("thing", root=_root(tmp_path, _EDITED, "b"))
    assert was != now

    findings = _findings()
    findings["_approved_hashes"]["thing"] = now
    assert sweeps._stale_key(_submission(scenario_set_hash=was), findings) == now
    assert findings["scenario_set_stale"] == []  # the caller appends, not the check


# ------------------------------------------------------ the third answer, which does not refuse

def test_a_submission_with_no_hash_is_unverifiable_and_not_refused(tmp_path):
    """Every row written before 0046. An unknown hash is not a mismatch.

    Refusing these would be a rule nobody ruled, and it would strand the twenty
    Burkham rows on a ruling about corrected Greenstone approvals.
    """
    findings = _findings()
    findings["_approved_hashes"]["thing"] = simforge.approved_scenario_set_hash(
        "thing", root=_root(tmp_path, _BODY)
    )
    assert sweeps._stale_key(_submission(scenario_set_hash=None), findings) is None
    assert len(findings["scenario_set_unverifiable"]) == 1
    assert "no scenario-set hash" in findings["scenario_set_unverifiable"][0]["why"]


def test_a_draft_key_is_unverifiable_and_not_refused(tmp_path):
    """A module whose key nobody has approved has no approved key to differ from."""
    _key(tmp_path, _BODY, status="draft")
    assert simforge.approved_scenario_set_hash("thing", root=tmp_path) is None

    findings = _findings()
    findings["_approved_hashes"]["thing"] = None
    assert sweeps._stale_key(_submission(), findings) is None
    assert len(findings["scenario_set_unverifiable"]) == 1
    assert "no approved answer key" in findings["scenario_set_unverifiable"][0]["why"]


def test_a_module_with_no_key_at_all_is_unverifiable(tmp_path):
    """`parse_document` and every other module the contract suite invents."""
    findings = _findings()
    assert sweeps._stale_key(_submission(), findings) is None
    assert len(findings["scenario_set_unverifiable"]) == 1


# --------------------------------------------------------------- through the sweep itself

class _Client:
    def __init__(self, result):
        self.result = result
        self.asked: list[str] = []

    async def office_gate_result(self, conn, *, run_ref: str):
        self.asked.append(run_ref)
        return self.result


@pytest.mark.asyncio
async def test_a_stale_pass_is_read_counted_and_not_written(tmp_path):
    """The whole ruling, end to end, against the shape that actually failed.

    `conn` is None on purpose. The refusal must happen before anything touches the
    database, so a version of this that wrote a certification first and retracted it
    after would raise here rather than pass.
    """
    approved = simforge.approved_scenario_set_hash("thing", root=_root(tmp_path, _BODY))
    sub = _submission(scenario_set_hash="0" * 64)
    findings = _findings()
    findings["_approved_hashes"]["thing"] = approved

    client = _Client(simforge.GateResult(
        run_ref=sub["simforge_run_ref"], unit="A", verdict="PASS",
        rubric_kind="operation", rubric_version="2.3.1", score=1.0, threshold=1.0,
        certified_tier="propose", scenario_count=7, coverage_denominator=7,
        agent_model="ollama/phi4:latest", model_identity={},
    ))
    await sweeps._ingest_one(None, client, sub, findings)

    # ASKED, then refused. The verdict is on the record even though nothing was written.
    assert client.asked == [sub["simforge_run_ref"]]
    assert findings["by_verdict"] == {"PASS": 1}
    assert findings["rows_written"] == 0
    assert findings["ingested"] == 0
    assert findings["refused"] == []  # not this sweep failing; this sweep working

    stale = findings["scenario_set_stale"]
    assert len(stale) == 1
    assert stale[0]["verdict"] == "PASS"
    assert stale[0]["submitted_hash"] == "0" * 64
    assert stale[0]["approved_hash"] == approved


@pytest.mark.asyncio
async def test_a_stale_timeout_is_refused_too(tmp_path):
    """A TIMEOUT this sweep synthesised for a withdrawn exam says nothing about an
    agent - not even that it did not answer. The live exam moves that certification."""
    findings = _findings()
    findings["_approved_hashes"]["thing"] = simforge.approved_scenario_set_hash(
        "thing", root=_root(tmp_path, _BODY)
    )

    class _Silent:
        async def office_gate_result(self, conn, *, run_ref: str):
            raise simforge.SimForgeError("no record of that run")

    sub = _submission(scenario_set_hash="0" * 64, hours_waiting=72.0)
    await sweeps._ingest_one(None, _Silent(), sub, findings)

    assert findings["by_verdict"] == {"TIMEOUT": 1}
    assert findings["timed_out"] == 1
    assert findings["rows_written"] == 0
    assert len(findings["scenario_set_stale"]) == 1


def _root(tmp_path: Path, body: str, name: str = "a") -> Path:
    """A directory holding one key, so two versions can exist side by side."""
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    _key(root, body)
    return root
