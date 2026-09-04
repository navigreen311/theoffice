# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `compliance_manifest_assemble`
**Endpoint:** `GET /api/documents/export/:businessId`
**Permission:** `COMPLIANCE_READ`
**Version:** 1.1 — drafted 2 September 2026, against CapitalForge `2b36895`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Rules 1, 2 and 5 govern most of this.

**Sibling module:** `regulator_dossier_export`. Same permission, same reader, different blast radius. See §6 — the difference is the most important thing an agent holding both grants needs to know.

## 1. WHAT IT DOES

Assembles a compliance manifest for one business: a business snapshot, eight record collections — consent records, acknowledgments, applications with their adverse-action notices, fee schedules, ACH authorisations, suitability checks, compliance checks, documents — plus attributable ledger events and fourteen summary counts.

Optional `since` and `until` narrow it to a date range.

## 2. WHAT IT DOES NOT DO

**It does not contain documents.** `contents: 'references'` says so in the payload. The manifest carries `storageKey`, `sha256Hash` and `cryptoTimestamp`. Nothing here fetches a byte or builds an archive.

The route sets `Content-Disposition: attachment`, so a browser saves a file that looks like a deliverable. It is an index.

**It does not transfer anything.** A manifest is internal until somebody decides otherwise. Whether a self-contained packet should exist — and who may receive a document under legal hold — is an open ruling, not a missing feature.

**It does not cover everything.** `excludedRecordTypes` names four record types it omits, each with a reason.

## 3. WHAT COMES BACK

Five fields exist so a reader can tell an omission from an emptiness. They are the subject of this manual.

### `filteredFields` — one date range, four clocks

A single `filterSince` once described four different columns: acknowledgments on `signedAt`, ACH authorisations on `authorizedAt`, fee schedules and suitability checks on `createdAt`.

"Records since 1 January" meant four things and said one.

**Never report a date-filtered manifest as "everything since X."** Report what each collection was filtered on.

### `ledgerScopeNote` — attribution, not completeness

Nothing on a ledger row names a business, so events are matched by `aggregateId = businessId` or `payload.businessId = businessId`. An event whose `aggregateId` is a child entity — an application, an authorisation — and whose payload omits the business is not included.

The section is what can be **attributed** to this business. It is not everything that touched it.

### The three integrity counts

| Field | Means |
|---|---|
| `documentsVerified` | Hash and timestamp checked and sound |
| `documentsUnverifiable` | Could not be checked — the evidence to check is absent |
| `timestampsTampered` | Checked and failed |

`timestampsTampered: 0` once meant either every document verified or not one could be checked. It is the field a regulator reads first.

**Never report zero tampered as a clean result without the unverifiable count.**

### `summary` — fourteen counts and one boolean

The fifteenth member is `noGoTriggered`, and it is not a count. It is true when any suitability check on file triggered a hard no-go — a finding about whether this client should have been placed at all, sitting in a block a reader skims for totals.

A manual that says "fourteen counts" gives an agent no reason to look for it. Read it.

### `excludedRecordTypes`

Four types, each with a reason. An excluded type is not an empty one.

### `generatedAt` and `assembledAt`

The same value. Two names, one clock. Not assembly-versus-generation.

## 4. THE CORRECT SEQUENCE

None. One call, one manifest.

The ownership check runs before any record query, so nothing is read for a business that is not the caller's.

## 5. WHAT FAILURE LOOKS LIKE

| Response | Meaning |
|---|---|
| `200` | Assembled |
| `400 InvalidDateRangeError` | Unreadable or inverted range |
| `400 UnknownRequesterError` | The token's user resolves to nobody in the tenant |
| `404` | No such business, or not yours |
| `500` | Assembly failed |

Two conditions share 400. Read the message.

The date refusal is the control working, not a fault to route around: a manifest covering nothing because the range was unparseable reads exactly like a client with no records.

The requester refusal is the same discipline on provenance — `assembledBy` on a document read by counsel cannot name nobody.

## 6. RETRY VS ESCALATE

**Retry freely.** It mints no id and creates no artefact.

But it is not trace-free. Each assembly emits `compliance.manifest.assembled` to the ledger, carrying the requester, the date range and the three integrity counts. A retry adds a second assembly event — which is true, and is what the ledger is for. Do not treat the duplicate as an error.

This is the sentence that separates this module from `regulator_dossier_export`. That one is `at_most_once`: a retry there produces a second export of the same inquiry and the audit trail shows two. An agent holding both grants must not carry this module's retry habit across.

## 7. NEVER

**Never present a manifest as a packet.** It lists documents; it does not contain them. The attachment header does not change that.

**Never report a date-filtered manifest as complete without `filteredFields`.** Four clocks, one label.

**Never report the ledger section as everything that touched the client.** It is what could be attributed.

**Never read `timestampsTampered: 0` alone.** Unverifiable is the third state and it is the one a regulator asks about.

**Never treat an excluded record type as an empty one.** `excludedRecordTypes` names all four and says why.

**Never route around a 400 on the date range.** The refusal exists because the alternative is a manifest that covers nothing and looks complete.

## 8. WHICH LAWS THIS TOUCHES

`compliance/consumer-privacy-rights-v1` — a manifest indexes nine systems of personal data about a person. Assembling one is a read of all of them.

`compliance/bureau-report-handling-v1` — the documents and compliance checks include bureau-derived material. Indexing it here does not widen what may be done with it.

`compliance/application-truthfulness-v1` — applications and their adverse-action notices are carried. What a manifest states about an application must match what was submitted.

**On communication scans.** They are excluded deliberately, not missing. `CommComplianceRecord` carries `tenantId` and `advisorId` and no business — a scan is attributed to the advisor who ran it, and a marketing script relates to no client at all. Communication monitoring is a programme, answered by a tenant-level report, not a per-client index. Recorded as a known absence.

## PROVENANCE

**Corrected in 1.1:** `summary` carries a fifteenth member, `noGoTriggered`, which is a finding rather than a count; and the assembly event now carries `documentsVerified` alongside the other two integrity counts.

**From the code, read 2 September 2026 at `2b36895`:** the eight collections and the summary counts, all five declaration fields, both 400 conditions, the ownership gate preceding the fetches, the ledger emission.

**Decided by the founder, 2 September 2026:** manifests stay internal and a packet is a separate unbuilt module; the ledger and compliance scans ruling; the four clocks named rather than collapsed; `documentsUnverifiable` as a third state.

## OPEN

A packet does not exist. Whether one should — and who may receive a document under legal hold — is one ruling covering this module and `regulator_dossier_export`. Not started.

The tenant-level communication monitoring report does not exist. It is the honest home for the scans this manifest excludes.
