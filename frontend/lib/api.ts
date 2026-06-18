import { authHeaders } from "@dome-layer/dome-ui/utils";
import type { RunRecord } from "@/types/runs";

// Base URL of the agent-flow shim. Env-first; falls back to localhost in dev.
export function agentFlowApiBase(): string {
  const env = process.env.NEXT_PUBLIC_AGENTFLOW_API_BASE;
  if (env) return env.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location.hostname === "localhost") {
    return "http://localhost:8000";
  }
  return "";
}

function url(path: string): string {
  return `${agentFlowApiBase()}/api/v1${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export async function listRuns(status?: string): Promise<{ runs: RunRecord[]; total: number }> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/runs${q}`);
}

export async function getRun(workflowRunId: string): Promise<RunRecord> {
  return request(`/runs/${encodeURIComponent(workflowRunId)}`);
}

export async function postDecision(
  workflowRunId: string,
  decision: "approve" | "reject",
  note?: string,
): Promise<RunRecord> {
  return request(`/runs/${encodeURIComponent(workflowRunId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });
}
