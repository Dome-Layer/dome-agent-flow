"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { postDecision } from "@/lib/api";

export function DecisionPanel({ workflowRunId }: { workflowRunId: string }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(decision: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await postDecision(workflowRunId, decision, note || undefined);
      router.push("/");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit decision");
      setBusy(false);
    }
  }

  return (
    <div
      className="rounded-dome-card p-5 mt-6"
      style={{
        background: "var(--color-bg-base)",
        border: "1px solid var(--color-border-default)",
      }}
    >
      <label
        className="block text-sm font-medium mb-2"
        style={{ color: "var(--color-text-primary)" }}
      >
        Approval note (recorded in the audit trail)
      </label>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        className="w-full rounded-dome p-2 text-sm mb-3"
        style={{
          background: "var(--color-bg-subtle)",
          border: "1px solid var(--color-border-default)",
          color: "var(--color-text-primary)",
        }}
        placeholder="Reason for the decision…"
      />
      {error && (
        <p className="text-sm mb-2" style={{ color: "var(--color-error)" }}>
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <button
          onClick={() => act("approve")}
          disabled={busy}
          className="px-4 py-2 rounded-dome text-sm font-medium disabled:opacity-60"
          style={{ background: "var(--color-success)", color: "#fff" }}
        >
          Approve
        </button>
        <button
          onClick={() => act("reject")}
          disabled={busy}
          className="px-4 py-2 rounded-dome text-sm font-medium disabled:opacity-60"
          style={{ background: "var(--color-error)", color: "#fff" }}
        >
          Reject
        </button>
      </div>
    </div>
  );
}
