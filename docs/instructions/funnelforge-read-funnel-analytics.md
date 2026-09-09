# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `read_funnel_analytics`
**Endpoint:** `GET /api/analytics/dashboard`
**Version:** 1.0 — drafted 9 September 2026, against `adapters/funnelforge/` at `ac6475c` and
the running FunnelForge stack
**Status:** draft, pending Compliance Review Board

Read `funnelforge-approved-send-rules.md` first. Rules 1, 2, 4 and 5 govern this module. The
send rules — 3, 6, 7, 8, 9 — do not apply: this is the only read of the nine, it is
non-mutating, and it retries freely.

**This module is one of two V31 permits at `auto_execute`**, the other being
`capture_contact`. It is permitted because it is non-mutating, which is a fact about the
route and not a judgement about the answer.

**Three things about it are counter-intuitive and each is load-bearing.** It takes date
arguments and ignores them (§3). It is scoped to a *user account*, not to a venture or a
business (§2). And its answer may be up to ten minutes old with nothing saying so (§5).

## 1. WHAT IT DOES

Returns six aggregate numbers about funnel performance over **the last thirty days**, for
every business the brokered FunnelForge account owns.

One call, one answer:

| Field | What it is |
|---|---|
| `totalVisitors` | Distinct `visitorId` values on analytics events in the window |
| `totalPageViews` | Count of `PAGE_VIEW` events in the window |
| `totalLeads` | Count of `Lead` rows created in the window |
| `totalRevenue` | **Sum of `Order.total` for `COMPLETED` orders in the window** |
| `conversionRate` | `FORM_SUBMIT` count / `PAGE_VIEW` count × 100 |
| `funnelCount` | Number of funnels across those businesses — **not windowed** |

**`totalRevenue` is money, and it is worth naming because a reader would not expect it.** The
binding proposal describes this module as *"anonymous browsing and pixel data, aggregated"*,
which is true about the PII and incomplete about the content. A completed-order total is not
browsing data. It is still within §6.2's cap — no named contact, no credit data, nothing
FCRA-regulated — and it is still a revenue figure that an agent can quote.

**No named contact appears anywhere in the answer.** No lead, no email, no business name, no
funnel name. The response is six scalars. That is the module's defining property and most of
§7 follows from it.

## 2. WHAT IT DOES NOT DO

**It does not scope to Burkham. It scopes to a user account.** The handler reads the user id
out of the JWT and starts from `prisma.business.findMany({ where: { userId } })`. There is no
tenant, no venture and no business filter. **The answer covers every business that FunnelForge
account owns.**

Combined with shared rule 5 — there is no tenant credential, so The Office brokers one user's
token — this means: **the denominator of every figure here is "whatever that one account
owns", and nothing in the answer says what that is.** `funnelCount` is the only hint, and it
is a count without names. If the account owns anything that is not Burkham, it is in these
numbers, silently.

**It does not accept a date range**, however much the module's arguments suggest it. §3.

**It does not say when it was computed.** There is no `computedAt`, no `asOf`, no window
description. Compare `capitalforge-portfolio-health.md`, which stamps one per call — this
module stamps nothing.

**It does not tell you the answer was cached.** §5. The route signals it in a header and the
adapter discards headers (shared rule 2).

**It does not write.** No row changes. **A brokered call is the exception and it is not this
module's doing** — a call arriving through The Office writes one ledger row per call,
`office.module.called`, keyed by the trace id, whatever the module does, reads included.

**It does not read anything about an individual.** No PII of any kind is in the response.

**It does not reach underwriting data, and it never will.** §6.3 of the marketing-plan intake
makes the separation architectural rather than policy: FunnelForge holds no credit data, no
Plaid data, no financial statements, nothing FCRA-regulated, and *"FunnelForge cannot query
Console for credit data to segment marketing sequences."* **That bounds this surface for good,
not for V1.**

**It does not count contacts captured through The Office in `conversionRate`.** A
`FORM_SUBMIT` event is written only when a funnel id and a page id are supplied, and
`capture_contact` supplies neither (`funnelforge-capture-contact.md` §2). Those contacts land
in `totalLeads` and not in the numerator of the conversion rate. **So the more contacts agents
capture, the lower the conversion rate reads.**

## 3. WHAT EACH INPUT MEANS

| Field | Meaning |
|---|---|
| `start_date` | **Accepted, transmitted, and ignored by the receiving handler** |
| `end_date` | **Accepted, transmitted, and ignored by the receiving handler** |

**There is no third input, and there is no real first or second.**

The adapter builds a query string from them — `start_date` becomes `startdate`, `end_date`
becomes `enddate` — and sends it. `GET /api/analytics/dashboard` reads the user id from the
token and **nothing at all from `request.query`.** The window is computed in the handler:

```js
const last30Days = new Date();
last30Days.setDate(last30Days.getDate() - 30);
```

**Always thirty days, always ending now.** Whatever dates are supplied.

This is the `ipAddress` shape from `capitalforge-record-consent.md` §3, and it is more
dangerous here because the field's name promises exactly the thing a caller wants. **An agent
asked for last quarter's numbers can supply last quarter's dates, receive a 200, and report
the last thirty days as the quarter.** Nothing anywhere reports the substitution.

**So the honest rule is: this module answers one question and it is not parameterised.** If
the question has a period in it, the period cannot be honoured and the agent must say so
before answering. §6.

**`funnelCount` is not even windowed**, unlike the other five. It is every funnel those
businesses have, ever. Reporting it beside five thirty-day figures without saying so implies a
window it does not have.

## 4. THE CORRECT SEQUENCE

Four steps, and two of them are about the answer rather than the call:

1. **Establish what period the asker means, before calling.** If it is not "the last thirty
   days", this module cannot answer and no module on this Forge can. §6.
2. **Call.** No arguments are needed and none has an effect.
3. **Read `upstream.status`.** Not the presence of an `analytics` key — the adapter returns
   `{"analytics": {"status": ..., "body": ...}}` whatever came back, so an `analytics` key
   sits above a 401 exactly as it sits above a 200. Shared rule 1.
4. **Report every figure with its window and its scope attached.** *"Over the last thirty
   days, across the businesses this FunnelForge account owns."* A figure from this module
   without both of those is a number whose period and population are unstated, and both are
   surprising. `funnelCount` takes the scope and not the window.

**Step 4 is the one that carries.** The call is trivial; every failure mode of this module is
in what gets said about the answer.

## 5. WHAT COMES BACK

**The answer may be up to ten minutes old, and there is no way to tell.**

`cacheService.getUserDashboard(userId)` is consulted first; on a hit the cached object is
returned and the route sets `X-Cache: HIT`. On a miss the figures are computed and cached for
**600 seconds** with `X-Cache: MISS`. **The adapter discards response headers** (shared rule
2), and the body carries no timestamp. So:

- Two calls a minute apart can return identical numbers because nothing changed, **or**
  because the second was served from cache. Those are different facts and the response cannot
  distinguish them.
- A number read immediately after an event may not include it.
- **"Current" is the wrong word for anything this module returns.** *"As at some point in the
  last ten minutes"* is the strongest true claim.

**Zero is not "no data".** `conversionRate` is `pageViews > 0 ? ... : 0` — a hard zero when
there were no page views, not a null and not an absence. `totalRevenue` is
`orders._sum.total || 0`, so a zero can mean no completed orders or no orders at all.
**Report a zero as a zero over a stated window and population, never as "no activity".**

**`totalVisitors` counts distinct `visitorId` strings, and one of them is `'unknown'`.**
FunnelForge's own capture path writes `visitorId: 'unknown'` where none is supplied, so every
such event collapses into a single "visitor". The count is distinct identifiers, not distinct
people, and it never was.

**There is no third state.** Unlike `portfolio_health`, there is no `assessed` flag and no
`notAssessedReason`. An account with no businesses gets six zeros, and six zeros look
identical to an account with businesses and no traffic.

## 6. WHAT FAILURE LOOKS LIKE

### From the adapter

| Response | Meaning |
|---|---|
| `503 ADAPTER_NOT_CONFIGURED` | `FUNNELFORGE_TENANT_TOKEN` is unset. **Not a refused credential — do not rotate anything** |
| `401 UNAUTHENTICATED` | The presented token does not match the configured one |
| `404 MODULE_NOT_BOUND` | A spelling problem in the module id, not a missing report |
| `200` | The handler ran. Read `upstream.status` |

**The 503 and the 401 are the pair that must not be collapsed.** 503 means there is nothing to
check a credential against; 401 means one was checked and refused. Reporting the first as the
second sends somebody to rotate a credential that was never the problem — `docs/forge-adapter.md`
trap #9.

**No refusal code is reachable on this module.** No compliance refusal, no template refusal,
and no required argument — so `ARGUMENT_MISSING` cannot fire either.

### From FunnelForge, at `upstream.status`

| Status | Body | Meaning |
|---|---|---|
| `200` | `{"success":true,"data":{...six fields...}}` | Computed or cached. §5 |
| `401` | `FST_JWT_NO_AUTHORIZATION_IN_HEADER` | The brokered token did not reach the route |
| `429` | `RATE_LIMIT_EXCEEDED` | Refused before the route ran. Shared rule 4 |
| `500` | — | The aggregation failed. Nothing was written; nothing to reconcile |

**There is no 404 and there cannot be.** This module takes no identifier that reaches the
handler, so it cannot be asked about something that does not exist. An account that exists
always has an answer, and sometimes that answer is six zeros.

**A 401 here is about the credential, not about permission.** No role check, no scope check
and no grant check runs on this route; what scopes the call is the user read from the token. So
a 401 is *the call was never authenticated*, and it goes to whoever owns the credential — not
to a grant administrator, because there is no permission on this route for anyone to widen.

**A 429 on a read is the shared-bucket case in its purest form.** This module can be called
once a day and still be refused, because six sends and a booking spend the same counter
(shared rule 4c). An agent must not respond by reading less often; that is treating somebody
else's traffic as its own.

**The question this module cannot answer is not a failure signature and it must be reported
like one.** Asked for a period other than the last thirty days, the correct response is that
the module has no date range — not a 200 relabelled. §3.

## 7. RETRY VS ESCALATE

**Retry freely.** It is a pure read. Nothing is written, nothing is sent, nobody is contacted,
and a retry after a timeout costs nothing and duplicates nothing.

**Two caveats, and neither is a reason not to retry:**

**The retry may be answered from cache** (§5), so identical numbers after a failure are not
evidence that the failure was harmless or that the data is unchanged. They are not evidence of
anything.

**The retry spends the shared budget** (shared rule 4c). Retrying a read in a tight loop can
refuse a send that a person is waiting on. On a 429, honour `retryAfter` from the body rather
than retrying immediately.

**Escalate rather than retry in two cases, and they go to different people.**

**A 401, or the adapter's 503**, goes to whoever holds the FunnelForge credential and the
adapter's configuration. It is an operator hand-off. Nothing about the numbers is unresolved,
because nothing was read.

**A question this module structurally cannot answer** goes back to whoever asked it, with the
reason. A request for a specific period, or for one business's numbers, or for a figure "as of
now", cannot be met — there is no date range (§3), no per-business view (§2), and no timestamp
(§5). **Handing that back is the module's only real escalation, and it is a hand-back rather
than a hand-up.** The agent stops short of answering a narrower question with a broader number.

## 8. NEVER

**Never report a figure without its window and its population.** Thirty days ending now, across
the businesses the brokered account owns. Both are surprising and neither is in the response.

**Never honour a date range.** `start_date` and `end_date` are ignored by the handler (§3). An
agent that passes them and then reports the answer as covering them has reported a period that
was never queried.

**Never call the answer current, live, or up to date.** It may be ten minutes old and nothing
says which. §5.

**Never attribute any figure to Burkham specifically.** The scope is a user account (§2).
Unless somebody has established that the account owns only Burkham businesses, "Burkham's
funnel traffic" is a claim this module does not support.

**Never attribute a figure to a client, a funnel, a campaign or a channel.** The answer names
none of them and none can be inferred from six scalars.

**Never report `totalRevenue` as Burkham's revenue.** It is the sum of completed
`Order.total` rows in FunnelForge's marketing tier, for whatever businesses that account owns.
It is not the firm's revenue, not placement volume, and not fee income.

**Never report `conversionRate` as a rate at which people became clients.** It is form
submissions over page views. §6.3 keeps client status in Console; this number has never seen
it.

**Never report a zero as "no activity" or as an absence.** §5. Zero is a computed zero.

**Never report `funnelCount` as a thirty-day figure.** It is not windowed. §3.

**Never present these numbers as verified, reconciled or audited.** They are aggregates over
whatever events were recorded, and what was recorded is whatever fired.

**Never treat a 429 as a signal to read less.** The bucket is shared. Shared rule 4c.

**Never treat a 401 as evidence about the data.** It is a fact about the caller. There is no
permission on this route, so it is also not a fact about a grant.

## 9. WHICH LAWS THIS TOUCHES

**`compliance/consumer-privacy-rights-v1`** — **the entry applies to what this module reads,
not to what it returns.** The aggregation touches `AnalyticsEvent`, `Lead` and `Order` rows
about identifiable people, and reading personal data is a processing activity whatever the
output shape. The six numbers are not subject to an access request; the rows they were
computed from are.

**No fair-treatment entry applies, and that is a decision rather than an omission.**
`compliance/fair-treatment-in-routing-v1` governs inputs to a routing or recommendation
decision about a client. **This module returns no client, so nothing it returns can route
one.** `conversionRate` is the reason to check rather than assume: a conversion statistic
across a population is the shape a disparate-impact analysis uses. It is not one — one
tenant-wide percentage, no protected characteristic, no per-client breakdown, no comparison
group.

**No FCRA entry applies, and §6.3 is why it structurally cannot.** Nothing this module reads
is bureau-derived, and nothing ever will be: the marketing tier holds no credit data by
architecture, and FunnelForge cannot query Console for it. That is what keeps the marketing
tier out of FCRA scope at all.

**No GLBA entry applies.** No Plaid connection and no financial account data is in scope for
this tier.

**`compliance/outbound-contact-boundary-v1` is scoped out.** This module contacts nobody and
triggers no contact. It is the only one of the nine of which that is true — the six sends
send, the booking mails a confirmation, and `capture_contact` can start a welcome sequence.
**This is the one module on this Forge with no send anywhere behind it.**

**`compliance/own-claims-and-pricing-v1` reaches the reporting, not the module.** Nothing here
is client-facing. But a `totalRevenue` or a `conversionRate` repeated in a marketing claim
becomes a statement Burkham makes about its own results, and §8's prohibitions are what keep
the number from acquiring a meaning it does not have.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** `_read_funnel_analytics`, the query it
builds from `start_date` and `end_date`, the `{"analytics": ...}` wrapper, and `HttpUpstream`
returning status and body and discarding headers.

**Read from FunnelForge's source (`apps/api/src/modules/analytics/routes.ts`):** the handler
reading only `user.userId`, the `businesses → funnels → events` chain, the hard-coded
thirty-day window, the six computed fields, the `X-Cache` header, and the
`cacheService.setUserDashboard(..., 600)` ten-minute TTL. From `services/cache-service.ts`: the
TTL and its comment.

**Measured, 9 September 2026:** the rate-limit behaviour on the running stack. The `401
FST_JWT_NO_AUTHORIZATION_IN_HEADER` on this exact route was measured by P-13 and is recorded
verbatim in `docs/plans/funnelforge-binding-RECORD.md`.

**Not measured:** a `200` from this route. It requires a valid FunnelForge user JWT, and there
is no tenant credential to mint one from (shared rule 5). **The field list and the window are
read from the handler, not from a response**, and that limit is stated rather than glossed —
`docs/forge-adapter.md` trap #4 is about exactly this gap, and this module is on the wrong
side of it.

## OPEN

**Nobody knows what the brokered account owns.** §2. Every figure this module returns has that
account's holdings as its population, and the population is unknown. It is answerable by
somebody with FunnelForge access and it has not been asked.

**A cached answer is indistinguishable from a fresh one, because the adapter drops the
header.** Shared rule 2. Surfacing `X-Cache`, or returning a computed-at timestamp, would fix
it; both are changes outside this manual. Until then §5's rule stands.

**The date arguments should probably not exist.** §3. A field that is accepted and ignored is
a field that will eventually be reported as honoured. Whether to remove them from the module's
inputs or to make the route read them is a decision for whoever owns each side, and it has not
been made.

**This module has never been called successfully.** See PROVENANCE. Until it has been, every
statement here about the *answer* is read from a handler rather than from a response.
