# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `regulator_dossier_export`
**Endpoint:** `POST /api/regulator/inquiries/:id/export-dossier`
**Permission:** `COMPLIANCE_READ`
**Trust tier:** `propose`
**Idempotency:** `at_most_once`
**Version:** 1.1 — drafted 2 September 2026, against CapitalForge `2b36895`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Rules 1, 2, 5 and 6 govern most of this.

**This module writes.** Two rows and a ledger event per call. Its sibling `compliance_manifest_assemble` writes nothing and retries freely. Do not carry that habit here. See §6.

## 1. WHAT IT DOES

Exports a dossier for one regulatory inquiry, and records that it did.

It mints an `exportId`, persists a `regulatoryDossierExport` row holding the sections as sent, and emits `regulator.dossier.exported`.

The duplication is deliberate. A regeneration differs from the original the moment any underlying row changes — and for a regulator artefact that is the difference between evidence and a printout. "The dossier we sent on the 14th" has to resolve to a row.

Sections: inquiry details, documents, complaints, consent records, compliance checks, ACH authorisations, and a legal hold summary where a hold is active.

## 2. WHAT IT DOES NOT DO

**It does not contain documents.** References only — `storageKey`, hash, timestamp. Nothing fetches a byte.

**It carries less than the compliance manifest.** It omits product acknowledgments, card applications with their adverse-action notices, fee schedules, suitability checks, and the ledger. All five are in the sibling module.

`excludedRecordTypes` names them. This matters more here than anywhere else in the system — this is the artefact that actually goes to a regulator, and until 2 September a reader could not tell any of those omissions from "this business has none."

## 3. WHAT COMES BACK

### `legalHoldSummary` — read this before reporting anything about preservation

`preservedDocumentIds` and `documentCount` were **every document for the business, as of now** — no filter on the document's own `legalHold` flag, none on the hold's activation date.

So a document whose flag was false, and a document created after the hold was activated, both appeared in a list called *preserved*, under a hold timestamped earlier.

That is a fabricated provenance claim inside a legal-hold record.

It now lists only documents under hold that existed when the hold ran.

For any dossier exported before `a2968d7`: treat `preservedDocumentIds` as a document inventory, not a preservation record — and say which it is when reporting it.

**And a new shape to escalate on, visible for the first time.** `activateLegalHold` resolved the business from `metadata['businessId']` alone while the export read the column. For a backfilled inquiry — the link on the column, not in the metadata blob — the hold set `legalHold: true` on nothing. It preserved no documents at all, and the old export hid that completely by listing every document as preserved.

So: `documentCount: 0` alongside a populated documents section is **a hold that did not take effect.** It is not "there was nothing to preserve." Escalate it; do not report zero preserved documents as a fact about the business.

The documents section still discloses everything. Narrowing the hold list does not narrow what the dossier reveals.

### `excludedRecordTypes`, `contents`, and the integrity counts

Three states, as on the sibling: verified, unverifiable, tampered. The field names differ and so does their position. Here they are top-level — `documentsVerified`, `documentsUnverifiable`, `documentsTampered`. On `compliance_manifest_assemble` they are nested under `summary` and the third is called `timestampsTampered`.

One concept, two vocabularies. Do not carry the sibling's field names across.

**Never read tampered-zero as clean without the unverifiable count.**

`contents` states that this is references rather than bytes.

## 4. THE CORRECT SEQUENCE

The requester is resolved before anything is assembled or written. A bad id costs no queries and no row.

The inquiry must have a business attached. If it does not, nothing is assembled — see the 422 in §5.

## 5. WHAT FAILURE LOOKS LIKE

| Response | Meaning |
|---|---|
| `200` | Exported. A row now exists |
| `422 INQUIRY_HAS_NO_BUSINESS` | The inquiry exists; nothing is attached to it |
| `400 UNKNOWN_REQUESTER` | `generatedBy` would name nobody |
| `404` | No such inquiry in this tenant |
| `500` | Export failed. The row is written before the event, so either no export exists, or one exists with no ledger entry |

The 422 is shared rule 1 in its sharpest form. It is deliberately **not a 404**, because "no such inquiry" and "nothing attached to it" are different facts and must not share a response.

Until 2 September this assembled five empty arrays and returned them as a complete dossier. A dossier of empty sections reads as "this business has no records" when the fact is that no business was attached.

**On a 500: an export may exist.** Look for an `exportId` before doing anything else.

Until `2b36895` the event was published first, so a failed write left `regulator.dossier.exported` in the ledger carrying an `exportId` that resolved to nothing. For any incident before that commit, the ledger event is not evidence the export exists. Check for the row.

## 6. RETRY VS ESCALATE

**Never retry. Escalate.**

Every call mints a new `exportId`, writes a new row, and emits another event. A retry after a timeout produces a second export of the same inquiry, and the audit trail then shows two — on the artefact where "the dossier we sent on the 14th" has to resolve to one row.

On a timeout the export may or may not have completed. The correct next step is to look for an existing `exportId`, not to make another.

The sibling module is the opposite and the difference is not cosmetic. `compliance_manifest_assemble` mints nothing and creates no artefact, so a retry there is harmless and merely adds a true assembly event. An agent holding both grants must keep the two apart.

## 7. NEVER

**Never retry.** §6. This is the module that rule exists for.

**Never present the dossier as containing documents.** It lists them.

**Never read an empty section as "the client has none"** without checking `excludedRecordTypes`. Six record types are omitted by design. Five — product acknowledgments, card applications, fee schedules, suitability checks, the ledger — are carried by the sibling. The sixth, `business_owners`, is excluded from both and for a different reason: it holds encrypted SSNs and has its own permissioned endpoint.

**Never describe `preservedDocumentIds` from a pre-`a2968d7` export as a preservation record.** It was a document inventory wearing that name.

**Never report `documentsTampered: 0` as verified.** Unverifiable is the third state — and the field is `documentsTampered` here, not `timestampsTampered`.

**Never treat a 422 as a refusal about the client.** No business was attached to the inquiry. There is nothing there to refuse.

**Never assemble a second export to "make sure."** Look for the first.

## 8. WHICH LAWS THIS TOUCHES

This module produces an artefact for a regulator. Everything in `foi-shared-rules.md` about basis, absence and provenance applies with the consequence at its highest.

`compliance/consumer-privacy-rights-v1` — the dossier indexes personal data across systems, and it has a counterparty by design.

`compliance/bureau-report-handling-v1` — ACH authorisations and compliance checks carry regulated material.

`compliance/client-interest-standard-v1` — a dossier assembled in response to a complaint is evidence about how a client was treated. What it omits is part of what it says.

**A counterparty by design.** Unlike a compliance manifest, which is internal until somebody decides otherwise, this artefact has an intended recipient — a regulator, or the client who complained. If a packet is ever built and transfer under legal hold is permitted, this is the module where those conditions get exercised first.

## PROVENANCE

**From the code, read 2 September 2026 at `a2968d7`:** the six sections, the persisted export row and the ledger emission, the 422 and its reasoning, the requester check preceding assembly, the corrected legal hold filter.

**Decided by the founder, 2 September 2026:** split from `compliance_manifest_assemble` on blast radius; `at_most_once` with escalation on timeout; the legal-hold filter; `generatedBy` required to match the sibling; declared contents and exclusions.

**Corrected in 1.1, from a fact-check:** the integrity fields are top-level and named differently from the sibling's; six record types are excluded, not five; the write order was reversed at `2b36895` so the row now precedes the event; and a failed legal hold is now visible as `documentCount: 0`.

**Fixed 2 September**, and stated here because dossiers exported before it are still in circulation: `preservedDocumentIds` listed documents not under hold; the ACH read was unscoped; five unreachable guards read as live policy; `generatedBy` was optional.

## OPEN

A packet does not exist, and this is the module where the legal-hold transfer question would first be exercised. One ruling covers both evidence modules. Not started.

Pre-`a2968d7` exports carry the old legal hold claim. They are persisted rows and cannot be corrected retroactively. Anyone reading one needs §3.
