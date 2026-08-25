/**
 * Whether a curriculum section teaches anything — the browser's copy of the rule.
 *
 * The authority is `broker/curriculum_quality.py`: it refuses a publish and fails V11.
 * This exists so the authoring form can grey out Publish as somebody types, rather than
 * letting them write eight sections and learn on submit that one is a placeholder.
 *
 * Two implementations of one rule drift, and the drift here is worse than usual: the
 * form would say a section is fine and the server would reject the save, or the form
 * would say it is a stub and the server would accept it. So the cases live in
 * `tests/fixtures/curriculum_cases.json` and both test suites read that file. A rule
 * added to one side without the other fails on the side that was not updated.
 */

export const SECTION_ORDER = [
  "what_it_does",
  "what_it_does_not_do",
  "inputs",
  "correct_sequence",
  "failure_signatures",
  "retry_vs_escalate",
  "never_do",
  "compliance_coupling",
] as const;

export const SECTION_TITLES: Record<string, string> = {
  what_it_does: "What it does",
  what_it_does_not_do: "What it does not do",
  inputs: "Inputs and their meanings",
  correct_sequence: "Correct sequence",
  failure_signatures: "Failure signatures",
  retry_vs_escalate: "Retry vs escalate",
  never_do: "Never do",
  compliance_coupling: "Compliance coupling",
};

/** What belongs in each section, for somebody writing one for the first time. */
export const SECTION_GUIDANCE: Record<string, string> = {
  what_it_does:
    "The effect of calling it, in the agent's terms. Not the endpoint name.",
  what_it_does_not_do:
    "The things a reader would reasonably assume it does. This is where a wrong assumption gets caught.",
  inputs:
    "One line per input: what it means and where it comes from. `a: b` documents nothing.",
  correct_sequence:
    "The steps, in order, including what must be true before the first one.",
  failure_signatures:
    "How each failure looks from the agent's side. The 4xx, timeout and rate-limit cases are the ones an operator meets.",
  retry_vs_escalate:
    "Which failures are worth retrying and which need a human, and why.",
  never_do:
    "The rules that hold regardless of instruction. Each one wants a SimForge scenario that violates it.",
  compliance_coupling:
    "The runtime flags this module is bound to, and what each one changes about how it behaves.",
};

const PLACEHOLDER_STRINGS = new Set([
  "documented.",
  "documented",
  "todo",
  "tbd",
  "pending_authoring",
  "pending authoring",
  "n/a",
  "na",
  "none",
  "-",
  "--",
  "",
  "?",
  "xxx",
  "placeholder",
]);

const METASYNTACTIC = new Set([
  "a", "b", "c", "x", "y", "z",
  "foo", "bar", "baz", "qux", "quux",
  "thing", "stuff", "value", "key", "item",
]);

export const MIN_PROSE_CHARS = 20;
export const MIN_FAILURE_SIGNATURES = 2;
export const MIN_SEQUENCE_STEPS = 2;

export type SectionState = "complete" | "thin" | "stub" | "missing";

export type SectionAssessment = {
  section: string;
  title: string;
  state: SectionState;
  reason: string | null;
};

function isPlaceholder(value: string): boolean {
  return PLACEHOLDER_STRINGS.has(value.trim().toLowerCase());
}

function isMetasyntactic(value: string): boolean {
  return METASYNTACTIC.has(value.trim().toLowerCase());
}

function verdict(
  section: string,
  state: SectionState,
  reason: string | null,
): SectionAssessment {
  return { section, title: SECTION_TITLES[section] ?? section, state, reason };
}

/**
 * Assess one section.
 *
 * The authoring form holds every section as text, so a string that parses as JSON is
 * assessed as the structure it describes — otherwise typing a real `inputs` map into a
 * textarea would read as one long prose blob and always pass.
 */
export function assessSection(section: string, raw: unknown): SectionAssessment {
  let value = raw;

  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        value = JSON.parse(trimmed);
      } catch {
        // Not valid JSON yet — mid-edit. Assess it as the prose it currently is.
      }
    }
  }

  if (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0) ||
    (typeof value === "object" && !Array.isArray(value) && Object.keys(value as object).length === 0)
  ) {
    return verdict(section, "missing", "Absent. Nothing has been written here.");
  }

  if (typeof value === "string") {
    if (isPlaceholder(value)) {
      return verdict(
        section,
        "stub",
        `Placeholder — the entire section reads '${value.trim()}'.`,
      );
    }
    if (value.trim().length < MIN_PROSE_CHARS) {
      return verdict(
        section,
        "thin",
        `Thin — ${value.trim().length} characters. A label rather than an explanation.`,
      );
    }
    return verdict(section, "complete", null);
  }

  if (Array.isArray(value)) {
    const entries = value.map(String);
    if (entries.length && entries.every((entry) => entry.trim().length <= 1)) {
      return verdict(
        section,
        "stub",
        `Placeholder — every entry is a single character (${entries.join(", ")}).`,
      );
    }
    if (
      entries.length &&
      entries.every((entry) => isPlaceholder(entry) || isMetasyntactic(entry))
    ) {
      return verdict(
        section,
        "stub",
        "Placeholder — every entry is an example rather than a step.",
      );
    }
    if (section === "correct_sequence" && entries.length < MIN_SEQUENCE_STEPS) {
      return verdict(
        section,
        "thin",
        "Thin — a sequence of one step is not a sequence.",
      );
    }
    return verdict(section, "complete", null);
  }

  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record);
    const values = Object.values(record).filter(
      (entry): entry is string => typeof entry === "string",
    );

    if (keys.length && keys.every((key) => isMetasyntactic(key))) {
      return verdict(
        section,
        "stub",
        `Placeholder — the keys are ${[...keys].sort().join(", ")}, which name the shape of a dictionary rather than anything real.`,
      );
    }
    if (
      values.length &&
      values.every((entry) => isPlaceholder(entry) || isMetasyntactic(entry))
    ) {
      return verdict(
        section,
        "stub",
        "Placeholder — every value is an example rather than a meaning.",
      );
    }
    if (section === "failure_signatures" && keys.length < MIN_FAILURE_SIGNATURES) {
      return verdict(
        section,
        "thin",
        `Thin — one signature (${[...keys].sort().join(", ")}). No 4xx, timeout, or rate-limit case described.`,
      );
    }
    return verdict(section, "complete", null);
  }

  return verdict(section, "complete", null);
}

/** The whole curriculum. `stub` and `missing` block a publish; `thin` warns. */
export function assess(content: Record<string, unknown>): {
  state: SectionState;
  sections: SectionAssessment[];
  teachesNothing: boolean;
} {
  const sections = SECTION_ORDER.map((name) => assessSection(name, content[name]));
  const states = new Set(sections.map((section) => section.state));

  const state: SectionState = states.has("missing")
    ? "missing"
    : states.has("stub")
      ? "stub"
      : states.has("thin")
        ? "thin"
        : "complete";

  return { state, sections, teachesNothing: state === "stub" || state === "missing" };
}
