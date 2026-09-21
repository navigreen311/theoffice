"""Build an approved answer-key header whose content hash matches its own body.

Entry 141: an approved key records `approved_content_hash` over the text it covers, and
the loader refuses one that disagrees. A fixture that hard-codes a hash goes stale the
first time somebody edits the body beside it, so the hash is derived here from the same
body the test is about.

**The derivation goes through a DRAFT.** Loading the body as a draft exercises every
parse and every refusal except the approval rules, so the hash is taken over what the
loader actually built rather than over a second reading of the YAML. A helper that parsed
the file itself would be a second implementation of `load_module`, and the two would
disagree the first time a field was added.

Tests that are ABOUT the hash do not use this - see
`tests/generators/test_an_approval_names_its_text.py`, which supplies mismatches on
purpose.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from generators import scenario_content as sc


def approved_header(
    body: str,
    *,
    module_id: str = "thing",
    forge_id: str = "cre-forge",
    approved_by: str = "test fixture",
    approved_on: str = "2026-09-20",
) -> str:
    """The `module_id`-through-`approved_content_hash` lines for `body`, as one string.

    `body` is everything from `scenarios:` down, exactly as it will be written.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{module_id}.yaml"
        path.write_text(
            f"module_id: {module_id}\nforge_id: {forge_id}\nstatus: draft\n" + body,
            encoding="utf-8",
        )
        drafted = sc.load_module(path)
    digest = sc.approved_content_hash(drafted.scenarios, drafted.not_applicable)
    return (
        f"module_id: {module_id}\n"
        f"forge_id: {forge_id}\n"
        "status: approved\n"
        f'approved_by: "{approved_by}"\n'
        f'approved_on: "{approved_on}"\n'
        f'approved_content_hash: "{digest}"'
    )
