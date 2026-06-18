import type { RunRecord } from "@/types/runs";
import { Badge, DecisionBadge, formatMoney } from "@/components/ui";

export function RunCard({ run }: { run: RunRecord }) {
  const inv = run.invoice;
  const d = run.decision;
  return (
    <div
      className="rounded-dome-card p-5 section-animate hover:border-dome-accent transition"
      style={{
        background: "var(--color-bg-base)",
        border: "1px solid var(--color-border-default)",
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold" style={{ color: "var(--color-text-primary)" }}>
            {inv?.vendor_name ?? "Unknown vendor"}
          </div>
          <div className="text-xs mt-0.5" style={{ color: "var(--color-text-secondary)" }}>
            {inv?.invoice_number ?? run.workflow_run_id}
            {inv?.category ? ` · ${inv.category}` : ""}
            {inv?.country ? ` · ${inv.country}` : ""}
          </div>
        </div>
        <div className="text-right">
          <div className="text-base font-semibold" style={{ color: "var(--color-text-primary)" }}>
            {formatMoney(inv?.amount ?? null, inv?.currency ?? null)}
          </div>
          {d?.required_role && (
            <div className="mt-1">
              <Badge label={`${d.required_role} sign-off`} color="var(--color-warning)" />
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 mt-3 flex-wrap">
        {d && <DecisionBadge decision={d.decision} />}
        {d && d.rules_triggered.length > 0 && (
          <span className="text-xs" style={{ color: "var(--color-text-tertiary)" }}>
            {d.rules_triggered.length} rule{d.rules_triggered.length === 1 ? "" : "s"} triggered
          </span>
        )}
        {run.council && <Badge label="Council consulted" color="var(--color-accent)" />}
      </div>
    </div>
  );
}
