/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Traces exactly the files the server needs into .next/standalone, so the runtime
  // image carries no node_modules tree and no build toolchain. Required by
  // console/Dockerfile; without it the image starts and cannot find its dependencies.
  output: "standalone",
  // No rewrites or proxy to the API. The browser never talks to it: every call happens
  // server-side, so there is no cross-origin request and no CORS configuration to get
  // wrong. See docs/plans/console-ui-PLAN.md.
};
export default nextConfig;
