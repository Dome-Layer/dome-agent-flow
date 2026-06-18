"use client";

import { type ReactNode } from "react";
import { AuthProvider as DomeAuthProvider, useAuth } from "@dome-layer/dome-ui";
import { getToken } from "@dome-layer/dome-ui/utils";

function domeAuthBaseUrl(): string {
  if (typeof window === "undefined") return "https://auth.domelayer.com";
  const { hostname } = window.location;
  if (hostname === "localhost") return "http://localhost:8001";
  if (hostname.includes("staging")) return "https://auth.staging.domelayer.com";
  return "https://auth.domelayer.com";
}

async function revokeSession(): Promise<void> {
  const token = getToken();
  if (!token) return;
  await fetch(`${domeAuthBaseUrl()}/api/v1/auth/session`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => {}); // best-effort; local token always cleared by DomeAuthProvider
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return <DomeAuthProvider onSignOut={revokeSession}>{children}</DomeAuthProvider>;
}

export { useAuth };
