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
    secure: process.env.NODE_ENV === "production",
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
