/**
 * A static export (Sprint H, 2026-10-21): Cloudflare serves out/ as static assets and the Worker in
 * worker/ adds the per-request CSP nonce and the security headers (worker/site.ts) that
 * middleware.ts and headers() used to set, and serves /runs/<id> from one prebuilt shell. No
 * backend proxy: the app calls the shim API cross-origin. Nothing here may need a server at
 * request time.
 *
 * @type {import('next').NextConfig}
 */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
