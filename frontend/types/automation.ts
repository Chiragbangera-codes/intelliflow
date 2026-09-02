export type AutomationStatus = 'success' | 'failure' | 'partial';

export interface AutomationCondition {
  field: string;
  operator: string;
  value: unknown;
}

export interface AutomationAction {
  type: string;
  config: Record<string, unknown>;
}

export interface AutomationRule {
  id: string;
  name: string;
  description: string | null;
  trigger_event: string;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationRuleCreatePayload {
  name: string;
  trigger_event: string;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
  description?: string | null;
  is_active?: boolean;
}

export interface AutomationRuleUpdatePayload {
  name?: string | null;
  trigger_event?: string | null;
  conditions?: AutomationCondition[] | null;
  actions?: AutomationAction[] | null;
  description?: string | null;
  is_active?: boolean | null;
}

export interface AutomationRuleListResponse {
  items: AutomationRule[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AutomationExecution {
  id: string;
  rule_id: string;
  event_id: string | null;
  event_type: string;
  status: AutomationStatus;
  action_results: Record<string, unknown>[];
  error_message: string | null;
  execution_time_ms: number | null;
  created_at: string;
}

export interface AutomationExecutionListResponse {
  items: AutomationExecution[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AutomationTestResult {
  rule_id: string;
  matched: boolean;
  conditions_met: boolean;
  dry_run: boolean;
  actions_to_execute: number;
  duration_ms: number;
}
