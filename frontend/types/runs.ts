export type Decision =
  | "auto_approve"
  | "route_to_council"
  | "require_human"
  | "reject";

export interface Invoice {
  invoice_number: string | null;
  vendor_name: string | null;
  amount: number | null;
  currency: string | null;
  category: string | null;
  country: string | null;
  vat_id: string | null;
  po_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  overall_confidence: number;
}

export interface RuleFlag {
  rule_id: string;
  severity: "info" | "warning" | "error";
  message: string;
}

export interface PolicyDecision {
  decision: Decision;
  required_role: string | null;
  human_in_loop: string;
  amount_tier_role: string;
  flags: RuleFlag[];
  rules_applied: string[];
  rules_triggered: string[];
  reasons: string[];
}

export interface CouncilMember {
  member_id: string;
  role: string;
  response: string;
  confidence: number;
  round: number;
}

export interface CouncilVerdict {
  verdict?: string;
  consensus_confidence?: number;
  dissenting_views?: string[];
  recommendation?: string;
  member_responses?: CouncilMember[];
}

export interface RunRecord {
  workflow_run_id: string;
  status: string;
  source: string;
  filename: string | null;
  invoice: Invoice | null;
  extraction: unknown | null;
  decision: PolicyDecision | null;
  council: CouncilVerdict | null;
  approver_id: string | null;
  decision_note: string | null;
  user_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}
