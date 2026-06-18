import type { Decision } from "@/types/runs";

export function formatMoney(amount: number | null, currency: string | null): string {
  if (amount == null) return "—";
  try {
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: currency || "EUR",
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency ?? ""}`.trim();
  }
}

const DECISION_LABEL: Record<Decision, string> = {
  auto_approve: "Auto-approved",
  route_to_council: "Council review",
  require_human: "Needs approval",
  reject: "Rejected",
};

const DECISION_COLOR: Record<Decision, string> = {
  auto_approve: "var(--color-success)",
  route_to_council: "var(--color-accent)",
  require_human: "var(--color-warning)",
  reject: "var(--color-error)",
};

export function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-dome"
      style={{ color, border: `1px solid ${color}` }}
    >
      {label}
    </span>
  );
}

export function DecisionBadge({ decision }: { decision: Decision }) {
  return <Badge label={DECISION_LABEL[decision]} color={DECISION_COLOR[decision]} />;
}

export function severityColor(severity: string): string {
  if (severity === "error") return "var(--color-error)";
  if (severity === "warning") return "var(--color-warning)";
  return "var(--color-text-tertiary)";
}
