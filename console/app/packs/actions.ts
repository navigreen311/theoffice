"use server";

import { revalidatePath } from "next/cache";

import {
  ApiError,
  api,
  type PackTemplateCategory,
  type ValidationResponse,
} from "@/lib/api";

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

/* ------------------------------------------------------------------ new Pack */

export type NewPackState = EditorState & {
  /** Filled by the template and duplicate paths, to seed the textarea. */
  loaded?: string;
  /** The rules a just-saved draft fails, so the operator sees the work remaining. */
  failing?: { rule_id: string; message: string }[];
  rules_checked?: number;
};

/**
 * Fetch a starting document.
 *
 * Both entry paths that are not "paste YAML" end here, because both do the same thing:
 * put text in the textarea. A template is generated from the schema; a duplicate is
 * another venture's live source. Neither writes anything — the operator still has to
 * save, which is what makes the draft theirs.
 */
export async function loadStarterAction(
  _prev: NewPackState | null,
  form: FormData,
): Promise<NewPackState> {
  const mode = String(form.get("mode") ?? "");

  try {
    if (mode === "template") {
      const category = String(form.get("category") ?? "");
      const ventureName = String(form.get("venture_name") ?? "").trim();
      if (!category) return { error: "Choose a category." };

      const query = new URLSearchParams({ category });
      if (ventureName) query.set("venture_name", ventureName);
      const result = await api.get<{ yaml_source: string; note: string }>(
        `/api/packs/template?${query.toString()}`,
      );
      return { loaded: result.yaml_source, ok: result.note };
    }

    if (mode === "duplicate") {
      const from = String(form.get("from_venture") ?? "");
      if (!from) return { error: "Choose a Pack to copy." };

      const result = await api.get<{
        live: { yaml_source: string; pack_version: string } | null;
      }>(`/api/packs/${encodeURIComponent(from)}`);
      if (!result.live) return { error: `${from} has no live Pack to copy.` };

      return {
        loaded: result.live.yaml_source,
        ok:
          `Copied ${from}@${result.live.pack_version}. Change identity.venture_name ` +
          `before saving — venture_id is derived from it, and saving unchanged would ` +
          `overwrite ${from}'s own draft.`,
      };
    }

    return { error: `Unknown starting point: ${mode}` };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}

/**
 * Save a draft.
 *
 * A draft is not a lesser publish — it is a Pack that cannot provision, and it cannot
 * because `packs.live` does not return it rather than because something checks a flag.
 * That is why a failing document is allowed to be saved: the work of authoring a Pack
 * is mostly the work of making it stop failing, and it has to be storable in the
 * meantime or it gets written somewhere this console cannot see.
 */
export async function saveDraftAction(
  _prev: NewPackState | null,
  form: FormData,
): Promise<NewPackState> {
  const source = String(form.get("yaml_source") ?? "");
  const version = String(form.get("pack_version") ?? "").trim() || "0.1.0";
  if (!source.trim()) return { error: "Nothing to save." };

  try {
    const result = await api.post<{
      venture_id: string;
      pack_version: string;
      content_hash: string;
      has_live_pack: boolean;
      validation: {
        failures: { rule_id: string; message: string }[];
        rules_checked: number;
      };
      note: string;
    }>("/api/packs/draft", { yaml_source: source, pack_version: version });

    revalidatePath("/packs");
    const failing = result.validation.failures;
    return {
      ok:
        `Saved ${result.venture_id}@${result.pack_version} as a draft. ` +
        (failing.length
          ? `${failing.length} of ${result.validation.rules_checked} rules failing — it cannot provision until they pass.`
          : `No rule is failing. ${result.note}`),
      source,
      failing,
      rules_checked: result.validation.rules_checked,
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}`, source };
    throw error;
  }
}

/**
 * Promote a draft to live.
 *
 * Says what it disturbed rather than reporting success, because the consequence is
 * invisible from here: a Gate 10 signature binds to the artifacts a specific version
 * generates, and publishing a different version stops those artifacts matching. Nothing
 * revoked the signature — it just no longer covers what is running.
 */
export async function publishDraftAction(
  _prev: EditorState | null,
  form: FormData,
): Promise<EditorState> {
  const venture = String(form.get("venture_id") ?? "");
  if (!venture) return { error: "No venture given." };

  try {
    const result = await api.post<{
      pack_version: string;
      content_hash: string;
      note: string;
    }>(`/api/packs/${encodeURIComponent(venture)}/publish`, {});
    revalidatePath("/packs");
    revalidatePath(`/packs/${venture}`);
    return { ok: `${venture}@${result.pack_version} is live. ${result.note}` };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}

/** The template catalogue. Read on the server so the client bundle carries no list. */
export async function templateCategories(): Promise<PackTemplateCategory[]> {
  const result = await api.get<{ categories: PackTemplateCategory[] }>(
    "/api/packs/templates",
  );
  return result.categories;
}

/* --------------------------------------------------- actions for version history */

/** The stored text of one version, for diffing. Read-only. */
export async function versionSource(
  ventureId: string,
  packVersion: string,
): Promise<string> {
  const result = await api.get<{ yaml_source: string }>(
    `/api/packs/${encodeURIComponent(ventureId)}/versions/${encodeURIComponent(packVersion)}`,
  );
  return result.yaml_source;
}

/**
 * Bring an old version back as the working draft.
 *
 * Deliberately a draft rather than a publish. Restoring is usually an act of
 * recovery — something in the current text is wrong and an older one was right — and
 * that is exactly the moment not to put a document into force in one click. It becomes
 * the draft, where it can be read, diffed and validated before anybody publishes it.
 */
export async function restoreAsDraftAction(
  _prev: NewPackState | null,
  form: FormData,
): Promise<NewPackState> {
  const venture = String(form.get("venture_id") ?? "");
  const version = String(form.get("pack_version") ?? "");
  if (!venture || !version) return { error: "No version given." };

  try {
    const source = await versionSource(venture, version);
    const result = await api.post<{
      pack_version: string;
      validation: { failures: { rule_id: string }[]; rules_checked: number };
    }>("/api/packs/draft", {
      yaml_source: source,
      // Marked, so the history does not grow two rows with the same version string and
      // no way to tell which is the restored copy.
      pack_version: `${version}-restored`,
    });

    revalidatePath(`/packs/${venture}`);
    revalidatePath("/packs");
    const failing = result.validation.failures.length;
    return {
      ok:
        `${version} is now the draft, as ${result.pack_version}. It is not live — ` +
        (failing
          ? `${failing} of ${result.validation.rules_checked} rules are failing against it.`
          : "publish it when you are ready."),
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}
