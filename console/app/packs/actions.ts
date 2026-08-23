"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, type ValidationResponse } from "@/lib/api";

export type EditorState = {
  error?: string;
  ok?: string;
  report?: ValidationResponse;
  /** Echoed back so the textarea keeps what the operator typed after a round trip. */
  source?: string;
};

/**
 * Validate a draft. **Writes nothing.**
 *
 * The point of a separate act is that finding a FAIL after publishing costs a run:
 * Gate 2 refuses, but only after Gates 0 and 1 have already reported healthy, and the
 * operator has to work backwards from a blocked run to a document they could have
 * checked in a second.
 */
export async function validateAction(
  _prev: EditorState | null,
  form: FormData,
): Promise<EditorState> {
  const source = String(form.get("yaml_source") ?? "");
  if (!source.trim()) return { error: "Nothing to validate." };

  try {
    const report = await api.post<ValidationResponse>("/api/packs/validate", {
      yaml_source: source,
    });
    return { report, source };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}`, source };
    throw error;
  }
}

/**
 * Publish a version.
 *
 * Deliberately does not start a run, and deliberately does not require a clean report.
 * Gate 2 is where a failing Pack is refused, and it refuses in the run — where refusing
 * means something. An editor that would not let you save a draft with a known failing
 * rule pushes people to edit the YAML somewhere this console cannot see.
 *
 * What it does do is say what publishing disturbed, because the consequence is not
 * visible from the editor: any Gate 10 signature made against the old artifacts is void
 * against the new ones, and nobody revoked it.
 */
export async function publishAction(
  _prev: EditorState | null,
  form: FormData,
): Promise<EditorState> {
  const source = String(form.get("yaml_source") ?? "");
  const version = String(form.get("pack_version") ?? "").trim();

  if (!version) return { error: "A version is required. Two Packs cannot share one.", source };
  if (!source.trim()) return { error: "Nothing to publish.", source };

  try {
    const result = await api.post<{
      venture_id: string;
      pack_version: string;
      content_hash: string;
      note: string;
    }>("/api/packs", { yaml_source: source, pack_version: version });

    revalidatePath("/packs");
    revalidatePath(`/packs/${result.venture_id}`);
    return {
      ok: `Published ${result.venture_id}@${result.pack_version} — ${result.content_hash.slice(0, 16)}…. ${result.note}`,
      source,
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}`, source };
    throw error;
  }
}
