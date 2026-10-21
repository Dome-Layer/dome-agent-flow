/**
 * What is specific to Agent Flow. The rest of worker/ is the shared tool Worker
 * (dome-docs/templates/tool-worker, Sprint H phase 2), copied unchanged into each tool.
 */

/**
 * The Content-Security-Policy. index.ts puts the per-response nonce in place of {NONCE}.
 * From the middleware it replaces (2026-10-21), minus what the static export no longer needs: the
 * localhost API origins (local development runs `next dev`, without this Worker) and Google Fonts
 * (next/font downloads the fonts at build time and serves them from this origin).
 */
export const CSP_DIRECTIVES = [
  "default-src 'self'",
  "script-src 'self' 'nonce-{NONCE}' 'strict-dynamic'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "connect-src 'self' https://*.domelayer.com https://*.up.railway.app",
  "font-src 'self'",
  "frame-ancestors 'none'",
]

/** Headers on every response (they were in next.config headers()). */
export const SECURITY_HEADERS: Record<string, string> = {
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
}

/**
 * Dynamic routes, served from one prebuilt page: /runs/<workflow run id> gets /runs/_ (with its
 * client-navigation payloads); the page reads the id from the URL (lib/routeId.ts).
 */
export const SHELL_ROUTES: { prefix: string; shell: string }[] = [{ prefix: '/runs/', shell: '/runs/_' }]

/** Paths passed through to a backend. None: the app calls the shim API cross-origin. */
export const PROXY_PREFIXES: string[] = []
