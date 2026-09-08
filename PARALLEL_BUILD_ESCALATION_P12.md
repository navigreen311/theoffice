# PARALLEL_BUILD_ESCALATION_P12.md

**P-12 needed two files that are not on its card. This is the record, raised before the
PR rather than explained after it.**

## The files

```
tests/golden/snapshots/greenstone_forge_manifest.json
tests/golden/snapshots/greenstone_runtime_config.json
```

Neither is on P-12's MODIFIES list, which names `packs/greenstone.yaml` and
`docs/blocking.md` only. Neither is on the always-forbidden list, and neither belongs to
another package in the shared-file risk map.

## Why they were needed

`packs/greenstone.yaml` is the input to the seven generators, and two of their outputs are
golden-snapshotted against it. Removing `simforge/run_scenario_pack` from the Pack changes
those two artifacts by construction. Left un-recorded, `tests/golden/test_generators.py`
fails on `[forge_manifest]` and `[runtime_config]` — which would put the **`Tests`** job
red in CI. `Tests` is **green in the baseline**, so that is a NEW failure, and a NEW failure
is an automatic hand-back under the merge checklist.

**This is not a discretionary tidy-up.** A golden snapshot is the file whose entire purpose
is to be re-recorded when its source legitimately changes, and the test says so in its own
failure message: *"Read the diff. If the change is intended, re-record with
UPDATE_GOLDEN=1."*

## The rule that already covers this, found after the fact

**`PARALLEL_BUILD.md` Caveat 6 is written for exactly this situation**, and it sanctions
the action outright:

> *"Any package that changes what a generator emits changes
> `tests/golden/snapshots/greenstone_curriculum.json`, and the Tests job goes red until the
> snapshot is re-recorded."*
>
> *"Read the diff before re-recording. That is the substance; `UPDATE_GOLDEN=1` is the
> trivial part. ... If the diff is not what you intended, stop and report — do not
> re-record."*

The diff **is** what was intended, in full, and it is set out below rather than asserted.

**One way this differs from the caveat's own examples, worth a sentence.** Caveat 6 names
**P-00 and P-05** as the packages that would hit it, and reasons about packages that change
**a generator**. P-12 changes a generator's **input** — the Pack — and lands in the same
place by a different route. The caveat's own wording covers it (*"changes what a generator
emits"*), but its list of who would be caught does not, which is presumably why the
snapshots are absent from P-12's card. **A rule stated by mechanism and illustrated by
package list will be read off the list.**

Also worth naming: Caveat 6 is about `greenstone_curriculum.json`, and the two snapshots
that actually moved here are `greenstone_forge_manifest.json` and
`greenstone_runtime_config.json`. The curriculum snapshot is **byte-identical** and is not
in this diff.

## The precedent, which is why this was re-recorded rather than left for the coordinator

`PARALLEL_BUILD.md`, hand-backs section, P-00: six defaulted fields serialised into the
curriculum artifact, the snapshot was not re-recorded, and **`Tests` went red as a NEW
failure.** The recorded fix was *"one re-recorded golden, verified purely additive at
`108 0` — zero deletions, which is the proof no existing value moved."*

The action is the same action. **The verification standard is the part being borrowed**:
show the diff, and show that nothing beyond the intended change moved.

## The diff, in full, because this one is not purely additive

Mine deletes — a removal from a Pack cannot be additive downstream. So the equivalent proof
is that **every deleted line belongs to `run_scenario_pack` and nothing else changed.**

```
1  11  tests/golden/snapshots/greenstone_forge_manifest.json
0   9  tests/golden/snapshots/greenstone_runtime_config.json
```

`greenstone_forge_manifest.json` — two hunks:

1. the nine-line `run_scenario_pack` module object removed whole
   (`criticality: hard`, `declared: true`, `forge_id: simforge`, `module_gap: false`,
   `module_id: run_scenario_pack`, `required: false`, `required_by: []`);
2. `reconciliation.declared_not_required` goes from `["gate_result", "run_scenario_pack"]`
   to `["gate_result"]` — two lines out, one back in, the one insertion being
   `"gate_result"` losing its trailing comma.

`greenstone_runtime_config.json` — one hunk: the same nine-line module object, removed
whole. **Zero insertions.**

**No other key, value, ordering or count moved in either file.** The other five Greenstone
snapshots — `appointment`, `approval_projection`, `curriculum`, `roles`, `workflow` — are
byte-identical and are not in the diff.

## One thing observed and deliberately not acted on

The removed object carried `"module_gap": false` for a module SimForge does not dispatch —
the manifest saw no gap where V32 reported one. **That is not a finding.** It is the V6/V32
distinction `generators/validator.py` already documents: V6 and the manifest resolve against
`forge_module_registry`, which is rows a human wrote, while V32 resolves against the Forge's
own dispatch map. A registry row existed; a handler did not. Noted here so that a reader of
this diff does not have to re-derive it, and left alone because it is neither P-12's file
nor P-12's question.

## What the coordinator is being asked to decide

Whether re-recording these two snapshots inside P-12 was correct, or whether it should have
been left red and handed over. **The change is reversible in one command** — `git checkout
origin/main -- tests/golden/snapshots/` — and if it is reverted, `Tests` goes red on
`[forge_manifest]` and `[runtime_config]` and the PR fails the merge checklist for a reason
that is now written down rather than discovered.

**Nothing else was touched.** `docs/decisions.md` is untouched; entry 25 is P-09's and is
cited, never appended to. No burkham Pack file, no `generators/*`, no `broker/*`, no
`scenarios/*`, no `db/*`, no `.env`, no contract, no plan, no `PARALLEL_BUILD.md`, no CI
workflow, no migration.
