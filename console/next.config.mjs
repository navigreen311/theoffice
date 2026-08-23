/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No rewrites or proxy to the API. The browser never talks to it: every call happens
  // server-side, so there is no cross-origin request and no CORS configuration to get
  // wrong. See docs/plans/console-ui-PLAN.md.
};
export default nextConfig;
