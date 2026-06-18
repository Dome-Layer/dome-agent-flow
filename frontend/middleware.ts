import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Nonce-based CSP. No 'unsafe-eval' / 'wasm-unsafe-eval' (no Mermaid, no react-pdf).
// connect-src allows the agent-flow shim API (Railway / *.domelayer.com) and the
// dome-auth service for sign-out; localhost entries cover local dev.
export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());

  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob:",
    "connect-src 'self' https://*.domelayer.com https://*.up.railway.app http://localhost:8000 http://localhost:8001",
    "font-src 'self' https://fonts.gstatic.com https://fonts.googleapis.com",
    "frame-ancestors 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|api/|favicon.ico|favicon.svg|favicon.png|apple-touch-icon.png).*)",
  ],
};
