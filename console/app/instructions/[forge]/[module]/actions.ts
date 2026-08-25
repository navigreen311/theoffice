"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";
import { assess, SECTION_ORDER } from "@/lib/curriculum";

export type AuthoringState = { error?: string; ok?: string };

/**
 * Author a new version of a curriculum.
 *
 * The form holds every section as text, so a section whose real shape is a list or a
 * map is parsed here before it is sent. A section that does not parse is stored as the
 * prose it is - `never_do` written as three sentences is still three rules, and refusing
 * to save it because it is not a JSON array would push authoring somewhere this console
 * cannot see.
 *
 * **A stub cannot be published.** Publishing a stub is what produced the current state:
 * nine modules badged `authored`, none of which describes what it documents, and agents
 * certified against their hashes. The server refuses it too - this check is the courtesy,
 * `broker.curriculum_quality` in V11 and the author path is the rule.
 */
export async function authorAction(
  _prev: AuthoringState | null,
  form: FormData,
): Promise<AuthoringState> {
  const forgeId = String(form.get("forge_id") ?? "");
  const moduleId = String(form.get("module_id") ?? "");
  const version = String(form.get("instruction_version") ?? "").trim();
  const forgeApiVersion = String(form.get("forge_api_version") ?? "");

  if (!version) {
    return { error: "A version is required. Two curricula cannot share one." };
  }

  const content: Record<string, unknown> = {};
  for (const section of SECTION_ORDER) {
    const raw = String(form.get(section) ?? "").trim();
    if (!raw) {
      content[section] = "";
      continue;
    }
    if (raw.startsWith("{") || raw.startsWith("[")) {
      try {
        content[section] = JSON.parse(raw);
        continue;
      } catch {
        // Prose that happens to start with a brace, or JSON mid-edit. Either way the
        // text is what the author wrote, and the assessment below judges it as text.
      }
    }
    content[section] = raw;
  }

  const quality = assess(content);
  if (quality.teachesNothing) {
    const bad = quality.sections
      .filter((section) => section.state === "stub" || section.state === "missing")
      .map((section) => `${section.title}: ${section.reason}`);
    return {
      error:
        `Not saved. ${bad.length} section${bad.length === 1 ? "" : "s"} teach nothing — ` +
        `${bad.join(" · ")}`,
    };
  }

  try {
    const result = await api.post<{
      content_hash: string;
      certifications_invalidated?: number;
    }>("/api/instructions", {
      forge_id: forgeId,
      module_id: moduleId,
      instruction_version: version,
      forge_api_version: forgeApiVersion,
      content,
    });

    revalidatePath(`/instructions/${forgeId}/${moduleId}`);
    revalidatePath("/instructions");

    const invalidated = result.certifications_invalidated ?? 0;
    return {
      ok:
        `Published ${version} — ${result.content_hash.slice(0, 12)}…. ` +
        (invalidated
          ? `${invalidated} certification(s) are now stale_instructions. Those agents ` +
            "stop being assignable on their very next call."
          : "No certification was bound to the previous text."),
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}
