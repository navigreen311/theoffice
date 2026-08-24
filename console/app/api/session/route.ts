import { NextResponse } from "next/server";

import { SESSION_COOKIE, verifyToken } from "@/lib/api";

/**
 * Sign-in. The token is verified against the API, then stored in an httpOnly cookie.
 *
 * httpOnly and sameSite=strict are the point. The browser holds the credential but
 * cannot read it, so an XSS in this console cannot exfiltrate it - and because every
 * API call happens server-side, the token never appears in a prop, a hydration payload
 * or a network request the browser makes.
 */

/**
 * Whether to mark the cookie `Secure`, from the protocol actually in use.
 *
 * This used to be `process.env.NODE_ENV === "production"`, which is wrong in a way that
 * is invisible until somebody tries to sign in: `next start` sets NODE_ENV=production,
 * so a production build served over plain http emitted a `Secure` cookie, **the browser
 * silently discarded it**, and the sign-in redirected to a page that bounced straight
 * back to the login screen. It looks exactly like a rejected token.
 *
 * The deployment documentation warned about this failure - "the console will appear to
 * accept a sign-in and then behave as though nobody signed in" - and then the local
 * experience shipped with it.
 *
 * Reading the protocol instead is both correct and safer. Over https the cookie is
 * `Secure`, which is what production needs. Over http it is not, which is what makes a
 * local build usable. `x-forwarded-proto` comes first because behind Caddy the app
 * receives http on the internal hop while the browser is on https - trusting the raw
 * URL there would drop `Secure` in production, which is the one direction that must
 * never happen silently.
 */
function isSecureRequest(request: Request): boolean {
  const forwarded = request.headers.get("x-forwarded-proto");
  if (forwarded) {
    // May be a list when there are several proxies. The first entry is the client hop.
    return forwarded.split(",")[0].trim() === "https";
  }
  return new URL(request.url).protocol === "https:";
}

export async function POST(request: Request) {
  const form = await request.formData();
  const token = String(form.get("token") ?? "");

  if (!token || !(await verifyToken(token))) {
    return NextResponse.redirect(new URL("/login?error=1", request.url), 303);
  }

  const response = NextResponse.redirect(new URL("/", request.url), 303);
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "strict",
    secure: isSecureRequest(request),
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return response;
}

/** Sign out. */
export async function DELETE(request: Request) {
  const response = NextResponse.redirect(new URL("/login", request.url), 303);
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
