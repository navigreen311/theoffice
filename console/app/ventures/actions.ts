"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api, type ValidationResponse } from "@/lib/api";

export type VentureState = {
  error?: string;
  ok?: string;
  slug?: string;
  report?: ValidationResponse;
};

function fail(error: unknown): VentureState {
  if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
  throw error;
}

/**
 * Create a venture in draft.
 *
 * Draft means no Pack, and therefore no manifest, no runtime config and nothing to
 * grant against — the inability to receive grants is structural rather than a flag
 * somebody remembers to check.
 */
export async function createVentureAction(
  _prev: VentureState | null,
  form: FormData,
): Promise<VentureState> {
  const text = (name: string) => String(form.get(name) ?? "").trim();

  if (!text("display_name")) return { error: "A venture needs a name." };
  if (!text("category")) return { error: "A venture needs a category." };

  try {
    const result = await api.post<{ slug: string; note: string }>("/api/ventures", {
      display_name: text("display_name"),
      slug: text("slug") || null,
      category: text("category"),
      environment: text("environment") || "sandbox",
    });
    revalidatePath("/ventures");
    return { ok: `${text("display_name")} created. ${result.note}`, slug: result.slug };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Validate a pasted Pack before anything is created.
 *
 * The point of the "start from a Pack" path: a Pack that fails Gate 2 wastes a
 * provisioning run, and finding out then means working backwards from a blocked run to
 * a document that could have been checked in a second. Writes nothing.
 */
export async function validatePackAction(
  _prev: VentureState | null,
  form: FormData,
): Promise<VentureState> {
  const source = String(form.get("yaml_source") ?? "");
  if (!source.trim()) return { error: "Paste a Pack to validate." };

  try {
    const report = await api.post<ValidationResponse>("/api/packs/validate", {
      yaml_source: source,
    });
    return { report };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Publish a pasted Pack. The venture comes from the document, never from the form.
 *
 * A caller who could name the venture could publish one venture's Pack under another
 * venture's id, and every gate downstream would provision the wrong business against a
 * right-looking name.
 */
export async function publishPackAction(
  _prev: VentureState | null,
  form: FormData,
): Promise<VentureState> {
  const source = String(form.get("yaml_source") ?? "");
  const version = String(form.get("pack_version") ?? "").trim() || "1.0.0";
  if (!source.trim()) return { error: "Paste a Pack to publish." };

  try {
    const result = await api.post<{
      venture_id: string;
      pack_version: string;
      note: string;
    }>("/api/packs", { yaml_source: source, pack_version: version });
    revalidatePath("/ventures");
    return {
      ok: `${result.venture_id}@${result.pack_version} published. ${result.note}`,
      slug: result.venture_id,
    };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Archive a venture, or bring one back.
 *
 * Archiving revokes nothing. A venture's grants and its ledger outlive the decision to
 * stop operating it, and collapsing the two would make archiving a quiet way to pull
 * authority with no revocation record.
 */
export async function setLifecycleAction(
  _prev: VentureState | null,
  form: FormData,
): Promise<VentureState> {
  const slug = String(form.get("slug") ?? "");
  const state = String(form.get("state") ?? "");
  const reason = String(form.get("reason") ?? "").trim();

  if (!reason) {
    return { error: "A reason is required. Retiring a venture gets reviewed later." };
  }

  try {
    await api.post(`/api/ventures/${slug}/lifecycle`, { state, reason });
    revalidatePath("/ventures");
    return {
      ok:
        state === "archived"
          ? "Archived. Grants and ledger are untouched — archiving is not revoking."
          : `Lifecycle set to ${state}.`,
    };
  } catch (error) {
    return fail(error);
  }
}
