"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";

export type AccessState = {
  error?: string;
  ok?: string;
  /** Shown once, never stored, never re-fetchable. */
  token?: string;
};

function fail(error: unknown): AccessState {
  if (error instanceof ApiError) return { error: `${error.status}: ${error.detail}` };
  throw error;
}

/**
 * Create a human and show their token exactly once.
 *
 * The token comes back in the response and is rendered on the next paint. It is never
 * written anywhere by this console — not to a cookie, not to `localStorage`, not into a
 * revalidated cache — and there is no route that can produce it again. If the operator
 * closes the tab before copying it, the answer is to reissue, which invalidates the one
 * they lost.
 */
export async function createHumanAction(
  _prev: AccessState | null,
  form: FormData,
): Promise<AccessState> {
  const text = (name: string) => String(form.get(name) ?? "").trim();

  if (!text("display_name") || !text("email")) {
    return { error: "A name and an email are required." };
  }

  try {
    const result = await api.post<{ human_id: string; token: string; note: string }>(
      "/api/humans",
      {
        display_name: text("display_name"),
        email: text("email"),
        role: text("role") || null,
        venture_id: text("venture_id") || null,
      },
    );
    revalidatePath("/access");
    return {
      ok: `Created ${text("display_name")}. ${result.note}`,
      token: result.token,
    };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Grant or remove a role.
 *
 * The rules are enforced in `humans.assert_may_grant` and are deliberately not
 * re-implemented here — a second copy of an authorisation rule is a second copy that
 * eventually disagrees, and the one in the console would be the one nobody audits. What
 * this does do is pass the intent through unchanged, so the API's refusal reaches the
 * operator with its own reason attached.
 */
export async function setRoleAction(
  _prev: AccessState | null,
  form: FormData,
): Promise<AccessState> {
  const humanId = String(form.get("human_id") ?? "");
  const role = String(form.get("role") ?? "");
  const venture = String(form.get("venture_id") ?? "").trim();
  const revoke = String(form.get("intent") ?? "") === "revoke";

  if (!humanId || !role) return { error: "Pick a person and a role." };

  try {
    const result = await api.post<{ status: string }>(
      `/api/humans/${humanId}/roles`,
      { role, venture_id: venture || null, revoke },
    );
    revalidatePath("/access");
    if (result.status === "no_such_role") {
      return { ok: `They did not hold ${role}${venture ? ` in ${venture}` : ""}.` };
    }
    return { ok: `${role} ${result.status}${venture ? ` for ${venture}` : ""}.` };
  } catch (error) {
    return fail(error);
  }
}

/** Suspend or reactivate. Takes effect on their next request, not their next session. */
export async function setStatusAction(
  _prev: AccessState | null,
  form: FormData,
): Promise<AccessState> {
  const humanId = String(form.get("human_id") ?? "");
  const status = String(form.get("intent") ?? "");
  const reason = String(form.get("reason") ?? "").trim();

  if (!reason) {
    return {
      error:
        "A reason is required. Suspending somebody's access is the kind of decision that gets reviewed later.",
    };
  }

  try {
    await api.post(`/api/humans/${humanId}/status`, { status, reason });
    revalidatePath("/access");
    return {
      ok:
        status === "suspended"
          ? "Suspended. They are refused on their next request, not their next session."
          : "Reactivated.",
    };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Rotate a token.
 *
 * The old one stops working the moment this returns, which is the point and is also the
 * thing most likely to surprise someone rotating their own — including the token the
 * current session is using.
 */
export async function reissueTokenAction(
  _prev: AccessState | null,
  form: FormData,
): Promise<AccessState> {
  const humanId = String(form.get("human_id") ?? "");
  if (!humanId) return { error: "Pick a person." };

  try {
    const result = await api.post<{ token: string; note: string }>(
      `/api/humans/${humanId}/token`,
      {},
    );
    revalidatePath("/access");
    return { ok: result.note, token: result.token };
  } catch (error) {
    return fail(error);
  }
}

/** Lift a revocation. The revocation row stays; `reinstated_at` records the lift. */
export async function reinstateAction(
  _prev: AccessState | null,
  form: FormData,
): Promise<AccessState> {
  const revocationId = String(form.get("revocation_id") ?? "");
  const reason = String(form.get("reason") ?? "").trim();

  if (!reason) {
    return {
      error:
        "A reason is required. Revocation is the kill switch; lifting one is a decision worth a sentence.",
    };
  }

  try {
    await api.post(`/api/revocations/${revocationId}/reinstate`, { reason });
    revalidatePath("/access");
    revalidatePath("/revocations");
    return { ok: "Reinstated. The revocation record stays, with the lift recorded on it." };
  } catch (error) {
    return fail(error);
  }
}

/**
 * Resolve an incident.
 *
 * An append, not an edit. The incident keeps its severity and its detail; what is added
 * is an account of what was done about it, which is the thing a later reader needs and
 * the thing that is lost when "resolve" means "set a flag".
 */
export async function resolveIncidentAction(
  _prev: AccessState | null,
  form: FormData,
): Promise<AccessState> {
  const incidentId = String(form.get("incident_id") ?? "");
  const resolution = String(form.get("resolution") ?? "").trim();

  if (!resolution) {
    return {
      error:
        "What was done? 'Resolved' with nothing attached is a status change, and the point of closing an incident is the account of what happened.",
    };
  }

  try {
    await api.post(`/api/incidents/${incidentId}/resolve`, { resolution });
    revalidatePath("/incidents");
    revalidatePath("/");
    return { ok: "Resolved. The incident itself is unchanged — this is an append." };
  } catch (error) {
    return fail(error);
  }
}
