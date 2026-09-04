# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `scan_communication`
**Endpoint:** `POST /api/comm-compliance/scan`
**Permission:** `COMPLIANCE_WRITE`
**Trust tier:** `propose`
**Idempotency:** `at_most_once`
**Version:** 1.2 — corrected 3 September 2026
**Status:** draft, pending Compliance Review Board

Read foi-shared-rules.md first. Rules 1, 2, 5 and 6 govern most of this.

Declared in Burkham's Pack, operated by the Compliance Reviewer. An agent holds this grant.

## 1. WHAT IT DOES

Scans advisor text for banned claims, inserts required disclosures into it, scores the risk, and files a record.

The insertion is the point, and it is easy to miss. This is not an analyser that returns findings. It returns contentWithDisclosures — a rewritten body, which is what would actually go out.

An agent that reads violations and ignores that field has discarded the only output that changes what a client receives.

It requires COMPLIANCE_WRITE, and that is not a mistake: a scan writes.

## 2. WHAT IT DOES NOT DO

It does not send anything. It returns text and files a record.

It does not inspect a video. video_script is the text a video is generated from, scanned before render. Named video_script rather than video because nothing here has inspected a video.

It does not stop at a threshold. There is no hard stop at 70 — see §6.

It does not review. A scan is automation. humanReviewedAt stays null until a person looks.

## 3. WHAT EACH INPUT MEANS

| Input | Meaning |
|---|---|
| `advisorId` | The advisor whose text this is. A UUID **that must name a real advisor in this tenant** |
| `channel` | Which channel the text is for. One of the six in §5 |
| `content` | The text to scan. 1–100,000 characters |
| tenant | **Not caller-supplied.** Read from the token |

**`advisorId` is validated against the tenant, and that is not a formality.** It was once validated as a UUID and nothing else, so a scan could be filed against an id belonging to nobody — and the QA scores endpoint would then report over it faithfully. It refuses rather than defaulting to the caller: a scan filed against the person who ran it, when they named somebody else, is a different wrong answer rather than a fix.

A non-existent id and another tenant's id get the same answer, deliberately.

**All three fields are required.** There is no partial scan.

## 4. THE CORRECT SEQUENCE

1. **Name the advisor the text is actually for.** `advisorId` must be the person whose communication this is, not the caller. This is the only step where getting it wrong writes a durable wrong record rather than sending bad text — a scan filed against the wrong advisor is reported over faithfully by the QA scores endpoint, and nothing afterwards contradicts it. The module refuses an id that names nobody in the tenant rather than defaulting to the caller; that refusal is a correction, not an obstacle.
2. **Read `contentWithDisclosures` and send that as the body.** Not the text you submitted. This is not an analyser that returns findings — it returns a rewritten body, and that field is the only output that changes what a client receives. An agent that reads `violations`, fixes nothing and sends its original text has run a scan and discarded its result.
3. **Scan before sending, never after.** A scan of text already sent is a record, not a control.
4. **For voice, expect a refusal rather than an appended disclosure.** Voice does not get a disclosure bolted on the end — see §6. The answer is to fix the script and scan again, not to send the text with the refusal noted.
5. **Do not treat the score as a gate.** There is no hard stop at any threshold. A number is not permission, and a low score is not a clearance to send.
6. **Do not treat the scan as a review.** `humanReviewedAt` stays null until a person looks. A scan is automation; it is evidence that a check ran, not evidence that anybody agreed with it.

## 5. SIX CHANNELS, AND TWO ARE NOT CONSENT CHANNELS

SCAN_CHANNELS is CONSENT_CHANNELS plus chat and video_script — a superset by construction, so the overlap cannot drift again. Four lists had grown up around this and none matched.

Extra channel    Why it is scanned and never consented to
chat    A live transcript. Consent is not captured over chat in this system
video_script    Text a video is generated from. A marketing script relates to no client at all

The consent channels are shared with record_consent, which is the module that owns that vocabulary. The superset relationship is the fact worth carrying: everything consentable is scannable, and two scannable things are not consentable.

## 6. WHAT COMES BACK

contentWithDisclosures

The rewritten body. Where a disclosure answers a specific banned claim it is placed immediately after the sentence containing it — not at the end.

A disclosure triggered by a keyword rather than a claim has no position to attach to and is appended. Except on voice — see §7.

riskScore — there is no hard stop

The header once claimed a hard stop at 70. There is none. Seventy is the high/critical boundary in the level mapping and nothing branches on it.

A manual repeating "70 blocks" would name a control that does not exist.

approved — exactly zero

approved is riskScore === 0. Not a judgement and not a threshold. One violation is unapproved.

occurrences — counted, not multiplied

Repeats are counted and do not raise the score. Nine of one claim is one problem to fix. Reporting nine violations from one repeated claim overstates it.

scannedAt is not humanReviewedAt

The field was once named for review and set when the automation ran, so a compliance reader saw reviewed and concluded a person had looked.

humanReviewedAt and reviewedByUserId stay null until somebody actually does. This is the module's unverifiable third state: scanned and reviewed are different facts.

## 7. VOICE REFUSES RATHER THAN APPENDING

On a written message an appended disclosure is imperfect — bottom of the message, the reader may not reach it.

On a spoken script it is a disclosure after the call ended. The script finishes, the advisor stops talking, and the text below the sign-off is read by nobody.

So a voice scan whose disclosure has no anchor refuses — 400, with details.disclosureIds naming which ones have nowhere to go.

The fix is to rewrite the script so the disclosure has somewhere to sit. Not to move the channel.

## 8. WHAT FAILURE LOOKS LIKE

Response    Meaning
400 unknown advisor    advisorId names nobody in this tenant
400 unanchored voice disclosure    With details.disclosureIds
400 invalid body    Content is capped at 100,000 characters

The advisor refusal is not a validation quibble. advisorId was once validated as a UUID and nothing else, so a scan could be filed against an id belonging to nobody — and the QA scores endpoint would then report over it faithfully.

It refuses rather than defaulting to the caller. A scan filed against the person who ran it, when they named somebody else, is a different wrong answer rather than a fix.

A non-existent id and another tenant's id get the same answer, deliberately.

## 9. RETRY VS ESCALATE

Never retry. Escalate.

And the state machine does not save you here. Unlike submit_application, where a second submit is refused, a second scan succeeds: it mints a new scanId, writes a second record with the same content, and emits another ledger event if violations were found. Nothing de-duplicates.

On a timeout, look for the existing scan.

A clean scan is invisible in the ledger

The violation event is written only when violations were found. A clean scan leaves a database row and no ledger event.

That is arguably correct — an event stream of things that happened, and nothing happened. But it means the ledger cannot answer "what was checked." It can only answer "what failed." A regulator asking the first question gets the second, and the difference is every message that passed.

The records exist. Query the records, not the ledger, when the question is coverage.

## 10. NEVER

Never send the original text after a scan. contentWithDisclosures is the output that matters. Sending what you scanned discards the disclosures the scan inserted.

Never re-run a refused voice script on another channel. Passing it as sms to get a clean result defeats the control. Rewrite the script.

Never report scannedAt as review. Nobody looked.

Never report occurrences as separate violations. One claim nine times is one claim.

Never treat riskScore under 70 as approved. approved is zero, and there is no threshold.

Never supply an advisorId other than the advisor whose text this is — and never substitute your own when the named one is refused.

Never read a silent ledger as an unscanned message. §9.

Never retry.

## 11. WHICH LAWS THIS TOUCHES

compliance/own-claims-and-pricing-v1 — the FTC entry, and the source of what counts as a banned claim. The classification rule lives there: a firm-scale factual claim is permitted, a claim that shifts a prospective client's expectation about their own outcome is not, including when it is true.

compliance/not-a-credit-repair-organization-v1 — credit-improvement language is a banned category here and the boundary is defined there.

compliance/estimate-not-offer-v1 — where scanned text carries a lender product number, that entry governs the hedge, the provenance and the not-the-lender statement.

compliance/call-recording-consent-v1 — where the text is a transcript of a recorded call, that entry governs the recording it came from.

These records are excluded from the compliance manifest, deliberately. CommComplianceRecord carries tenantId and advisorId and no business — a scan is attributed to the advisor who ran it, and a marketing script relates to no client. Communication monitoring is a programme, answered by a tenant-level report rather than a per-client index. That report does not exist. See compliance_manifest_assemble §10.

## PROVENANCE

From the code, read 3 September 2026: the six channels and the superset relationship, disclosure placement and the voice refusal, approved as exactly zero, occurrences not multiplying the score, the advisor verification, the conditional ledger emission.

Decided by the founder, 2 September 2026: the advisor is verified rather than defaulted; voice refuses rather than appends; scannedAt is renamed and human review is its own nullable state; repeats are counted and reported; riskLevel is computed and gates nothing, recorded rather than built.

## OPEN

riskLevel is computed and unused. Nothing acts on it. approved is the only gate and it is exactly zero. Recorded so nobody assumes it gates something.

The tenant-level monitoring report does not exist. It is the honest home for the coverage question the manifest excludes and the ledger cannot answer.

A clean scan writes no ledger event. §9. Correct as an event stream, and it leaves the ledger unable to answer what was checked.

## APPENDIX A — §3 WHAT EACH INPUT MEANS ADDED AT 1.1, 3 September 2026

**Why.** This manual's §3 was SIX CHANNELS, AND TWO ARE NOT CONSENT CHANNELS — a
fact about the channel enum, not a statement of what a caller supplies. So the
curriculum's `inputs` field would have been written from the route code rather than
lifted, making this one of three modules where the manual was not the source.

**Nothing here is new.** `advisorId`, `channel` and `content` were read from
`ScanBodySchema` and reviewed before authoring; the advisor-validation paragraph is
lifted from what was §7. Sections renumbered: the old §§3–9 are now §§5–10, and the
internal cross-references moved with them.

## APPENDIX B — §4 THE CORRECT SEQUENCE ADDED AT 1.2, 3 September 2026

**Why.** This manual had no sequence section — §§4–6 were the channel enum, what
comes back, and voice-refuses-rather-than-appending. None is a sequence of agent
steps, so composing one into the curriculum's `correct_sequence` field would have
made this a module whose curriculum was not derived from its manual.

**The order is the argument.** It leads with naming the advisor because that is the
only step where getting it wrong writes a durable wrong record rather than sending
bad text — everything else is recoverable by scanning again.

`contentWithDisclosures` is second rather than later because it is the failure this
module invites. §2 and §5 both say the rewritten body is the point; a sequence that
mentioned it third would have buried the one field an agent most often ignores.

**Nothing here is new.** Every step is lifted from §§2, 3, 5, 6 and 10. Sections
renumbered: the old §§4–10 are now §§5–11.
