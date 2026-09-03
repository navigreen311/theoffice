/**
 * The words this console uses for the values it stores.
 *
 * The console showed database values to people: `awaiting_human`, `auto_execute`,
 * `at_most_once`, `DECLARED_NOT_REQUIRED`. Each is precise and each is unreadable to
 * somebody who does not work on this system, which is most of the people who will ever
 * need to read these screens under pressure.
 *
 * **Translation, not simplification.** Every label here says the same thing the
 * identifier says. Where a shorter label would say less — `at_most_once` really does mean
 * "never retry automatically, a person must decide" — the longer label wins. A sentence
 * that is shorter and less true is a worse sentence, and on these screens it is a
 * dangerous one.
 *
 * One dictionary, because the same value has to read identically everywhere. A page
 * inventing its own wording for `propose` is a page that quietly teaches a different
 * meaning, and consistency here matters more than any individual choice.
 *
 * The identifier is never discarded. Engineers need it, and it is what appears in every
 * log, export and error message — so it stays as secondary monospace text beside the
 * label rather than being replaced by it.
 */

export type Vocabulary = Record<string, string>;

/** Provisioning runs and their gates. */
export const RUN_STATE: Vocabulary = {
  awaiting_human: "Waiting for you",
  aborted: "Abandoned",
  rejected: "Turned down",
  passed: "Passed",
  not_run: "Not run yet",
  never_run: "Never run",
  running: "In progress",
  at_ceiling: "Went as far as possible",
  blocked: "Blocked",
  failed: "Failed",
  fresh: "Verified recently",
  stale: "Out of date",
};

/** How much an agent may do without asking a person. */
export const TRUST_TIER: Vocabulary = {
  auto_execute: "Acts on its own",
  propose: "Asks first",
  suggest: "Advises only",
};

export const CERTIFICATION_STATE: Vocabulary = {
  certified: "Certified",
  never_certified: "Never tested",
  in_training: "Being tested",
  failed: "Failed the test",
  stale_instructions: "Instructions changed since testing",
  stale_forge: "Software updated since testing",
  revoked: "Certification withdrawn",
};

export const REVOCATION_SCOPE: Vocabulary = {
  agent_module: "One permission",
  agent: "One agent, everything",
  venture: "A whole business",
  forge: "A whole piece of software, everyone",
};

export const CREDENTIAL_MODE: Vocabulary = {
  brokered: "The Office holds the key and acts for this agent",
  native: "The agent has its own login",
};

export const MISMATCH: Vocabulary = {
  DECLARED_NOT_REQUIRED: "Set up but never used",
  REQUIRED_NOT_DECLARED: "Used but never declared",
  IN_USE_NOT_REQUIRED: "Being called and shouldn't be",
  REQUIRED_NOT_IN_USE_30D: "Declared but unused for 30 days",
  MATCHED: "Set up, needed, and in use",
};

/**
 * Whether a call is safe to send twice.
 *
 * `at_most_once` keeps its full sentence. "Never retry" alone would drop the half that
 * says what to do instead, and this is the value that decides whether a failed call gets
 * repeated by a machine or looked at by a person.
 */
export const IDEMPOTENCY: Vocabulary = {
  key: "Safe to retry",
  natural: "Safe to repeat",
  at_most_once: "Never retry automatically — a person must decide",
};

export const VERSION_SENSITIVITY: Vocabulary = {
  major: "Only major updates require re-testing",
  "major.minor": "Minor updates require re-testing",
  "major.minor.patch": "Even small patches require re-testing",
};

export const COMPLIANCE_FLAG: Vocabulary = {
  tsr_disclosure_required: "Must identify itself before a sales call",
  recording_consent_required: "Must get consent before recording",
};

export const CONTROL: Vocabulary = {
  audit_chain: "Audit log integrity",
  certification_staleness: "Out-of-date certifications",
  manifest_reconciliation: "Software actually being used",
  restore_drill: "Backup restore test",
};

/**
 * Forge modules.
 *
 * `forge_module_registry.module_name` exists and holds Title Case of the identifier —
 * "Generate Loi" — which is not a human label, it is the identifier with the underscores
 * removed and one word mis-cased. These say what the module does.
 */
export const MODULE: Vocabulary = {
  property_lookup: "Look up a property",
  comp_analysis: "Compare recent sales",
  underwrite_deal: "Underwrite a deal",
  buyer_match: "Match a listing to buyers",
  generate_loi: "Draft a letter of intent",
  place_call: "Place an outbound call",
  transcribe_call: "Transcribe a call",
  run_scenario_pack: "Run a scenario pack",
  gate_result: "Record a gate result",
};

/** Roles keep their identifiers — they are what the authority matrix is written in. */
export const ROLE: Vocabulary = {
  venture_operator: "Runs one business",
  compliance_officer: "Oversees every business",
  ivan: "Accountable for the portfolio",
};

/**
 * Compliance frameworks a Pack declares.
 *
 * Real regulatory shorthand, so the code stays visible - it is what a compliance officer
 * searches for and what appears in every export. What it needs beside it is which rule it
 * names, because `FTC_TSR` tells a newcomer nothing and the obligation behind it is the
 * reason the venture is gated.
 */
export const FRAMEWORK: Vocabulary = {
  FTC_TSR: "FTC Telemarketing Sales Rule",
  TWO_PARTY_CONSENT_RECORDING: "Two-party consent for recording",
  TCPA: "Telephone Consumer Protection Act",
  HIPAA: "Health-information privacy",
  HCQC: "Health-care quality and credentialing",
  TILA: "Truth in Lending Act",
  FCRA: "Fair Credit Reporting Act",
  ECOA: "Equal Credit Opportunity Act",
  UDAAP: "Unfair, deceptive or abusive acts and practices",
  CROA: "Credit Repair Organizations Act",
};

const DICTIONARIES = [
  RUN_STATE,
  TRUST_TIER,
  CERTIFICATION_STATE,
  REVOCATION_SCOPE,
  CREDENTIAL_MODE,
  MISMATCH,
  IDEMPOTENCY,
  VERSION_SENSITIVITY,
  COMPLIANCE_FLAG,
  CONTROL,
  MODULE,
  ROLE,
  FRAMEWORK,
];

/**
 * The label for a value, from a named dictionary or from any of them.
 *
 * An unknown value falls back to a readable form of itself rather than to "Unknown" or to
 * blank: a value this file has not caught up with is still a value somebody needs to
 * read, and `place_call` reads better as "Place call" than as an empty cell.
 */
export function label(value: string | null | undefined, from?: Vocabulary): string {
  if (!value) return "—";
  if (from && from[value]) return from[value];
  for (const dictionary of DICTIONARIES) {
    if (dictionary[value]) return dictionary[value];
  }
  return readable(value);
}

/** `provisioning_gate_passed` → `Provisioning gate passed`. Sentence case, never Title. */
export function readable(value: string): string {
  const words = value.replace(/[_.]+/g, " ").trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Domain terms, defined in one clause each.
 *
 * These are proper nouns for real things and are not replaced — a Pack is a Pack. What a
 * new reader has never seen is what one *is*, so each carries a definition that the page
 * attaches on first use.
 */
export const DOMAIN: Record<string, string> = {
  Village: "The 186 AI workers, organised into 12 departments",
  Forge: "A piece of business software agents operate — CapitalForge, VoiceForge, and six others",
  Pack: "The form describing one business; everything else is generated from it",
  Gate: "One of 17 checkpoints between a Pack and a live business",
  Grant: "Permission for one agent to use one part of one Forge for one business",
  Bridge: "The connection that lets an agent reach a Forge at all",
  "Trust tier": "How much an agent may do without asking a person",
  Shift: "One work period; an agent serves one business per shift",
  "The held-out set": "Surprise test questions The Office is never allowed to see",
  "Blast radius": "How much a revocation would stop",
  Curriculum: "The text an agent is certified against, for one Forge module",
  Manifest: "The list of Forge modules a business declares it needs",
};

/**
 * Gates and rules, with the meaning attached.
 *
 * "V13" alone means nothing to anybody who has not read the rule list. Numbers are never
 * shown without this.
 */
export const GATE_MEANING: Record<string, string> = {
  "0": "Bridge and registration check",
  "1": "Pack schema check",
  "2": "Pack rule check",
  "3": "Identity issuance",
  "3.5": "Manifest reconciliation",
  "4": "Curriculum and certification",
  "4.5": "Capacity and budget check",
  "5": "Grant issuance",
  "6": "Knowledge base check",
  "7": "Shift and coverage plan",
  "8": "Budget activation",
  "9": "Dry run",
  "9.5": "Rollback rehearsal",
  "10": "Human sign-off",
};

export function gateLabel(gate: string): string {
  const meaning = GATE_MEANING[gate];
  return meaning ? `Gate ${gate} — ${meaning}` : `Gate ${gate}`;
}
