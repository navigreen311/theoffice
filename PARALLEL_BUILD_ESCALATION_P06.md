# PARALLEL_BUILD_ESCALATION_P06.md

**P-06's escalations.** Same three kinds as `PARALLEL_BUILD_ESCALATION.md` — **BLOCKING**
(the package cannot complete the task as written), **RATIFY** (the package took a decision
it was not clearly authorised to take and is declaring it rather than hiding it), or
**RECORDED** (a finding for whoever holds the contract next; nothing is waiting on it).

**Why this is a separate file rather than an append.** Ruled by the coordinator. P-05
landed 308 lines of `PARALLEL_BUILD_ESCALATION.md` on `main`, and P-06, P-07 and P-08 are
all on branches off the same commit. Three agents appending to one file is a three-way
merge conflict by construction, and it would be a collision created by the filename rather
than by the work. **Entry numbering continues unbroken across both files** — P-05 used
E-001 to E-006, so this file starts at E-007 and a reader looking for E-005 will not find
a second one here.

Neither entry below is BLOCKING. Both content files were authored in full.

---

# P-06 — Office: scenario authorship, the writes group

---

## E-007 — the property that makes E-004's workaround recoverable is not enforced anywhere · **RECORDED**

> **DISPOSITION — RECORDED by the coordinator. Not covered by E-004, and it belongs to
> whoever adds the real `situation` field.** E-004 says the situation has no field and
> rides in prose under fixed labels. This is a different failure: **the splittability
> that makes E-004's workaround recoverable depends on an authoring rule nothing
> enforces.** The safety net fails exactly when it is first used.

**Not a request to change the contract, and not a request to change the loader. A finding
for the person who unwinds the workaround.**

`docs/scenario-generation.md` §7.1 and `AuthoredScenario.wire_behavior()` both state the
convention and both state why it is acceptable: the labels are fixed, the separator is a
blank line, and **the whole justification is that it is mechanically splittable by a
regular expression rather than by a human rereading prose** on the day somebody adds a
real `situation` field to both sides. §7.1 says so in three sentences and then adds the
authoring rule the property actually rests on: *"Do not vary the labels, do not translate
them, and do not put a blank line inside either half."*

**The labels are safe. The blank line is not.**

- The labels are emitted in code by `wire_behavior()`, so no author can vary them.
- **The blank-line rule is addressed to authors and nothing checks it.**

### The mechanism, stated precisely so the check can be written rather than rediscovered

A content file's `situation` and `expected_behavior` are ordinarily written as YAML folded
block scalars (`>`), as in `scenarios/record_consent.yaml`. **In a folded scalar a blank
line does not fold — it survives as a literal `\n\n` in the loaded value.** A paragraph
break is the most natural thing in the world to write in a four-sentence occasion, it is
invisible in the rendered file, and it looks like formatting rather than like data.

`generators/scenario_content.py::_scenario()` validates that each required key is a
present, non-empty string, refuses unknown keys, and calls `.strip()` on the value —
**which removes leading and trailing whitespace and never looks inside.** So a `situation`
containing a blank line:

- loads clean — no refusal, no warning;
- serialises clean into the curriculum artifact;
- submits clean — `expected_behavior` is a non-empty string, which is all §6 requires;
- **grades clean** — a human reading `SITUATION: … EXPECTED: …` reads it correctly, because
  a person is not a regular expression.

It surfaces on exactly one day: when somebody runs the split the convention was designed
to make possible. `wire_behavior()`'s output would then contain more than one `\n\n`, and a
naive `split("\n\n")` returns three pieces where two were promised, while a
`\n\nEXPECTED: ` anchored split silently truncates the situation at its first paragraph
break and drops the rest. **The failure lands on the person unwinding the workaround, at
the moment they are relying on the one property that justified it.**

The same holds, more obviously, for prose containing a literal `EXPECTED:` or `SITUATION:`
token.

### Found twice, independently, and that is the part worth keeping

**P-07 reported the identical defect from a different set of modules, before seeing
P-06's acknowledgment** — same mechanism, same reasoning, same conclusion. The coordinator
ruled that this file is the record and that P-07 references it rather than writing a
second copy.

Two authors finding the same unenforced property separately, **on first contact with the
convention and before writing a line**, is stronger evidence than either report alone: it
says the hole is reachable by an ordinary careful reader rather than by an unusually
suspicious one. It is also the run's recurring shape arriving one level down — **the
property everything depends on is the one nothing checks** — and it was found by the
authors about to write into the convention rather than by the package that built it, which
is the argument for having briefed them to read before writing.

### What P-06 did instead, since the loader is not its file

Held the line by hand and verified it mechanically outside the repo. Every `situation` and
`expected_behavior` in `scenarios/scan_communication.yaml` and
`scenarios/submit_application.yaml` was checked to contain no `\n\n` after loading, no
literal `SITUATION:`/`EXPECTED:` token, and to produce a `wire_behavior()` string
containing **exactly one** `\n\n`. All nine authored scenarios pass. **The loader was not
opened and no test file was added** — both are outside P-06's card.

### The recommendation, deliberately not implemented

Three lines in `_scenario()`, refusing rather than stripping: reject a `situation` or
`expected_behavior` containing a blank line, and reject either containing the literal
label tokens, with a message that says why the property matters. **Whoever adds the real
`situation` field should write that check in the same change they delete
`wire_behavior()` in** — or better, should not need it, because the field exists and the
prose no longer has to carry a second encoding.

---

## E-008 — two manuals instruct a recovery act that is not this module's endpoint · **RECORDED**

**A finding about how the one non-degenerate `recovery_after_failure` in the estate will
be graded. Nothing is blocked on it and the authoring did not change because of it.**

`docs/scenario-generation.md` §2.3 rules that `submit_application` is the single module
whose recovery is not degenerate, and gives the act: *"read the application's status, and
if it is `submitted` the call landed."* P-06 authored it exactly that way, and it is a real
second occasion with its own failure mode — the retry a careless agent makes returns a
`422 INVALID_TRANSITION` that reads as a rejected submission and is in fact the proof the
first call succeeded.

**The observation.** That status read is not `submit_application`. The manual's endpoint
line is `POST /api/applications/:id/submit`, and reading an application's status is a
different call. The same shape appears in `scan_communication` §9 — *"On a timeout, look
for the existing scan"* — where the module is a single `POST /api/comm-compliance/scan`.
So in both cases the section that tells an agent what to do after a failure names an act
the module itself does not perform.

**Why it matters, mildly.** SimForge certifies per `(module, class)`. A
`recovery_after_failure` scenario on `submit_application` therefore grades an agent on a
behaviour that spans grants: the graded act is correct, and it is not reachable through the
module the cert is attached to. If an agent's grant does not include whatever module reads
application status, the certified behaviour is one it cannot perform — and nothing in the
curriculum says so, because the curriculum is keyed on the module and not on the grant.

**The limits of this finding, stated because they are load-bearing.** P-06 has read the
manuals, not CapitalForge's route set, and has not established which other modules the
operating position holds. It is entirely possible the position operates a read that covers
this and the point is moot in practice. **What is checkable from the manuals alone is only
that the act named is not the endpoint declared.**

**Why P-06 did not act on it.** It was noticed while deciding whether
`scan_communication`'s recovery is genuinely degenerate, and the argument "the agent cannot
reach the read" was **rejected for that use** precisely because it applies symmetrically to
`submit_application` — using it on one module and not the other would have been an argument
chosen for its conclusion. `scan_communication`'s declaration therefore rests on the ground
§2.3 sanctions instead: the recovery act there is written inside the escalate section and
is the same hand-off `escalation_required` already grades, which is a statement about the
module rather than about the grant.

**The recommendation, for whoever holds the contract next:** if a scenario's expected
behaviour names an act outside the module's own endpoint, that is worth saying out loud in
the curriculum — either as a field, or as a stated convention that a recovery may span
grants. It is a smaller version of the same thing this run keeps finding: a dependency that
is real, satisfied today by accident, and written down nowhere.
