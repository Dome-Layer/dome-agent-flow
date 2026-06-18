"use client";

import { AuthGuard } from "@dome-layer/dome-ui";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useRun } from "@/hooks/useRuns";
import { DecisionPanel } from "@/components/DecisionPanel";
import { Badge, DecisionBadge, formatMoney, severityColor } from "@/components/ui";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      className="rounded-dome-card p-5 mb-4"
      style={{ background: "var(--color-bg-base)", border: "1px solid var(--color-border-default)" }}
    >
      <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--color-text-primary)" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function RunDetailPage() {
  const params = useParams<{ workflow_run_id: string }>();
  const id = (params?.workflow_run_id as string) ?? "";
  const { run, loading, error } = useRun(id);

  const inv = run?.invoice ?? null;
  const decision = run?.decision ?? null;
  const council = run?.council ?? null;
  const canDecide = run?.status === "pending_approval" || run?.status === "council";

  const fields: Array<[string, string | null | undefined]> = inv
    ? [
        ["Invoice #", inv.invoice_number],
        ["Vendor", inv.vendor_name],
        ["Amount", formatMoney(inv.amount, inv.currency)],
        ["Category", inv.category],
        ["Vendor country", inv.country],
        ["VAT id", inv.vat_id],
        ["PO number", inv.po_number],
        ["Invoice date", inv.invoice_date],
        ["Due date", inv.due_date],
        ["Extraction confidence", `${Math.round(inv.overall_confidence * 100)}%`],
      ]
    : [];

  return (
    <AuthGuard>
      <main className="flex-1 max-w-[820px] mx-auto w-full px-6 md:px-8 py-10">
        <Link
          href="/"
          className="text-sm"
          style={{ color: "var(--color-text-accent)" }}
        >
          ← Back to approvals
        </Link>

        {loading && (
          <p className="text-sm mt-6" style={{ color: "var(--color-text-secondary)" }}>
            Loading…
          </p>
        )}
        {error && (
          <p className="text-sm mt-6" style={{ color: "var(--color-error)" }}>
            {error}
          </p>
        )}

        {run && (
          <>
            <div className="flex items-start justify-between gap-4 mt-4 mb-6">
              <div>
                <h1
                  className="text-xl font-semibold tracking-dome-tight"
                  style={{ color: "var(--color-text-primary)" }}
                >
                  {inv?.vendor_name ?? "Unknown vendor"}
                </h1>
                <p className="text-xs mt-1" style={{ color: "var(--color-text-secondary)" }}>
                  {run.workflow_run_id} · {run.status}
                </p>
              </div>
              <div className="text-right">
                <div className="text-lg font-semibold" style={{ color: "var(--color-text-primary)" }}>
                  {formatMoney(inv?.amount ?? null, inv?.currency ?? null)}
                </div>
                {decision && (
                  <div className="mt-1 flex gap-2 justify-end">
                    <DecisionBadge decision={decision.decision} />
                    {decision.required_role && (
                      <Badge label={`${decision.required_role} sign-off`} color="var(--color-warning)" />
                    )}
                  </div>
                )}
              </div>
            </div>

            <Section title="Extracted invoice (Document Intelligence)">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
                {fields.map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-3 text-sm">
                    <dt style={{ color: "var(--color-text-secondary)" }}>{label}</dt>
                    <dd className="text-right" style={{ color: "var(--color-text-primary)" }}>
                      {value || "—"}
                    </dd>
                  </div>
                ))}
              </dl>
            </Section>

            {decision && (
              <Section title="Policy evaluation (rules engine)">
                {decision.flags.length === 0 && (
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>
                    No rules triggered.
                  </p>
                )}
                <ul className="space-y-2">
                  {decision.flags.map((f) => (
                    <li key={f.rule_id} className="flex gap-2 text-sm">
                      <span
                        className="mt-1 h-2 w-2 rounded-full shrink-0"
                        style={{ background: severityColor(f.severity) }}
                        aria-hidden
                      />
                      <span>
                        <span className="font-medium" style={{ color: "var(--color-text-primary)" }}>
                          {f.rule_id}
                        </span>
                        <span style={{ color: "var(--color-text-secondary)" }}> — {f.message}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {council && (
              <Section title="Council decision brief (LLM Council)">
                {council.verdict && (
                  <p className="text-sm mb-2" style={{ color: "var(--color-text-primary)" }}>
                    {council.verdict}
                  </p>
                )}
                {typeof council.consensus_confidence === "number" && (
                  <p className="text-xs mb-2" style={{ color: "var(--color-text-secondary)" }}>
                    Consensus confidence: {Math.round(council.consensus_confidence * 100)}%
                  </p>
                )}
                {council.recommendation && (
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>
                    <span className="font-medium">Recommendation: </span>
                    {council.recommendation}
                  </p>
                )}
                {council.dissenting_views && council.dissenting_views.length > 0 && (
                  <p className="text-xs mt-2" style={{ color: "var(--color-text-tertiary)" }}>
                    Dissent: {council.dissenting_views.join("; ")}
                  </p>
                )}
              </Section>
            )}

            {canDecide ? (
              <DecisionPanel workflowRunId={run.workflow_run_id} />
            ) : (
              run.status !== "received" &&
              run.status !== "extracted" && (
                <p className="text-sm mt-4" style={{ color: "var(--color-text-secondary)" }}>
                  This run is {run.status}
                  {run.decision_note ? ` — ${run.decision_note}` : ""}.
                </p>
              )
            )}
          </>
        )}
      </main>
    </AuthGuard>
  );
}
