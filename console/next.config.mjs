/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Where the build lands, overridable per process.
  //
  // `console-smoke.sh` runs its own `next build` in this directory, which replaced
  // `.next` underneath whatever `next start` the developer already had running on 3100.
  // The running server keeps serving from its own in-memory build, so its pages
  // reference chunk names the new `.next` does not contain: the chunk answers 400, React
  // fails with error #423, and the browser shows "a client-side exception has occurred".
  // A direct page load still works, which is what made it look intermittent - only a
  // client-side navigation, the way anybody actually reaches the page, fails.
  //
  // The smoke script sets NEXT_DIST_DIR so its build cannot touch the dev server's.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Traces exactly the files the server needs into .next/standalone, so the runtime
  // image carries no node_modules tree and no build toolchain. Required by
  // console/Dockerfile; without it the image starts and cannot find its dependencies.
  output: "standalone",
  // No rewrites or proxy to the API. The browser never talks to it: every call happens
  // server-side, so there is no cross-origin request and no CORS configuration to get
  // wrong. See docs/plans/console-ui-PLAN.md.
};
export default nextConfig;
