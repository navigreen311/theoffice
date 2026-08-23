"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";

export type KnowledgeActionState = { error?: string; ok?: string };

function fail(error: unknown): KnowledgeActionState {
  if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
  throw error;
}

/**
 * Author a Compliance Library entry — Part 6.3's six fields.
 *
 * Checked here as well as in the domain function and in the table constraint. Three
 * layers sounds excessive until you notice they do different jobs: the constraint is the
 * control and cannot be argued with, the domain function names the missing field, and
 * this one does it without a round trip so the author sees it while still looking at
 * the form.
 */
export async function authorEntryAction(
  _prev: KnowledgeActionState | null,
  form: FormData,
): Promise<KnowledgeActionState> {
  const text = (name: string) => String(form.get(name) ?? "").trim();

  const required = [
    ["framework", "Framework"],
    ["jurisdiction", "Jurisdiction"],
    ["applicability_rule", "Applicability rule"],
    ["agent_behavior_implication", "Agent-behaviour implication"],
    ["escalation_trigger", "Escalation trigger"],
    ["citation", "Citation"],
  ] as const;

  const missing = required.filter(([name]) => !text(name)).map(([, label]) => label);
  if (missing.length > 0) {
    return {
      error: `Part 6.3 needs all six fields. Missing: ${missing.join(", ")}. An entry with a citation and no behavioural implication is a reference nobody can act on.`,
    };
  }
  if (!text("entry_ref")) {
    return { error: "entry_ref is what a Pack's library_entry_ref resolves against." };
  }

  try {
    const result = await api.post<{ entry_ref: string; note: string }>(
      "/api/knowledge/compliance",
      {
        entry_ref: text("entry_ref"),
        framework: text("framework"),
        jurisdiction: text("jurisdiction")
          .split(",")
          .map((j) => j.trim())
          .filter(Boolean),
        applicability_rule: text("applicability_rule"),
        agent_behavior_implication: text("agent_behavior_implication"),
        escalation_trigger: text("escalation_trigger"),
        citation: text("citation"),
        runtime_flag: text("runtime_flag") || null,
      },
    );
    revalidatePath("/knowledge");
    return { ok: `${result.entry_ref} written. ${result.note}` };
  } catch (error) {
    return fail(error);
  }
}

/** Author a Business Playbook. Publishing supersedes the live version of that title. */
export async function authorPlaybookAction(
  _prev: KnowledgeActionState | null,
  form: FormData,
): Promise<KnowledgeActionState> {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  const body = text("content");

  if (!text("venture_id") || !text("title") || !text("playbook_version")) {
    return { error: "A playbook needs a venture, a title and a version." };
  }

  let content: Record<string, unknown>;
  try {
    content = JSON.parse(body || "{}");
  } catch {
    return { error: "Content must be JSON. A playbook with no content is a title." };
  }
  if (Object.keys(content).length === 0) {
    return { error: "A playbook with no content is a title." };
  }

  try {
    await api.post("/api/knowledge/playbooks", {
      venture_id: text("venture_id"),
      title: text("title"),
      playbook_version: text("playbook_version"),
      lifecycle_stage: text("lifecycle_stage") || null,
      content,
    });
    revalidatePath("/knowledge");
    return { ok: `Published "${text("title")}" for ${text("venture_id")}.` };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Share a playbook with another venture, or withdraw the share.
 *
 * Part 6.2 is opt-in only, so this form is the opt-in — and it requires a reason,
 * because cross-venture disclosure is exactly the decision somebody will want to review
 * later. Revoking keeps the row, so the record of who saw what survives the withdrawal.
 */
export async function shareAction(
  _prev: KnowledgeActionState | null,
  form: FormData,
): Promise<KnowledgeActionState> {
  const playbookId = String(form.get("playbook_id") ?? "");
  const toVenture = String(form.get("to_venture_id") ?? "").trim();
  const reason = String(form.get("reason") ?? "").trim();
  const revoke = String(form.get("intent") ?? "") === "revoke";

  if (!playbookId || !toVenture) return { error: "Pick a playbook and a venture." };
  if (!revoke && !reason) {
    return {
      error:
        "Sharing across ventures needs a reason. A share nobody can review later is a disclosure nobody agreed to.",
    };
  }

  try {
    await api.post("/api/knowledge/playbooks/share", {
      playbook_id: playbookId,
      to_venture_id: toVenture,
      reason: reason || "withdrawn",
      revoke,
    });
    revalidatePath("/knowledge");
    return {
      ok: revoke
        ? `Withdrawn from ${toVenture}. The share record stays.`
        : `Shared with ${toVenture}.`,
    };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Author a persona.
 *
 * One-way. `office_app` holds no SELECT on `persona_body`, so this console cannot read
 * back what it just wrote — the boundary in Part 6.4 is a column privilege rather than
 * a missing route, and the console runs as that role. The response says so, because a
 * form that silently cannot show its own result reads like a bug.
 */
export async function authorPersonaAction(
  _prev: KnowledgeActionState | null,
  form: FormData,
): Promise<KnowledgeActionState> {
  const text = (name: string) => String(form.get(name) ?? "").trim();

  if (!text("venture_id") || !text("persona_name") || !text("target_persona")) {
    return { error: "A persona needs a venture, a name and the target it stands in for." };
  }

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(text("persona_body") || "{}");
  } catch {
    return { error: "The body must be JSON." };
  }
  if (Object.keys(body).length === 0) {
    return { error: "A persona with an empty body teaches SimForge nothing." };
  }

  try {
    const result = await api.post<{ note: string }>("/api/knowledge/personas", {
      venture_id: text("venture_id"),
      persona_name: text("persona_name"),
      target_persona: text("target_persona"),
      persona_version: text("persona_version") || "1.0.0",
      persona_body: body,
    });
    revalidatePath("/knowledge");
    return { ok: `${text("persona_name")} written. ${result.note}` };
  } catch (error) {
    return fail(error);
  }
}

/** Append one institutional fact. There is no way back out — the table is append-only. */
export async function recordNoteAction(
  _prev: KnowledgeActionState | null,
  form: FormData,
): Promise<KnowledgeActionState> {
  const summary = String(form.get("summary") ?? "").trim();
  const venture = String(form.get("venture_id") ?? "").trim();

  if (!summary) {
    return { error: "A record nobody can read at a glance is an archive, not a memory." };
  }

  try {
    await api.post("/api/knowledge/history", {
      summary,
      venture_id: venture || null,
      detail: {},
    });
    revalidatePath("/knowledge");
    return { ok: "Recorded. Historical records are append-only — this cannot be edited." };
  } catch (error) {
    return fail(error);
  }
}
