"""Refuse a Compliance Library entry that constrains nothing.

    python scripts/check_compliance_library.py packs/compliance-library/*.yaml

Exit 0 if every entry is complete, 1 otherwise. Prints the specific defect per field,
because "invalid" tells an author nothing about what to write.

WHY A SCRIPT AND NOT A TEST
===========================

    It is both. `tests/validator/test_compliance_quality.py` asserts the assessor
    behaves; this is the thing an author runs while writing, before anything is loaded
    into a database. The failure that matters here happens at authoring time, and a
    check that only runs in CI is a check the author meets after they thought they
    were finished.

WHY IT IS NOT WIRED INTO `author_compliance_entry` YET
======================================================

    Because that would be a policy change, not a tooling one: it would start refusing
    entries somebody may be mid-way through writing, and the two existing entries in
    the development database have not been assessed. The same argument was made about
    calling `curriculum_quality.assess` from `instructions.author()`, and it is the
    same call to make deliberately rather than as a side effect.
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from broker.compliance_quality import assess, assess_provenance  # noqa: E402

TODO_MARKERS = ("todo", "tbd", "fixme", "xxx")

#: The only status that may reach the database.
#:
#: `status` and `notes` are AUTHORING-FILE fields. `ComplianceEntryRequest` does not
#: declare them and Pydantic ignores unknown keys, so POSTing an entry silently drops
#: both — which for a draft entry loses the open question that made it a draft.
#:
#: The fix is not a status column. A `draft` row in the live library is a row a Pack can
#: resolve against and V28 will pass on, which is the same defect one layer over. The
#: file is the right home: it is version-controlled, reviewable, and the open question
#: sits next to the text it qualifies. This checker is what makes that binding — an
#: entry whose status is not `approved` is reported not-ready and must not be loaded.
APPROVED_STATUS = "approved"

#: Fields that live in the file and never travel to the database.
AUTHORING_ONLY_FIELDS = ("status", "notes", "depends_on", "claim_provenance")


def _unmet_dependencies(entry: dict[str, Any]) -> list[str]:
    """Declared dependencies an entry does not yet have.

    WHY AN ENTRY DECLARES WHAT MUST EXIST BEFORE IT CAN FIRE
    ========================================================

        An entry can be complete, approved, loaded, and still enforce nothing —
        because the thing it defers to does not exist yet. `estimate-not-offer-v1`
        obliges a state-specific disclosure variant, and three of the seven states it
        binds have no Regulatory Engine module at all. In those states the entry reads
        as a live control and is one that cannot fire.

        That is the `status: draft` failure one layer out. A draft entry is honest
        about not being ready; an approved entry with an unmet dependency is not, and
        nothing in the file said so.

    WHY DECLARED RATHER THAN QUERIED
    ================================

        This checker deliberately runs without a database — a drift detector that only
        runs where Postgres is up is one that does not run. So a dependency is authored
        alongside the entry and maintained with it: `required_for` names what must
        exist, `satisfied_for` names what does, and the diff is the gap. The same
        discipline as `status`, and version-controlled for the same reason.

        The cost is that `satisfied_for` is human-maintained and can go stale in the
        permissive direction. It is the same trade the file already makes, and the
        alternative — a check that silently skips wherever it cannot reach a database —
        is worse.
    """
    unmet: list[str] = []

    for dep in entry.get("depends_on") or []:
        # A bare string is a capability that does not exist yet, named in prose.
        #
        # The structured form was written first, for per-jurisdiction dependencies
        # where `required_for` is a list of states and `satisfied_for` fills in as they
        # go live. Applied to "VoiceForge participant detection" that shape is noise:
        # there is one thing, it either exists or it does not, and forcing an author to
        # write `required_for: [voiceforge_participant_detection], satisfied_for: []`
        # to say so is ceremony.
        #
        # So a string means exactly that — unsatisfied and blocking — and an author who
        # needs the per-item detail reaches for the mapping. Accepting the natural form
        # matters more than one shape: a field that is awkward to write is a field that
        # gets left out, and a dependency nobody recorded is the thing this exists to
        # prevent.
        if isinstance(dep, str):
            if dep.strip():
                unmet.append(f"capability: {dep.strip()}")
            continue

        if not isinstance(dep, dict):
            unmet.append(f"malformed dependency: {dep!r}")
            continue
        if dep.get("blocking") is False:
            continue

        kind = dep.get("kind", "unnamed dependency")
        required = list(dep.get("required_for") or [])
        satisfied = set(dep.get("satisfied_for") or [])

        if not required:
            # A dependency naming nothing cannot be checked, and reads as satisfied.
            unmet.append(f"{kind}: declared with an empty `required_for`")
            continue

        missing = [item for item in required if item not in satisfied]
        if missing:
            unmet.append(f"{kind}: unmet for {', '.join(str(m) for m in missing)}")

    return unmet


def _print_provenance(prov: dict[str, Any]) -> None:
    """One line on where an entry's claims came from, and the malformed ones named.

    `unmarked` prints rather than staying silent. An entry with no provenance and one
    that is entirely sourced both have zero problems, and only one of them has been
    looked at.
    """
    if prov["unmarked"]:
        print("            provenance: UNMARKED - no claim has been attributed")
        return

    c = prov["counts"]
    print(
        f"            provenance: {c['sourced']} sourced / "
        f"{c['reconstructed']} reconstructed / {c['proposed']} proposed"
        f"  (of {prov['total']})"
    )
    for problem in prov["problems"]:
        print(f"              ! {problem.get('claim', '<unlabelled>')}: {problem['reason']}")


def _has_todo(entry: dict[str, Any]) -> list[str]:
    """Fields still carrying a template marker.

    Checked separately from `assess` so the message can say "this is still the
    template" rather than "this is thin", which are different situations for an author.
    """
    return sorted(
        name
        for name, value in entry.items()
        if isinstance(value, str) and value.strip().lower() in TODO_MARKERS
    )


def check_file(path: Path) -> tuple[int, int]:
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}

    entries = doc.get("entries") or []
    if not entries:
        print(f"{path}: no `entries` key, or it is empty.")
        return (0, 1)

    complete = 0
    failed = 0

    for entry in entries:
        ref = entry.get("entry_ref", "<no entry_ref>")
        todos = _has_todo(entry)

        if todos:
            print(f"\n  TEMPLATE  {ref}")
            print(f"            still a template: {', '.join(todos)}")
            failed += 1
            continue

        result = assess(entry)
        prov = assess_provenance(entry)
        status = str(entry.get("status", APPROVED_STATUS)).strip().lower()
        notes = " ".join(str(entry.get("notes", "")).split())
        unmet = _unmet_dependencies(entry)

        # Checked before status, because an unmet dependency is the stronger refusal:
        # a held entry becomes loadable when a human approves it, and this one does not
        # become loadable until something outside the library exists.
        if unmet and status == APPROVED_STATUS:
            print(f"\n  BLOCKED   {ref}")
            print("            approved, but a declared dependency is unmet:")
            for item in unmet:
                print(f"              - {item}")
            failed += 1
            continue

        if result["state"] == "complete" and status != APPROVED_STATUS:
            # Content finished, entry still held. Reported distinctly from `thin`,
            # because "not written yet" and "written and not yet approved" ask
            # different things of the author.
            print(f"\n  HELD      {ref}")
            print(f"            status: {status}")
            _print_provenance(prov)
            for item in unmet:
                print(f"            also unmet: {item}")
            if notes:
                print(f"            {notes[:280]}{'...' if len(notes) > 280 else ''}")
            failed += 1
            continue

        if result["state"] == "complete":
            print(f"\n  COMPLETE  {ref}")
            _print_provenance(prov)
            complete += 1
            continue

        failed += 1
        print(f"\n  {result['state'].upper():9} {ref}")
        for problem in result["problems"]:
            print(f"            {problem['title']}: {problem['reason']}")

    return (complete, failed)


def main(argv: list[str]) -> int:
    patterns = argv[1:] or ["packs/compliance-library/*.yaml"]
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(p) for p in sorted(glob.glob(pattern)))

    if not paths:
        print(f"no files matched: {', '.join(patterns)}")
        return 1

    total_complete = 0
    total_failed = 0
    for path in paths:
        print(f"\n{path}")
        complete, failed = check_file(path)
        total_complete += complete
        total_failed += failed

    print(
        f"\n{total_complete} complete, {total_failed} not ready.\n"
        "An entry that resolves a Pack's library_entry_ref and constrains nothing is "
        "the 'Documented.' stub one layer over: the Pack's claim of coverage becomes "
        "machine-verified and false."
    )
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
