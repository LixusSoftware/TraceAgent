export type RunListItem = {
  id: string;
  agent_name: string;
  goal: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  tool_count: number;
  error_count: number;
  retry_count: number;
  artifact_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  model: string | null;
  provider: string | null;
};

export type RunCreatePayload = {
  agent_name: string;
  goal: string;
  metadata?: Record<string, unknown>;
};

export type RunCreateResponse = {
  run_id: string;
  status: string;
};

export type TurnMessagePayload = {
  role: string;
  content?: unknown;
  [key: string]: unknown;
};

export type ToolDefinitionPayload = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  redact_fields: string[];
};

export type TurnCreatePayload = {
  provider?: string;
  model: string;
  messages: TurnMessagePayload[];
  tools?: ToolDefinitionPayload[];
  tool_choice?: string | Record<string, unknown>;
};

export type ToolCall = {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  step_id: string;
  parent_step_id: string | null;
};

export type TurnCreateResponse = {
  status: "message" | "requires_action";
  assistant_message: Record<string, unknown> | null;
  tool_calls: ToolCall[];
};

export type FinishRunResponse = {
  status: string;
  run_id: string;
  decisions?: number;
};

export type RunOverview = {
  id: string;
  agent_name: string;
  goal: string;
  status: string;
  provider: string | null;
  model: string | null;
  redaction_level: string;
  tool_count: number;
  error_count: number;
  retry_count: number;
  artifact_count: number;
  started_at: string;
  ended_at: string | null;
  metadata: Record<string, unknown>;
  final_output_summary: string | null;
  flags: Array<{ type: string; label: string; event_ids: number[] }>;
  execution: ExecutionMetadata;
  tool_chain: ToolChainItem[];
  command_chain: CommandChainItem[];
  file_activity: FileActivityItem[];
  patch_activity: PatchActivityItem[];
};

export type TokenUsageSummary = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  reasoning_tokens: number;
};

export type ExecutionMetadata = {
  duration_ms: number | null;
  total_event_count: number;
  model_turn_count: number;
  assistant_turn_count: number;
  tool_request_count: number;
  tool_success_count: number;
  tool_failure_count: number;
  command_count: number;
  command_failure_count: number;
  file_read_count: number;
  file_write_count: number;
  patch_count: number;
  registered_tool_count: number;
  current_state: string;
  last_event_type: string | null;
  last_event_actor: string | null;
  last_event_at: string | null;
  token_usage: TokenUsageSummary;
};

export type ToolChainItem = {
  call_id: string | null;
  step_id: string;
  parent_step_id: string | null;
  tool_name: string;
  status: string;
  event_ids: number[];
  requested_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  provider: string | null;
  model: string | null;
  args_summary: string | null;
  output_summary: string | null;
  error_summary: string | null;
  error_code: string | null;
  artifact_count: number;
};

export type CommandChainItem = {
  command_id: string | null;
  step_id: string;
  parent_step_id: string | null;
  command: string;
  status: string;
  event_ids: number[];
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  cwd: string | null;
  exit_code: number | null;
  output_summary: string | null;
  stdout_summary: string | null;
  stderr_summary: string | null;
  error_summary: string | null;
  error_code: string | null;
};

export type FileActivityItem = {
  step_id: string;
  parent_step_id: string | null;
  event_id: number;
  event_type: "file.read" | "file.written";
  path: string;
  status: string;
  change_type: string | null;
  summary: string;
  content_hash: string | null;
  before_hash: string | null;
  after_hash: string | null;
  diff_summary: string | null;
  line_additions: number | null;
  line_deletions: number | null;
  extension: string | null;
  size_bytes: number | null;
  timestamp: string;
};

export type PatchActivityItem = {
  step_id: string;
  parent_step_id: string | null;
  event_id: number;
  path: string;
  status: string;
  summary: string;
  before_hash: string | null;
  after_hash: string | null;
  diff_summary: string | null;
  line_additions: number | null;
  line_deletions: number | null;
  timestamp: string;
};

export type EventItem = {
  id: number;
  seq: number;
  timestamp: string;
  step_id: string | null;
  parent_step_id: string | null;
  actor: string;
  type: string;
  summary: string;
  status: string | null;
  duration_ms: number | null;
  provider: string | null;
  model: string | null;
  tool_name: string | null;
  artifact_refs: unknown[];
  error_code: string | null;
  payload_hash: string | null;
  payload_full: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
};

export type TimelineGroup = {
  step_id: string;
  label: string;
  status: string;
  step_type: string;
  tool_name: string | null;
  call_id: string | null;
  parent_step_id: string | null;
  event_count: number;
  started_at: string;
  ended_at: string;
  duration_ms: number | null;
  events: EventItem[];
};

export type TimelineResponse = {
  run_id: string;
  groups: TimelineGroup[];
};

export type GraphNode = {
  id: string;
  type: string;
  label: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  label: string | null;
  animated: boolean;
};

export type GraphResponse = {
  run_id: string;
  view: "execution" | "decisions" | "tool_chain";
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type Decision = {
  id: string;
  seq: number;
  kind: string;
  label: string;
  chosen_action: string;
  rationale_summary: string;
  trigger_event_ids: number[];
  evidence_event_ids: number[];
  alternatives: unknown[];
  outcome: string | null;
  metadata: Record<string, unknown>;
};

export type ExplanationResponse = {
  run_id: string;
  narrative: Array<{ text: string; evidence_event_ids: number[] }>;
  decisions: Decision[];
  flags: Array<{ type: string; label: string; event_ids: number[] }>;
  evidence: Record<string, EventItem>;
};

export type Artifact = {
  id: string;
  kind: string;
  label: string;
  summary: string;
  metadata: Record<string, unknown>;
  source_event_id: number | null;
  created_at: string;
};

export type ToolMetric = {
  tool_name: string;
  call_count: number;
  success_count: number;
  failure_count: number;
  total_duration_ms: number;
  avg_duration_ms: number;
  max_duration_ms: number;
  artifact_count: number;
  attributed_prompt_tokens: number;
  attributed_completion_tokens: number;
  attributed_total_tokens: number;
  estimated_cost_usd: number | null;
  providers: string[];
  models: string[];
};

export type SimilarRun = {
  run_id: string;
  agent_name: string;
  goal: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  tool_count: number;
  error_count: number;
  retry_count: number;
  provider: string | null;
  model: string | null;
  similarity_score: number;
  shared_tools: string[];
  reason: string;
};

export type SimilarRunFilters = {
  sameAgentOnly: boolean;
  status: "all" | "completed" | "failed" | "running";
  sharedToolsOnly: boolean;
  minScore: number;
  limit: number;
};

export type RunAnalytics = {
  run_id: string;
  tool_graph: GraphResponse;
  tool_metrics: ToolMetric[];
  similar_runs: SimilarRun[];
};

export type DiffTarget = {
  label: string;
  status: string | null;
  summary: string | null;
  event_ids: number[];
  step_id: string | null;
  duration_ms: number | null;
  metadata: Record<string, unknown>;
};

export type DiffPair = {
  relation: "shared" | "left_only" | "right_only" | "different";
  kind: string;
  summary: string;
  left: DiffTarget | null;
  right: DiffTarget | null;
};

export type OverviewDiff = {
  tool_count_delta: number;
  command_count_delta: number;
  error_count_delta: number;
  retry_count_delta: number;
  artifact_count_delta: number;
  token_total_delta: number;
  duration_ms_delta: number | null;
};

export type Divergence = {
  first_mismatch_kind: string;
  left_event_ids: number[];
  right_event_ids: number[];
  summary: string;
};

export type RootCause = {
  label: string;
  summary: string;
  first_causal_event_left: number | null;
  first_causal_event_right: number | null;
  supporting_event_ids: Record<string, number[]>;
  impact_summary: string;
  confidence: "high" | "medium" | "low";
};

export type RunCompareResponse = {
  left_run: RunOverview;
  right_run: RunOverview;
  overview_diff: OverviewDiff;
  divergence: Divergence | null;
  aligned_timeline: DiffPair[];
  tool_diff: DiffPair[];
  command_diff: DiffPair[];
  file_diff: DiffPair[];
  artifact_diff: DiffPair[];
  decision_diff: DiffPair[];
  root_cause: RootCause;
  evidence: Record<"left" | "right", Record<string, EventItem>>;
};

export type AuditFinding = {
  kind: "pii" | "prompt_injection" | "secret" | string;
  severity: "high" | "medium" | "low";
  source: string;
  score?: number;
  entity?: string;
  count?: number;
  patterns?: string[];
  message: string;
};

export type AuditEvent = {
  event_id: number;
  seq: number;
  timestamp: string | null;
  type: string;
  scope: "input" | "output" | "block";
  summary: string;
  severity: "high" | "medium" | "low" | "info";
  finding_count: number;
  findings: AuditFinding[];
  provider: string | null;
  model: string | null;
};

export type TurnOut = {
  id: string;
  run_id: string;
  seq: number;
  provider: string | null;
  model: string | null;
  messages: Record<string, unknown>[];
  assistant_message: Record<string, unknown> | null;
  tool_calls: Record<string, unknown>[];
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  reasoning_tokens: number | null;
  finish_reason: string | null;
  response_id: string | null;
  created_at: string;
};

export type RunFilters = {
  limit?: number;
  offset?: number;
  agent_name?: string;
  status?: string;
  provider?: string;
  model?: string;
  search?: string;
  started_after?: string;
  started_before?: string;
};

export type DashboardStats = {
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  running_runs: number;
  total_errors: number;
  total_tools: number;
  total_artifacts: number;
  avg_duration_ms: number | null;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
};

export type DashboardTrendItem = {
  date: string;
  runs: number;
  completed: number;
  failed: number;
};

export type DashboardTopTool = {
  tool_name: string;
  call_count: number;
  avg_duration_ms: number;
};

export type DashboardTopError = {
  error_code: string;
  count: number;
};

export type DashboardResponse = {
  stats: DashboardStats;
  trend: DashboardTrendItem[];
  top_tools: DashboardTopTool[];
  top_errors: DashboardTopError[];
  provider_distribution: Record<string, unknown>[];
  model_distribution: Record<string, unknown>[];
};

export type AuditReport = {
  run_id: string;
  security_score: number;
  pii_hit_count: number;
  injection_hit_count: number;
  secret_hit_count: number;
  block_count: number;
  guardrail_event_count: number;
  guardrail_events: AuditEvent[];
  flags: Array<{ type: string; label: string; event_ids: number[] }>;
};

