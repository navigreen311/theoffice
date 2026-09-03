"""5.6 Forge Manifest Generator.

In: bindings + Workflow + Task Ledger. Out: the venture's Bill of Materials, plus the
three-way reconciliation.

**Three states** (Part 15):

  Declared  the Pack names the module in a `forge_binding`
  Required  a Workflow step or Task Ledger entry uses it
  In-Use    it appears in `agent_call_ledger` — runtime, not generation time

At generation time only Declared and Required exist. In-Use is reconciled at runtime by
`broker/manifest.py`, and by the monthly sweep at Gate 15. This generator produces the
rows that runtime check reads, which is why the two must agree on what "required" means.

**Four mismatch handlers**, and the asymmetry between them is deliberate:

| Mismatch | Handler |
|---|---|
| `REQUIRED_NOT_DECLARED` | **fails the Pack.** A step needs a module nobody declared |
| `DECLARED_NOT_REQUIRED` | WARN (V25). Declared and paid for, used by nothing |
| `IN_USE_NOT_REQUIRED` | HIGH incident + auto-throttle — runtime, `broker/manifest.py` |
| `hard` + `module_gap` | **cannot provision** (V8) |

`REQUIRED_NOT_DECLARED` fails rather than auto-declaring the missing module. Silently
adding it would let a workflow grant itself access to any Forge module by referencing
one, which inverts the entire point of a Bill of Materials.
"""

from __future__ import annotations

from generators.artifacts import ForgeManifest, ManifestEntry, Reconciliation, Workflow
from generators.pack import BusinessPack


def generate(pack: BusinessPack, workflow: Workflow) -> ForgeManifest:
    declared: dict[str, tuple[str, str, bool]] = {}
    for binding in pack.forge_dependencies.forge_bindings:
        for module in binding.modules_expected:
            declared[module] = (binding.forge, binding.criticality, binding.module_gap)

    required_by: dict[str, set[str]] = {}
    for step in workflow.steps:
        for module in step.forge_modules:
            required_by.setdefault(module, set()).add(f"workflow step {step.number}")

    entries: list[ManifestEntry] = []
    for module in sorted(set(declared) | set(required_by)):
        forge, criticality, gap = declared.get(module, ("UNDECLARED", "soft", False))
        entries.append(
            ManifestEntry(
                forge_id=forge,
                module_id=module,
                declared=module in declared,
                required=module in required_by,
                criticality=criticality,
                module_gap=gap,
                required_by=sorted(required_by.get(module, ())),
            )
        )

    reconciliation = Reconciliation(
        required_not_declared=sorted(set(required_by) - set(declared)),
        declared_not_required=sorted(set(declared) - set(required_by)),
        hard_dependency_on_gap=sorted(
            m for m, (_f, crit, gap) in declared.items() if crit == "hard" and gap
        ),
    )

    return ForgeManifest(
        venture_id=pack.venture_id, entries=entries, reconciliation=reconciliation
    )
