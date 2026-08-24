"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";

export type ControlState = { error?: string; ok?: string; detail?: string };

/**
 * Run the verification sweeps.
 *
 * A page that reports four never-run controls and offers no way to run them is a page
 * that has described a problem and left the reader holding it. This is the button that
 * closes that loop.
 *
 * The result names what actually ran. A sweep that could not acquire its lock ran
 * nothing, and reporting that as success would be the same category of lie the whole
 * page exists to avoid.
 */
export async function runControlsAction(
  _prev: ControlState | null,
  form: FormData,
): Promise<ControlState> {
  const control = String(form.get("control") ?? "").trim() || null;

  try {
    const result = await api.post<{
      ran: { control: string; status: string; passed: boolean; denominator: number }[];
      skipped: string[];
      note: string;
    }>("/api/controls/run", { control });

    revalidatePath("/");

    if (result.ran.length === 0) {
      return {
        error:
          "Nothing ran — every control was already running elsewhere. That is not the same as running and finding nothing.",
      };
    }

    const summary = result.ran
      .map(
        (r) =>
          `${r.control}: ${r.status} over ${r.denominator} item(s)`,
      )
      .join(" · ");

    const failed = result.ran.filter((r) => !r.passed);
    return {
      ok: `Ran ${result.ran.length} control(s). ${summary}`,
      detail:
        failed.length > 0
          ? `${failed.length} did not pass. A failing control is a finding to investigate, not a reason to stop running it.`
          : result.skipped.length > 0
            ? `${result.skipped.join(", ")} held no lock and did not run.`
            : undefined,
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}

/**
 * Produce a regulator export.
 *
 * Returned as a document rather than a file download because the thing that matters is
 * that it is read: it states its own control freshness at the top, and it lists what it
 * did not include. A recipient who skips both has been handed a complete-looking record
 * of an unchecked system.
 */
export async function exportRecordAction(
  _prev: (ControlState & { document?: string; hash?: string }) | null,
  form: FormData,
): Promise<ControlState & { document?: string; hash?: string }> {
  const text = (name: string) => String(form.get(name) ?? "").trim() || null;

  try {
    const document = await api.post<Record<string, unknown>>(
      "/api/compliance/export",
      {
        venture_id: text("venture_id"),
        framework: text("framework"),
        since: text("since"),
        until: text("until"),
      },
    );

    const integrity = document.integrity as { content_hash?: string } | undefined;
    const freshness = document.control_freshness_at_export as
      | { statement?: string }
      | undefined;

    return {
      ok: freshness?.statement ?? "Export produced.",
      hash: integrity?.content_hash,
      document: JSON.stringify(document, null, 2),
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
    throw error;
  }
}
