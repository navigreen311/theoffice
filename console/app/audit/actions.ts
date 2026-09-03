"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";

export type AuditState = { ok?: string; error?: string } | null;

/**
 * Run the chain verification and record it as a control result.
 *
 * This is the whole resolution to the two pages disagreeing: one verification, one
 * recorded row, and both screens read it. A check that runs on page load and reports its
 * answer without recording it is the thing that produced a green badge here and
 * `never_run` on Compliance — both accurate, describing the same property.
 */
export async function verifyChainAction(
  _prev: AuditState,
  _form: FormData,
): Promise<AuditState> {
  try {
    const result = await api.post<{
      recorded_verification: { verified_entries: number; entries: number; status: string };
    }>("/api/controls/audit-chain", {});
    revalidatePath("/audit");
    revalidatePath("/");
    const verification = result.recorded_verification;
    return {
      ok: `Recorded: ${verification.status} over ${verification.verified_entries} entries. Compliance reads this same result.`,
    };
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: `${error.status}: ${error.detail}` };
    }
    throw error;
  }
}
