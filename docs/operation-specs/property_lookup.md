# Operation spec — `cre-forge/property_lookup`

**The first one.** Fifteen modules follow; this is the shape they take.

    module      cre-forge/property_lookup
    read/write  pure read
    drafted     Claude, 20 September 2026, from CRE Forge at 3e48d5d
    ruled       Ivan Green, 20 September 2026 - judgment calls 11-19

## How to read this

Two groups, and the split is a ruling (decisions entry 136, ruling 3):

**Mechanical** judgment calls are answered from code, with a file and a line. Claude
drafts the answer and Ivan corrects it if the reading is wrong.

**Practice** judgment calls are what a competent operator actually does. **Claude drafts
the question only, with no candidate answer** — because a drafted answer is an anchor, and
an anchor is how Claude's judgment becomes Ivan's ruling by being easier to approve than
to replace. Everything in §B below is Ivan's, quoted as given.

---

## A. Mechanical — read from code

**1. A caller asks for `page_size: 500`. What do they get?**
100, silently, with no error. `backend/app/api/forge.py:122` —
`page_size=min(100, max(1, ...))`. Read it back from the response.

**2. A caller sends `page: 0` or a negative page. What do they get?**
Page 1. `forge.py:121` — `page=max(1, ...)`.

**3. No `page_size` is sent. What is used?**
25. `forge.py:122`, the default inside `payload.get("page_size", 25)`.

**4. Is a retry safe after a timeout?**
Yes, unconditionally. `property.py:291-325` is a SELECT and a COUNT; nothing is written
and nothing is sent. `forge.py:124-126` calls it and returns.

**5. Is `total` the whole match or the page?**
The whole match. `property.py:313-316` counts the filtered set; `:319-320` applies offset
and limit afterwards.

**6. Which fields does the query text match against?**
Four: `address`, `city`, `county`, `zip_code`. `property.py:298` builds one `%query%`
pattern; `:300-308` ORs it across those four and nothing else.

**7. Are soft-deleted properties included?**
No. `property.py:301` — `Property.is_deleted == False`. Nothing in the manual says so.

**8. Can a caller narrow by property type, state, price or square footage?**
No. `forge.py:125` passes `filters=None`, so `PropertyFilter` is unreachable through this
module.

**9. What happens if `page` or `page_size` is non-numeric?**
An uncaught `ValueError` → 500, not 422. `forge.py:121-122` coerce with bare `int()`.
`query` is validated at `:104-109`; the pagination arguments are not.

**Filed as CRE Forge #86** — *"Unguarded coercion of untyped input returns 500 where 422
belongs: 15 sites, 6 of them on the Forge surface Greenstone calls."* This module owns two
of those six. The other four are `comp_analysis`'s `radius_miles`, `max_comps` and
`max_age_days` (`forge.py:163-165`) and `buyer_match`'s `limit` (`:217`), so four of the
fifteen remaining specs inherit the same answer and should cite the same issue rather than
re-deriving it.

**Until it closes, the agent's position is unchanged**: a 500 from this module on a
well-formed `query` is a malformed pagination argument, and the agent corrects its own
payload rather than reporting a Forge outage.

**10. Is `total: 0` a failure?**
No — `200` with an empty `results`. There is no 404 on this module; the instruction's
`failure_signatures` says so directly.

---

## B. Practice — ruled by Ivan Green, 20 September 2026

Quoted as given.

**11. Rows returned when a filter doesn't exist.**

> Return them, and label the set for what it is: an answer to part of the request. Name
> the unmet constraint in the agent's own first sentence, before the rows. Never present
> the set in a way that implies it was filtered. If the returned rows carry a type field,
> the agent can filter client-side — and must not, when it holds only one page. Pagination
> happens before any client-side filter, so filtering page 1 of 6 produces a number that
> describes nothing. Client-side filtering is legitimate only when the agent holds the
> complete result set and says that's what it did. Full set in hand → filter and say you
> filtered locally. Partial set → hand over unfiltered rows, name the missing filter,
> don't do arithmetic on them.

**12. Query string beside the count.**

> Every time a count is reported. No exceptions, no "obvious" cases. A bare "143 results"
> is unreadable; "143 results for reno" tells the reader the match was geographic, not
> typological. When no count is reported, the string isn't owed.

**13. Whose wording gets reported.**

> The string the agent actually sent, verbatim, plus a one-clause note that it differs
> from what was asked. The sent string is quoted exactly, never paraphrased, never cleaned
> up. "I searched sparks" not "I searched for Sparks properties."

**14. "Every" match, one page held.**

> Owed, in order: that this is a partial set, the position (page 1 of N, or first 50 of
> 143), the total if the module reports one, and the ordering. With one page in hand the
> agent may not characterize the whole: no "these are all in Washoe County," no "none of
> them have a listed price," no "the prices range from X to Y." Every summary statement
> silently claims completeness. If the caller said "every," either the agent enumerates
> all pages or it makes no claims about the set as a whole.

**15. Nulls worth naming.**

> Either trigger suffices: the null falls in a field the request referenced or depended
> on; or the nulls cluster. One missing square footage is a data entry gap; twelve of
> fourteen is a fact about the dataset and the caller should hear it, regardless of what
> they asked.

**16. Soft-deleted absence.**

> No. "Not in our records" is complete and correct. The carve-out: if soft-delete is ever
> the mechanism for consent revocation, that is not absence and cannot be reported as
> absence. (Confirmed 20 September: separate flags; a revoked buyer keeps their row.)

**17. Stop trying, start asking.**

> Hard budget of three attempts: the literal query, one reformulation, one widening. Then
> ask. Earlier stops override the budget: two consecutive zero-result queries; the next
> reformulation would require guessing what the caller meant; the next widening would
> change the request rather than loosen it. When it asks, it asks something specific —
> "did you mean the Prater Way property or the one on Greg Street" — never "could you
> clarify."

**18. A query string worth sending.**

> The agent must be able to name which of the four searched fields the string could
> literally appear in. If it can't, don't send it. Single geographic tokens and street
> fragments are valid; multi-word conceptual queries — "Reno warehouse," "industrial
> Sparks" — are not. When a request decomposes into a sendable part and an unsendable
> part, send the sendable part and handle the remainder under 11 and 19.

**19. Who's told when the module can't answer what was asked.**

> The caller, in the same turn, in the agent's opening sentence — before the partial
> results. Phrased in terms of the request, not the implementation: "I can't filter by
> property type here, so these are all Sparks properties regardless of type." Second
> audience: a recurring gap belongs in the weekday digest as a capability gap with a
> count. Property type is the first entry.

---

## C. What this spec obliged, in the answer key

Four scenarios changed the day the spec was ruled, and `property_lookup` returned to
draft. See decisions entry 140.

    happy_path[0]        query "Reno warehouse" -> "Reno"          spec 18, 11, 19
    happy_path[2]        query "industrial in Sparks" -> "Sparks"  spec 18, 11, 19
    partial_failure[1]   caveat naming the page the 2 was counted over    spec 14
    partial_failure[2]   caveat naming the page the 1 was counted over    spec 14

## D. Open, and owed elsewhere

- **Spec 19's second audience** — *"a recurring gap belongs in the weekday digest as a
  capability gap with a count. Property type is the first entry."* No weekday digest
  exists in The Office today. Raised, not built.
- **Mechanical 9** — a non-numeric `page` is a 500. **CRE Forge #86**, open, covering all
  fifteen unguarded coercion sites. Not an open question on this side: the answer is
  recorded above and the fix is theirs.
- **Spec 16's carve-out** is already discharged: soft-delete and consent revocation are
  separate flags, confirmed 20 September and recorded in decisions entry 138.
