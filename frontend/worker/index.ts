import { CSP_DIRECTIVES, PROXY_PREFIXES, SECURITY_HEADERS, SHELL_ROUTES } from './site'

/**
 * The tool Worker (Sprint H phase 2, dome-docs sprints/SPRINT_H_HOSTING_EVAL.md). The tool is a
 * static Next.js export in ASSETS; this Worker runs in front of every request except
 * /_next/static/* (wrangler.jsonc), which is served directly, free and uncounted.
 *
 * It keeps the security the Vercel middleware gave:
 * - every HTML page gets a fresh nonce, in its CSP header (`'nonce-…' 'strict-dynamic'`) and on
 *   every <script> and script preload in the page. That is safe because the HTML is our own build output: the only
 *   inline scripts in it are Next's and the theme script, and nothing a visitor sends can reach it.
 * - HTML is never cached, so a nonce is never reused;
 * - the security headers that were in vercel.json go on every response.
 *
 * - paths in PROXY_PREFIXES are passed through to the tool's backend (env.API_ORIGIN), as the
 *   Vercel rewrite did; the response streams back untouched (server-sent events included).
 *
 * Tool-specific values live in site.ts. Keep this file identical across the tools.
 */

export interface Env {
  ASSETS: Fetcher
  /** "true" on every tool host (production too, since 2026-10-20): every response gets X-Robots-Tag: noindex. */
  DOME_NOINDEX?: string
  /** The backend that PROXY_PREFIXES go to, for tools that call their API same-origin. */
  API_ORIGIN?: string
}

/** The tool's CSP (site.ts) with this response's nonce in place of {NONCE}. */
export function contentSecurityPolicy(nonce: string): string {
  return CSP_DIRECTIVES.join('; ').replaceAll('{NONCE}', nonce)
}

export function isProxied(pathname: string): boolean {
  return PROXY_PREFIXES.some((prefix) => pathname.startsWith(prefix))
}

/** A nonce with 128 bits of randomness, base64 encoded. */
export function makeNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return btoa(String.fromCharCode(...bytes))
}

/**
 * The prebuilt path that serves a dynamic route, or undefined for any other path. The id segment
 * is swapped for the shell's and the rest kept, so `/dashboard/abc` gets the shell page and the
 * client-navigation payloads follow: `/dashboard/abc.txt` gets `/dashboard/_.txt`, and
 * `/dashboard/abc/__next._tree.txt` gets `/dashboard/_/__next._tree.txt`. `$` in Next's payload
 * names is percent-encoded, as Cloudflare stores it (the raw form answers with a redirect).
 */
export function shellFor(pathname: string): string | undefined {
  for (const { prefix, shell } of SHELL_ROUTES) {
    if (!pathname.startsWith(prefix) || pathname.length <= prefix.length) continue
    const rest = pathname.slice(prefix.length)
    const slash = rest.indexOf('/')
    const segment = slash === -1 ? rest : rest.slice(0, slash)
    const tail = slash === -1 ? '' : rest.slice(slash)
    const payload = segment.endsWith('.txt') ? '.txt' : ''
    return (shell + payload + tail).replace(/\$/g, '%24')
  }
  return undefined
}

export function isNoindexHost(host: string, env: Env): boolean {
  return env.DOME_NOINDEX === 'true' || host.endsWith('.workers.dev')
}

function withHeaders(response: Response, url: URL, env: Env): Response {
  for (const [key, value] of Object.entries(SECURITY_HEADERS)) response.headers.set(key, value)
  if (isNoindexHost(url.host, env)) response.headers.set('X-Robots-Tag', 'noindex')
  return response
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)
    // One canonical URL per page, permanently, as Vercel did (Cloudflare's own redirect is a 307).
    if (url.pathname.length > 1 && url.pathname.endsWith('/')) {
      url.pathname = url.pathname.replace(/\/+$/, '')
      return withHeaders(new Response(null, { status: 308, headers: { Location: url.pathname + url.search } }), url, env)
    }
    if (env.API_ORIGIN && isProxied(url.pathname)) {
      const upstream = await fetch(new Request(new URL(url.pathname + url.search, env.API_ORIGIN), request))
      return withHeaders(new Response(upstream.body, upstream), url, env)
    }
    const shell = shellFor(url.pathname)
    const assetRequest = shell ? new Request(new URL(shell, url), request) : request
    const asset = await env.ASSETS.fetch(assetRequest)

    const response = withHeaders(new Response(asset.body, asset), url, env)
    if (!(response.headers.get('Content-Type') ?? '').includes('text/html')) return response

    response.headers.set('Content-Type', 'text/html; charset=utf-8')

    const nonce = makeNonce()
    response.headers.set('Content-Security-Policy', contentSecurityPolicy(nonce))
    response.headers.set('Cache-Control', 'private, no-cache, no-store, max-age=0, must-revalidate')
    response.headers.delete('ETag')
    const addNonce = {
      element(element: Element) {
        element.setAttribute('nonce', nonce)
      },
    }
    // Script preloads need the nonce too: Chrome checks them against script-src, and with
    // 'strict-dynamic' an un-nonced preload is blocked (the script itself would still run).
    return new HTMLRewriter()
      .on('script', addNonce)
      .on('link[rel="preload"][as="script"]', addNonce)
      .on('link[rel="modulepreload"]', addNonce)
      .transform(response)
  },
} satisfies ExportedHandler<Env>
