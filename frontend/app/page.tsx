"use client";

import { AuthGuard } from "@dome-layer/dome-ui";
import Link from "next/link";
import { usePendingRuns } from "@/hooks/useRuns";
import { RunCard } from "@/components/RunCard";

export default function ApprovalsPage() {
  const { runs, loading, error } = usePendingRuns();

  return (
    <AuthGuard>
      <main className="flex-1 max-w-[960px] mx-auto w-full px-6 md:px-8 py-10">
        <h1
          className="text-xl font-semibold mb-2 tracking-dome-tight"
          style={{ color: "var(--color-text-primary)" }}
        >
          Pending approvals
        </h1>
        <p className="mb-6 text-sm" style={{ color: "var(--color-text-secondary)" }}>
          Invoices the governed agent flow has routed to a human for sign-off.
        </p>

        {loading && (
          <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>
            Loading…
          </p>
        )}
        {error && (
          <p className="text-sm" style={{ color: "var(--color-error)" }}>
            {error}
          </p>
        )}
        {!loading && !error && runs.length === 0 && (
          <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>
            Nothing waiting for approval right now.
          </p>
        )}

        <div className="grid gap-4">
          {runs.map((run) => (
            <Link
              key={run.workflow_run_id}
              href={`/runs/${run.workflow_run_id}`}
              className="block"
            >
              <RunCard run={run} />
            </Link>
          ))}
        </div>
      </main>
    </AuthGuard>
  );
}
