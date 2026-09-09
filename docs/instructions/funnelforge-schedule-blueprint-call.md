# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `schedule_blueprint_call`
**Endpoint:** `POST /api/scheduling/public/{businessId}/{slug}/book`
**Version:** 1.0 — drafted 9 September 2026, against `adapters/funnelforge/` at `ac6475c` and
the running FunnelForge stack
**Status:** draft, pending Compliance Review Board

Read `funnelforge-approved-send-rules.md` first. Rules 1, 2, 4, 5, 8 and 9 govern this module
even though it sends no template — it is `at_most_once`, it shares the rate-limit bucket, its
success flag is a constant, and its retry rule is the send rule for the same reason.

**This module is not a send and it causes a send.** Booking an appointment makes FunnelForge
email the client, with copy nobody at Burkham approved, through a path no module gates. That
is §2 and it is the most important thing in this manual.

## 1. WHAT IT DOES

Books one appointment against a published, active appointment type, on behalf of a named
person.

One call, one row. `prisma.appointment.create` writes a `SCHEDULED` appointment carrying the
client's name, email, optional phone, the date, the start time, an end time the route derives
from the type's duration, and the agent's notes.

**It is a public booking route.** The same route a client uses from a booking page. There is
no privileged path here — the module reaches the identical handler.

**One refusal runs inside the handler**, before anything leaves: `compliance_state` must be
exactly the string `pass`. It is worker-autonomous in a Pass state, so the §3.3 refusal
applies even though there is no template. **The template refusal deliberately does not run** —
there is no template, and writing one against a fabricated id would be a control that tests
nothing.

## 2. WHAT IT DOES NOT DO

### It does not avoid sending an email. It sends one, and nothing gates it.

**On every successful booking, `POST /api/scheduling/public/:businessId/:slug/book` calls
`sendAppointmentConfirmationEmail` and mails the client.** The address it uses is the
`client_email` the agent supplied. The copy is FunnelForge's own
`templates.appointmentConfirmation` — not on the approved list in
`adapters/funnelforge/templates.py`, not reviewed under §4.5, and not reachable by any
refusal in `adapters/funnelforge/gate.py`.

**This is the second hole of this shape in the same nine modules.** The first is
`capture_contact` auto-enrolling a new lead in the WELCOME sequence, recorded in
`docs/plans/funnelforge-binding-RECORD.md`. **This one is worse in one specific way: that one
is conditional on a WELCOME sequence being configured, and this one is unconditional.**
`clientEmail` is required by the route's schema, the send is guarded only by `if (clientEmail)`,
and so it fires on every booking that succeeds.

Module-gating stops an agent *naming* a send. It does not stop a non-send module *triggering*
one. **The approved-template refusal never runs on this mail.**

**And today it silently does not arrive.** Same `emailSender`, same absent provider (shared
rule 3), so `sendAppointmentConfirmationEmail` returns `success: false`. The route logs
`emailSent: false` and returns `200` regardless. **The booking succeeds, the confirmation does
not go out, and nothing in the response says so.** The agent cannot tell, because the route
does not tell it.

So the honest statement about the confirmation is: **an agent does not know whether the client
was emailed, and cannot find out from this module.** It must not say the client was confirmed
by email, and it must not say they were not.

**Interaction with `send_scheduling_confirmation`.** That module sends the approved Blueprint
scheduling confirmation — *"Your Blueprint call is confirmed."* Booking already triggers
FunnelForge's own confirmation. **If a provider is ever configured, a client who is booked and
then sent the approved confirmation receives two confirmation emails for one appointment, one
of which is copy no founder reviewed.** Recorded here rather than resolved: which of the two
should exist is a §4.5 question.

### The rest

**It does not check availability.** The handler reads the appointment type, checks
`maxBookingsPerDay` if the type sets one, and creates. It never consults
`ScheduleAvailability`, never looks at `bufferBefore` or `bufferAfter`, and never checks
whether another appointment already occupies the slot. **A booking at 03:00 on a Sunday
succeeds.** So does a second booking at exactly the same time as an existing one.

**`maxBookingsPerDay` is nullable, and a null means no cap.** Where it is set, the count is
over appointments for that type on that date whose status is not `CANCELLED`. Where it is not,
there is no limit of any kind.

**It does not de-duplicate.** No unique constraint on the appointment type, the date, the
start time or the client's email; the model indexes those and constrains none of them. A
second identical call creates a second appointment. Shared rule 8, and it is why this module is
`at_most_once`.

**It does not take payment.** `AppointmentType.price` exists and this route ignores it.
Booking is not purchase, and the Funding Readiness Score Blueprint is a paid diagnostic
(`docs/reference/burkham-wickmont-marketing-plan-intake.md` Part 2.1, step 4). **A booked call
is not a paid engagement**, and nothing here says otherwise.

**It does not attach a meeting link.** `Appointment.meetingUrl` is left null and the route
supplies no `calendarUrl` to the confirmation. If the type's location is `VIDEO`, the
confirmation — if it were ever delivered — says *"Video Call"* and contains no link.

**It does not tell you whether an appointment exists.** `booked: true` is a constant. Shared
rule 1. Read `upstream.status`.

**It does not record who booked.** The appointment carries the client's name and email and
nothing about the agent. Shared rule 5: The Office's ledger is the only per-agent record.

## 3. WHAT EACH INPUT MEANS

| Field | Meaning |
|---|---|
| `business_id` | **Required.** Path segment. The Burkham business that owns the appointment type |
| `appointment_slug` | **Required.** Path segment. Unique with `business_id`; must be `isActive` |
| `client_name` | **Required.** Stored verbatim. The confirmation's greeting uses its first word |
| `client_email` | **Required.** Stored, **and mailed** — see §2 |
| `date` | **Required.** Parsed by `new Date(...)` into a `@db.Date` column |
| `time` | **Required.** Stored **verbatim as a string.** `HH:mm` |
| `compliance_state` | **Required, and must be exactly `pass`** |
| `client_phone` | Optional. Stored |
| `notes` | Optional. Free text, stored on the appointment, readable by whoever opens it |

**`time` has no timezone, and neither does anything around it.** `startTime` and the derived
`endTime` are `String // HH:mm format` in the schema. The request carries no offset, the
response carries none, and the appointment row carries none. **Nothing anywhere states which
zone `"10:00"` means.** An agent that tells a client their call is at ten o'clock has stated a
time whose zone was never established, to a person who may not be in the same one as whoever
reads the calendar.

**`date` is parsed, and a bare `YYYY-MM-DD` is parsed as UTC.** With a date-only column that
is usually harmless and it is not nothing: it is another place a zone is assumed rather than
stated.

**`notes` is the only free text an agent writes into FunnelForge on this surface.** It is not
sent to the client by this route, and it is stored where a person will read it. Write what a
colleague needs; do not write a summary of the client's financial position, which §6.3 keeps
out of FunnelForge entirely.

**Any of the six required fields absent or empty is refused before any call**, as
`422 ARGUMENT_MISSING` naming every missing field at once.

## 4. THE CORRECT SEQUENCE

1. **Establish that a human decided this call should be booked, for this person, at this
   time.** The module does not observe an agreement and cannot infer one.
2. **Establish the timezone with the client, outside this module, and record it where a person
   will see it.** §3. Nothing in FunnelForge will carry it.
3. **Obtain the categorical compliance state.** Do not compose it.
4. **Call once.**
5. **Read `upstream.status`.** Not `booked`. Shared rule 1.
6. **On `200`, read `upstream.body.data.id`** — that is the appointment id, and it is the only
   handle anyone will ever have on this row. If the caller does not keep it, nothing else
   will: the module cannot look an appointment up, and there is no read module on this Forge
   that can.
7. **Report the confirmation email honestly: unknown.** §2. Do not report that the client was
   emailed and do not report that they were not.
8. **Do not call again.** Shared rule 9; the 429 exception is in §6.

**Step 6 is the one that is easy to skip and impossible to undo.** These nine modules include
no way to read, list, cancel or reschedule an appointment. A booking whose id was not kept is
a row that exists, that a client is relying on, and that no agent can reach again.

## 5. WHAT FAILURE LOOKS LIKE

### From the adapter

Identical to `funnelforge-send-intake-acknowledgment.md` §5 — `503
ADAPTER_NOT_CONFIGURED`, `401 UNAUTHENTICATED`, `404 MODULE_NOT_BOUND`, `422` with a code,
`200` meaning only that the handler ran. The refusal codes reachable here are
`ARGUMENT_MISSING`, `COMPLIANCE_STATE_ABSENT` and `COMPLIANCE_STATE_NOT_PASS`. **The two
template codes cannot fire on this module** — there is no template.

### From FunnelForge, at `upstream.status`

| Status | Body | Meaning |
|---|---|---|
| `200` | `{"success":true,"data":{"id":...,"message":"Appointment booked successfully",...}}` | The row exists. Keep the `id` |
| `400` | `{"success":false,"error":{"message":"No more slots available for this date"}}` | `maxBookingsPerDay` is set and reached |
| `404` | `{"success":false,"error":{"message":"Booking type not found or inactive"}}` | **A domain 404** |
| `429` | `RATE_LIMIT_EXCEEDED` | Refused before the route ran. Nothing was booked. Shared rule 4 |
| `500` | `{"success":false,"error":{"message":"Failed to book appointment"}}` | The catch-all. **State unknown** |

**The 404 is a domain 404 and its shape is how you know.** P-13 measured it: the handler ran,
looked for an appointment type matching `(businessId, slug, isActive: true)`, and did not find
one. Compare a routing 404, which answers `{"message":"Route POST:... not found"}` — a
different body from a different layer. **Reading the body is what separates them, and only the
body does.**

It means one of three things and does not say which: no such business, no such slug, or **the
type exists and `isActive` is false**. The third is the likely one in practice and it is an
operational state somebody changed, not a mistake in the call. Report it as *no active
appointment type by that name for that business*, which is exactly what was checked.

**The 400 is not a validation failure.** *"No more slots available for this date"* means the
day is full under a cap the appointment type carries. It is a real answer about capacity, and
the fix is a different date, not a different request.

**The 500 is the one to escalate on, and it is genuinely ambiguous.** The handler wraps
everything — the type lookup, the count, the create, and the confirmation email — in one
`try`. A 500 can mean the appointment was not created, or that it was created and something
after it threw. **`booked: true` will still be sitting beside it.** Shared rule 1 exists for
this response.

**There is no per-field validation message.** The route's schema requires `clientName`,
`clientEmail`, `date` and `time`; a bad `clientEmail` format is rejected by the schema layer
before the handler. The adapter's own `_require` catches absence earlier and more usefully.

## 6. RETRY VS ESCALATE

**On a timeout or a 500: stop and escalate. Do not retry. Do not check first.**

**The asymmetry is the same as a send's and the reason is different.** A duplicate email is a
message; a duplicate appointment is two rows in a calendar for one conversation, and nothing
in this module can cancel either one. Whoever opens the calendar sees two bookings for the
same client at the same time and cannot tell which is real — and the client, who received two
confirmations if a provider is ever configured, cannot either.

**Check-then-retry is not available.** There is no module on this Forge that reads
appointments. An agent proposing to check whether the booking landed is proposing a capability
that does not exist.

**A 429 is a wait, not a retry.** The rate-limit hook refuses before the route runs, so
nothing was written. Honour `retryAfter` from the body; shared rule 4c first.

**A 404 is not retried at all.** It is an answer. The appointment type is not active, and
calling again will produce the same answer until a person changes something. Escalate to
whoever owns the booking page.

**A 400 is not retried at all either.** The day is full. A different date is a new decision by
a human, not a retry.

**Escalate to two different people, and the response says which.** A `404` or a `400` goes to
whoever administers the appointment types and the calendar. A `500` or a timeout goes to
whoever can look at the appointment table, because the question — *does this row exist* — is
one no agent can answer and one that must be answered before the client is told anything.

## 7. NEVER

**Never report a booking from `booked: true`.** It is a constant. Shared rule 1.

**Never retry a booking.** No idempotency key, no de-duplication, no unique constraint, and no
way to cancel what a retry creates.

**Never say the client has been sent a confirmation.** §2. The route sends one, it fails
silently today, and the response does not report either outcome. *"The appointment is booked;
whether FunnelForge's confirmation email reached them is not visible from here"* is the true
statement.

**Never state the appointment time without stating the timezone it was agreed in**, and never
assume one. §3. Nothing in the request, the response or the stored row carries a zone.

**Never present a booked call as a paid engagement, a commitment, or a place in the Blueprint
process.** It is an appointment row. The Blueprint is a paid diagnostic and this route takes
no payment.

**Never book without an appointment id kept.** §4 step 6. There is no read, no list and no
cancel on this Forge.

**Never book into a slot because the module accepted it.** The route checks no availability,
no buffers and no collisions. Acceptance is not evidence that anyone is free.

**Never treat a 404 as a bad request to be reworded.** It is a domain answer about an inactive
or absent appointment type, and trying variant slugs is guessing at somebody else's
configuration.

**Never put client financial detail in `notes`.** §6.3 keeps credit data, statements and
anything FCRA-regulated out of FunnelForge architecturally. `notes` is a free-text column and
the architecture cannot stop an agent typing into it.

**Never book on behalf of somebody who did not agree to the time.** The route will accept it,
the client will receive nothing (today), and the first anyone learns of it is a missed call.

## 8. WHICH LAWS THIS TOUCHES

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR) — *"Any Burkham-initiated contact with
an individual, any channel."* **This module is not obviously outbound contact and it produces
some**, via §2's confirmation email. The entry applies to the mail the booking triggers, and
the mail is the one thing here nobody at Burkham reviewed. That is the coupling worth naming:
the compliance surface reaches the act the module list does not.

**`compliance/consumer-privacy-rights-v1`** (CCPA and the comprehensive-privacy states) — the
appointment row holds a named person's name, email, optional phone and free-text notes. It is
personal data, subject to access and deletion rights, and **this module set has no way to
read it back or delete it.** A privacy request touching a booking made here is answered by
somebody with database access, not by an agent.

**`compliance/facilitator-not-broker-v1`** — *"Every engagement, in every state, from intake
through placement."* Booking a Blueprint call is the first scheduled contact in the engagement,
and how it is described to the client is where a facilitator can start sounding like a broker.
The module writes `notes` and nothing else a client reads; the description lives in whatever
the agent says around the booking, and §7 governs that.

**`compliance/estimate-not-offer-v1`** (STATE_COMMERCIAL_FINANCING_DISCLOSURE, NY UT VA GA CT
FL) — **scoped out, and worth scoping out explicitly.** A Blueprint call is a diagnostic
conversation, not a commercial financing offer, and nothing this module writes or sends states
a rate, an amount or a term. The entry governs what may be presented as an offer later; it
does not reach a calendar row. Named here because "scheduling the capital conversation" is
where somebody would reasonably look for it.

**No FCRA entry and no GLBA entry apply.** §6.3 caps FunnelForge at anonymous browsing data
and named-contact marketing PII. A name, an email, a phone number and a date are within that
cap; nothing bureau-derived or account-derived can reach this module.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** `_schedule_blueprint_call`, its
`refuse_unless_pass` call and the deliberate absence of the template refusal, `_require` over
six fields, the request body, and the constant `booked: True`.

**Read from FunnelForge's source (`apps/api/src/modules/scheduling/routes.ts`):** the
appointment-type lookup and its `isActive` condition, the `maxBookingsPerDay` count and its
`CANCELLED` exclusion, the absence of any availability, buffer or collision check,
`calculateEndTime`, the unconditional `sendAppointmentConfirmationEmail` and its
log-and-continue handling, and the single wrapping `try`. From the Prisma schema: `date
DateTime @db.Date`, `startTime String // HH:mm format`, `maxBookingsPerDay Int?`, the four
indexes and the absence of any unique constraint over the booking fields.

**Measured by P-13, 9 September 2026:** the domain 404 body, verbatim, against the running
container.

**Measured by P-16, 9 September 2026:** the rate-limit behaviour and the absent email
provider. Transcripts in the shared rules.

## OPEN

**Two confirmations for one appointment.** §2. If a provider is ever configured and an agent
books and then calls `send_scheduling_confirmation`, the client receives FunnelForge's
confirmation and Burkham's approved one. Which should exist is a §4.5 decision and has not
been made. Today the question is hidden by the fact that neither arrives.

**The confirmation email's copy has never been reviewed by Burkham.** It is FunnelForge's
`templates.appointmentConfirmation`, and it goes out over Burkham's engagement in Burkham's
name. Nobody has read it against `compliance/own-claims-and-pricing-v1`. That review is not
P-16's and it has not happened.

**No timezone exists anywhere on this path.** §3. Whether the fix is a field, a convention or
a business-level setting is a FunnelForge question; that there is no answer today is a fact
about the schema.

**There is no read, list, cancel or reschedule module on this Forge.** A booking is
write-only from The Office's side. Whether an autonomous booking surface should exist without
one is a question the nine-module surface raises and does not answer.
