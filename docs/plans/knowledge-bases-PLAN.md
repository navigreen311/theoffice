# The four missing knowledge bases, and the Manager — PLAN

Master prompt Part 6 and Part 17, screen 14.

---

## The thing that has to happen first

I have refused this screen three times, in three commit messages, with the same
sentence: *a screen over nothing is worse than an absent screen, because it implies the
thing exists.* That reason has not changed, so the screen is not the increment — **the
four stores are**, and the Manager is what you get once they exist.

Part 6 names five. One is built:

| KB | State |
|---|---|
| 6.1 Forge Operating Instructions | built (Phase 3), versioned, `content_hash` binds certification |
| 6.2 Business Playbooks | **does not exist** |
| 6.3 Compliance Library | **does not exist** |
| 6.4 Persona Library | **does not exist** |
| 6.5 Historical Records | **does not exist** |

## Each store gets one control, and the control is why it is a store

A table with a CRUD screen over it is a filing cabinet. 6.1 was *elevated from filing
cabinet to curriculum* by one property — `content_hash` binds certification, so
republishing decertifies. Each of the four gets the equivalent.

### 6.2 Business Playbooks — sharing is opt-in, structurally

Part 6.2: "Cross-venture patterns shareable **by opt-in only**." A playbook belongs to
one venture. It becomes visible to another only through a row somebody wrote, naming
both ventures and who consented.

Enforced by the read path taking `venture_id` and resolving shares, never by a filter a
caller can omit. The failure mode this prevents is one venture's SOP appearing in
another's context because a `WHERE` clause was forgotten — which is a tenancy breach
that reads as a feature.

### 6.3 Compliance Library — structured, and it makes V4 checkable

Part 6.3 names six fields: framework, jurisdiction, applicability rule,
**agent-behaviour implication**, escalation trigger, citation. All six NOT NULL. An
entry with a citation and no behavioural implication is a legal reference nobody can
act on, and an entry with no escalation trigger tells an agent what to notice and not
what to do about it.

The real change is upstream. `library_entry_ref` in a Pack is **self-attestation
today**: V4 passes whether or not the ref resolves, exactly as a Pack that *declares* a
Forge is bridged proves nothing. So **V28** is a world rule that resolves every
`library_entry_ref` against the library, and a ref pointing at nothing is a
`[COMPLIANCE LIBRARY GAP]` — the same upgrade V2 represents for Gate 0.

### 6.4 Persona Library — SimForge only, enforced by a column grant

Part 6.4 is one line: "SimForge only, never production." The production call path runs
as `office_app`, so:

    GRANT SELECT (persona_id, venture_id, persona_name, target_persona, ...) 
    -- persona_body is NOT in that list
    GRANT INSERT ON persona TO office_app

`office_app` can author a persona and **cannot read its body back**. Not by convention,
not by a missing route — by a column privilege, so a `SELECT persona_body` anywhere in
the runtime, now or later, is an error rather than a leak.

Accepted cost, stated: the console cannot render a persona body either, because it runs
as the same role. Reviewing one is an out-of-band act on the admin connection. That is
the price of the boundary being real, and it is the same trade the held-out partition
makes.

### 6.5 Historical Records — append-only, with a real writer

Part 6.5: "append-only institutional memory." Same enforcement as the ledger: `REVOKE
UPDATE, DELETE` from `office_app` plus a guard trigger, so it is refused at the database
rather than in review.

**And it gets a writer on day one.** Phase 4.1 shipped three controls that were fully
tested and completely inert because nothing ran them; a store nobody writes to is the
same mistake with a different shape. Provisioning run completion and abandonment record
themselves here — those are the institutional facts a venture's history is made of.

## Gate 6 stops lying

Today Gate 6 hardcodes:

```python
"knowledge_bases_missing": ["business_playbooks", "compliance_library",
                            "persona_library", "historical_records"],
```

It becomes a real count per store with denominators — instructions per module,
compliance entries per flag in use, personas per target persona — and blocks on the ones
that block. A hardcoded list is right exactly once and then rots.

## The Manager

`/knowledge`. **Coverage, not browsing.** For each of the five: what exists, out of how
many, and what is missing by name. The gaps are the point; a screen that listed 40
entries and no denominator would be a filing cabinet with search.

Authoring for Compliance Library entries and Business Playbooks, because both have a
computable gap that blocks something. Personas are author-only (the body cannot be read
back). Historical records get a human note form; the rest is written by the system.

## Acceptance tests

| # | Test |
|---|---|
| K1 | a playbook is invisible to another venture until a share row exists |
| K2 | revoking a share hides it again |
| K3 | a compliance entry missing any of the six fields is refused |
| K4 | **V28: a `library_entry_ref` that resolves passes; one that does not is a FAIL** |
| K5 | V28 is NOT_RUN without a connection, never a pass |
| K6 | **`office_app` cannot SELECT `persona_body`** |
| K7 | `office_app` can INSERT a persona |
| K8 | a persona body appears in no API response |
| K9 | `office_app` cannot UPDATE or DELETE a historical record |
| K10 | a completed provisioning run writes a historical record |
| K11 | an abandoned run writes one too, and says it was abandoned |
| K12 | Gate 6 reports real counts and names what is missing |
| K13 | Gate 6 blocks on a compliance flag with no library entry |
| K14 | the Manager renders coverage with denominators for all five |
