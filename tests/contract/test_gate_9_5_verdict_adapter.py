"""The Gate 9.5 adapter, against SimForge's published contract and nothing else.

SIMFORGE NAMED THE SHAPE. THE OFFICE RECORDS IT, IN THAT ORDER.
===============================================================

    `docs/contracts/gate-9-5-verdict.md` in SimForge's tree, decided in their ADR-0108
    and implemented in ADR-0111. Its own words:

        *"Nothing on The Office's side may guess past this page."*

    That sentence is there because a guess about another system's response reads as
    that system's silence, and it once cost two days (entry 144). So the contract is
    quoted in this file and every assertion traces to a line of it.

THE ADAPTER, VERBATIM FROM THE PAGE
===================================

        partition_exists == false  ->  None   (Gate 9.5: at ceiling)
        otherwise                  ->  verdict verbatim

    Two lines, and `test_the_two_lines_of_the_contract` is both of them.

WHAT THIS DELIBERATELY DOES NOT DO
==================================

    It does not decide what a verdict MEANS. `_gate_9_5` holds that rule - only PASS
    advances, NOT_RUN is not a pass, TIMEOUT is not a failure - and a second place
    deciding it is how two spellings of one rule start disagreeing.

    It does not read `decided_at` into anything. The port answers one question.

    It does not look at simulation. The page: *"A venture in simulation gets the same
    answer. SimForge is blind to simulation. The Office's gate decides."*
"""

from __future__ import annotations

import pytest

from broker import provisioning
from broker.simforge import SimForgeClient, SimForgeError

VENTURE = "greenstone"

#: Every verdict the contract's table admits, in its own order.
VERDICTS = ("PASS", "FAIL", "NOT_RUN", "IN_PROGRESS", "TIMEOUT")


def _body(**over):
    body = {
        "venture_id": VENTURE,
        "partition_exists": True,
        "verdict": "PASS",
        "decided_at": "2026-09-23T18:00:00Z",
    }
    body.update(over)
    return body


#: The contract's own table, transcribed. State -> the three answered fields.
CONTRACT_TABLE = (
    ("unknown venture", False, None, None),
    ("no sealed partition", False, None, None),
    ("sealed, never graded", True, "NOT_RUN", None),
    ("graded", True, "FAIL", "2026-09-23T18:00:00Z"),
)


class _Response:
    def __init__(self, status_code: int, body=None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class _Http:
    def __init__(self, response) -> None:
        self.response = response
        self.url = None
        self.headers = None
        self.json = None

    async def post(self, url, *, json=None, headers=None, timeout=None):
        self.url, self.headers, self.json = url, headers, json
        return self.response

    async def get(self, url, **kw):  # pragma: no cover - must not be called
        raise AssertionError(f"gate_9_5_verdict is a POST, not a GET to {url}")


class _Credential:
    def reveal(self) -> str:
        return "tenant-token"


def _client(response):
    http = _Http(response)
    client = SimForgeClient(object(), http=http)

    async def _cred(_conn):
        return _Credential()

    async def _reg(_conn):
        return "http://simforge.example:8110/office", "1.0.0"

    client._tenant_credential = _cred  # type: ignore[method-assign]
    client._registry = _reg  # type: ignore[method-assign]
    return client, http


async def _ask(body, status=200):
    client, http = _client(_Response(status, body))
    return await client.gate_9_5_verdict(object(), VENTURE), http


# ======================================================== the two lines

async def test_the_two_lines_of_the_contract():
    """**THE ADAPTER.** `partition_exists == false -> None; otherwise -> verbatim.`"""
    absent, _ = await _ask(_body(partition_exists=False, verdict=None, decided_at=None))
    assert absent is None

    for verdict in VERDICTS:
        got, _ = await _ask(_body(verdict=verdict))
        assert got == verdict, f"{verdict} was not returned verbatim"


@pytest.mark.parametrize("state,exists,verdict,decided", CONTRACT_TABLE)
async def test_every_row_of_the_contracts_table(state, exists, verdict, decided):
    """The four states the page tabulates, each answered as the page says."""
    got, _ = await _ask(_body(partition_exists=exists, verdict=verdict,
                              decided_at=decided))
    assert got == (None if not exists else verdict), state


async def test_an_unknown_venture_is_indistinguishable_from_an_absent_partition():
    """The page says so in as many words, and it is a property not an accident.

    Both are `partition_exists: false`, so both answer None here and Gate 9.5 blocks
    with one reason. Telling them apart would be telling a caller which ventures
    SimForge has heard of.
    """
    unknown, _ = await _ask(_body(venture_id="no-such-venture",
                                  partition_exists=False, verdict=None, decided_at=None))
    absent, _ = await _ask(_body(partition_exists=False, verdict=None, decided_at=None))
    assert unknown is absent is None


async def test_not_run_is_returned_and_not_translated():
    """**The gate owns what a verdict means, not this.**

    `NOT_RUN` is the state of a sealed partition nobody has graded. Turning it into
    None here would make it read as "no partition", and `_gate_9_5`'s own docstring
    says NOT_RUN is not a pass - a rule that needs the value to still be NOT_RUN.
    """
    got, _ = await _ask(_body(verdict="NOT_RUN", decided_at=None))
    assert got == "NOT_RUN"


async def test_decided_at_is_read_and_not_returned():
    """The port answers one question, and the page's adapter section names one value."""
    got, _ = await _ask(_body(verdict="FAIL", decided_at="2020-01-01T00:00:00Z"))
    assert got == "FAIL"


# ======================================================== the one invariant

async def test_a_body_that_breaks_the_null_iff_rule_is_refused():
    """*"verdict is null if and only if partition_exists is false."* On the page.

    Checked because the two branches read one field each: `partition_exists: true`
    with a null verdict would return None and be indistinguishable from an absent
    partition. Which field is wrong is not knowable from this side, so it refuses.
    """
    with pytest.raises(SimForgeError) as caught:
        await _ask(_body(partition_exists=True, verdict=None))
    assert "if and only if" in str(caught.value)

    with pytest.raises(SimForgeError):
        await _ask(_body(partition_exists=False, verdict="PASS"))


async def test_a_non_boolean_partition_exists_is_refused():
    with pytest.raises(SimForgeError):
        await _ask(_body(partition_exists="true"))


async def test_a_non_string_verdict_is_refused():
    with pytest.raises(SimForgeError):
        await _ask(_body(verdict=1))


# ======================================================== the shape

async def test_an_undeclared_field_is_refused_by_the_manifest():
    """**The guard against the page being quietly widened.**

    The contract says four keys and never any other. `validate_response` is what makes
    that true on arrival rather than on trust: a fifth field fails here instead of
    being stored by whatever happened to read it.
    """
    with pytest.raises(SimForgeError) as caught:
        await _ask(_body(partition_digest="abc123"))
    assert "manifest" in str(caught.value)


async def test_the_manifest_declares_exactly_the_contracts_four_keys():
    import json

    from broker.simforge import MANIFEST_PATH

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert set(manifest["gate_9_5_verdict"]["fields"]) == {
        "venture_id", "partition_exists", "verdict", "decided_at",
    }


async def test_no_key_carries_a_forbidden_name_fragment():
    """The page names The Office's own forbidden fragments and stays clear of them.

    Asserted against the manifest rather than one response, because the manifest is
    what a future field would have to be added to.
    """
    import json

    from broker.simforge import MANIFEST_PATH

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for name in manifest["gate_9_5_verdict"]["fields"]:
        for fragment in ("held_out", "heldout", "prompt", "scenarios"):
            assert fragment not in name


# ======================================================== the call itself

async def test_it_posts_to_the_adapter_surface_with_the_tenant_credential():
    """Not agent facing, so it travels the hand-over's path.

    Gate 9.5 runs during provisioning and the answer is about the venture, not about
    an agent - so there is no agent a grant could name. The page specifies the tenant
    credential for the same reason.
    """
    _, http = await _ask(_body())

    assert http.url == "http://simforge.example:8110/office/gate_9_5_verdict"
    assert http.headers["Authorization"] == "Bearer tenant-token"
    assert http.json == {"venture_id": VENTURE}


def test_the_module_is_recorded_as_not_agent_facing():
    from broker import forge_modules

    why = forge_modules.not_agent_facing("simforge", "gate_9_5_verdict")
    assert why and "no agent" in why


# ======================================================== when it cannot be read

async def test_a_4xx_is_reported_as_a_fault_and_never_as_an_answer():
    """The page: *"A 4xx is auth or a malformed body only. It never depends on the
    venture."* So it says nothing about the partition and must not be read as if it
    did."""
    with pytest.raises(SimForgeError) as caught:
        await _ask(_body(), status=403)
    assert "not an answer about the partition" in str(caught.value)


async def test_an_unreachable_forge_raises_rather_than_answering_none():
    """**Entry 177, arriving here the moment the source stops being a constant.**

    `None` is a statement that SimForge has no sealed partition. An unreachable Forge
    reported as an absent partition is a false fact about SimForge written into a
    gate's evidence, and it reads identically to the true one.
    """
    import httpx

    class _Down:
        async def post(self, *a, **kw):
            raise httpx.ConnectError("refused")

    client = SimForgeClient(object(), http=_Down())

    async def _cred(_conn):
        return _Credential()

    async def _reg(_conn):
        return "http://simforge.example:8110/office", "1.0.0"

    client._tenant_credential = _cred  # type: ignore[method-assign]
    client._registry = _reg  # type: ignore[method-assign]

    with pytest.raises(SimForgeError) as caught:
        await client.gate_9_5_verdict(object(), VENTURE)
    # The exception TYPE, never its message: the message can carry the URL, and this
    # request carried a credential.
    assert "ConnectError" in str(caught.value)
    assert "tenant-token" not in str(caught.value)


# ======================================================== the port

class _Answers:
    def __init__(self, answer) -> None:
        self.answer = answer
        self.asked = None

    async def gate_9_5_verdict(self, conn, venture_id):
        self.asked = venture_id
        return self.answer


class _Raises:
    async def gate_9_5_verdict(self, conn, venture_id):
        raise SimForgeError("could not reach SimForge: ConnectError")


async def test_the_held_out_source_passes_the_answer_through():
    client = _Answers("FAIL")
    source = provisioning.SimForgeHeldOut(client, object())

    assert await source.verdict(VENTURE) == "FAIL"
    assert client.asked == VENTURE


async def test_the_held_out_source_passes_none_through():
    source = provisioning.SimForgeHeldOut(_Answers(None), object())
    assert await source.verdict(VENTURE) is None


async def test_the_held_out_source_asserts_the_ports_own_type():
    """`client` is Any so a fake can stand in, which puts the assertion here."""
    source = provisioning.SimForgeHeldOut(_Answers(object()), object())
    with pytest.raises(SimForgeError):
        await source.verdict(VENTURE)


async def test_partition_absent_still_means_what_it_said():
    """Unchanged, and still the default. Swapping the default is a deployment act."""
    assert await provisioning.PartitionAbsent().verdict(VENTURE) is None


# ======================================================== the gate

async def _gate(source):
    from types import SimpleNamespace

    ctx = SimpleNamespace(held_out=source, venture_id=VENTURE)
    return await provisioning._gate_9_5(ctx)


def _source(answer):
    """The real port over a fake client, so the gate sees what it would in production."""
    return provisioning.SimForgeHeldOut(_Answers(answer), object())


def _failing_source():
    return provisioning.SimForgeHeldOut(_Raises(), object())


async def test_the_gate_blocks_on_an_unreadable_verdict_and_says_which_kind():
    """**Not the same block as an absent partition**, and the difference is what the
    operator does next: stand the partition up, or look at a service."""
    outcome = await _gate(_failing_source())

    assert outcome.verdict == "blocked"
    assert outcome.evidence["blocked_by"] == "held_out_verdict_unreadable"
    assert "nobody was able to ask" in outcome.reason


async def test_the_gate_still_blocks_on_an_absent_partition_as_it_did():
    outcome = await _gate(provisioning.PartitionAbsent())

    assert outcome.verdict == "blocked"
    assert outcome.evidence["blocked_by"] == "held_out_partition_not_created"


async def test_the_two_blocks_are_told_apart_by_the_evidence():
    unreadable = await _gate(_failing_source())
    absent = await _gate(provisioning.PartitionAbsent())
    assert unreadable.evidence["blocked_by"] != absent.evidence["blocked_by"]


async def test_only_pass_advances_the_gate():
    """The rule the adapter deliberately does not hold, asserted where it does live."""
    assert (await _gate(_source("PASS"))).verdict == "passed"
    for verdict in ("FAIL", "NOT_RUN", "IN_PROGRESS", "TIMEOUT"):
        outcome = await _gate(_source(verdict))
        assert outcome.verdict == "blocked", verdict
        assert outcome.evidence["verdict"] == verdict
