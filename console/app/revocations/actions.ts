"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";

/**
 * Revocation, as a Server Action.
 *
 * The form posts to the server; the server calls the API with the httpOnly cookie. The
 * browser never sees the token and never makes a cross-origin request.
 *
 * **Authority is not checked here.** It is checked twice on the API side - by
 * `humans.authorize` for venture scope and by `revocation.assert_authority` for scope
 * strength. Re-implementing either check in the console would create a second opinion
 * about who may do what, and the two would eventually disagree. The console's job is to
 * report the refusal, not to anticipate it.
 */
export async function revokeAction(
  _prev: { error?: string; ok?: string } | null,
  form: FormData,
): Promise<{ error?: string; ok?: string }> {
  const scope = String(form.get("scope") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  if (!reason) return { error: "A reason is required." };

  const payload: Record<string, string> = { scope, reason };
  for (const key of ["office_agent_id", "forge_id", "module_id", "venture_id"] as const) {
    const value = String(form.get(key) ?? "").trim();
    if (value) payload[key] = value;
  }

  try {
    const result = await api.post<{ revocation_id: string }>("/api/revocations", payload);
    revalidatePath("/revocations");
    return { ok: `Revoked. Takes effect on the target's very next call. ${result.revocation_id}` };
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: `${error.status}: ${error.detail}` };
    }
    throw error;
  }
}
