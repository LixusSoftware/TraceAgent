from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    redact_fields: list[str] = Field(default_factory=list)


class ArtifactInput(BaseModel):
    kind: str
    label: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunCreateRequest(BaseModel):
    agent_name: str
    goal: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunCreateResponse(BaseModel):
    run_id: str
    status: str


class TurnCreateRequest(BaseModel):
    provider: str = "openai"
    model: str
    messages: list[dict[str, Any]]
    tools: list[ToolDefinition] = Field(default_factory=list)
    tool_choice: str | dict[str, Any] = "auto"


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    step_id: str
    parent_step_id: str | None = None


class TurnCreateResponse(BaseModel):
    status: Literal["message", "requires_action"]
    assistant_message: dict[str, Any] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ToolResultInput(BaseModel):
    call_id: str
    name: str
    step_id: str
    status: Literal["succeeded", "failed"]
    args: dict[str, Any] = Field(default_factory=dict)
    output_summary: str | None = None
    output_hash: str | None = None
    error_code: str | None = None
    error_summary: str | None = None
    duration_ms: int | None = None
    artifacts: list[ArtifactInput] = Field(default_factory=list)


class ToolResultsRequest(BaseModel):
    results: list[ToolResultInput]


class ObservationInput(BaseModel):
    kind: Literal["command", "file_read", "file_write", "patch", "artifact"]
    step_id: str | None = None
    parent_step_id: str | None = None
    status: Literal["succeeded", "failed"] | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_summary: str | None = None
    command_id: str | None = None
    command: str | None = None
    cwd: str | None = None
    exit_code: int | None = None
    output_summary: str | None = None
    stdout_summary: str | None = None
    stderr_summary: str | None = None
    path: str | None = None
    change_type: Literal["create", "update", "delete"] | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    content_hash: str | None = None
    diff_summary: str | None = None
    line_additions: int | None = None
    line_deletions: int | None = None
    extension: str | None = None
    size_bytes: int | None = None
    artifact: ArtifactInput | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationsRequest(BaseModel):
    observations: list[ObservationInput]


class FinishRunRequest(BaseModel):
    final_output: Any | None = None
    artifacts: list[ArtifactInput] = Field(default_factory=list)


class FailRunRequest(BaseModel):
    error_code: str
    error_summary: str


class EventOut(BaseModel):
    id: int
    seq: int
    timestamp: datetime
    step_id: str | None
    parent_step_id: str | None
    actor: str
    type: str
    summary: str
    status: str | None
    duration_ms: int | None
    provider: str | None
    model: str | None
    tool_name: str | None
    artifact_refs: list[Any]
    error_code: str | None
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class DecisionOut(BaseModel):
    id: str
    seq: int
    kind: str
    label: str
    chosen_action: str
    rationale_summary: str
    trigger_event_ids: list[int]
    evidence_event_ids: list[int]
    alternatives: list[Any]
    outcome: str | None
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class ArtifactOut(BaseModel):
    id: str
    kind: str
    label: str
    summary: str
    metadata: dict[str, Any]
    source_event_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NarrativeItem(BaseModel):
    text: str
    evidence_event_ids: list[int] = Field(default_factory=list)


class TokenUsageSummary(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0


class ExecutionMetadata(BaseModel):
    duration_ms: int | None
    total_event_count: int
    model_turn_count: int
    assistant_turn_count: int
    tool_request_count: int
    tool_success_count: int
    tool_failure_count: int
    command_count: int
    command_failure_count: int
    file_read_count: int
    file_write_count: int
    patch_count: int
    registered_tool_count: int
    current_state: str
    last_event_type: str | None
    last_event_actor: str | None
    last_event_at: datetime | None
    token_usage: TokenUsageSummary = Field(default_factory=TokenUsageSummary)


class ToolChainItem(BaseModel):
    call_id: str | None = None
    step_id: str
    parent_step_id: str | None = None
    tool_name: str
    status: str
    event_ids: list[int] = Field(default_factory=list)
    requested_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    provider: str | None = None
    model: str | None = None
    args_summary: str | None = None
    output_summary: str | None = None
    error_summary: str | None = None
    error_code: str | None = None
    artifact_count: int = 0


class CommandChainItem(BaseModel):
    command_id: str | None = None
    step_id: str
    parent_step_id: str | None = None
    command: str
    status: str
    event_ids: list[int] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    cwd: str | None = None
    exit_code: int | None = None
    output_summary: str | None = None
    stdout_summary: str | None = None
    stderr_summary: str | None = None
    error_summary: str | None = None
    error_code: str | None = None


class FileActivityItem(BaseModel):
    step_id: str
    parent_step_id: str | None = None
    event_id: int
    event_type: Literal["file.read", "file.written"]
    path: str
    status: str
    change_type: str | None = None
    summary: str
    content_hash: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    diff_summary: str | None = None
    line_additions: int | None = None
    line_deletions: int | None = None
    extension: str | None = None
    size_bytes: int | None = None
    timestamp: datetime


class PatchActivityItem(BaseModel):
    step_id: str
    parent_step_id: str | None = None
    event_id: int
    path: str
    status: str
    summary: str
    before_hash: str | None = None
    after_hash: str | None = None
    diff_summary: str | None = None
    line_additions: int | None = None
    line_deletions: int | None = None
    timestamp: datetime


class RunOverview(BaseModel):
    id: str
    agent_name: str
    goal: str
    status: str
    provider: str | None
    model: str | None
    redaction_level: str
    tool_count: int
    error_count: int
    retry_count: int
    artifact_count: int
    started_at: datetime
    ended_at: datetime | None
    metadata: dict[str, Any]
    final_output_summary: str | None
    flags: list[dict[str, Any]] = Field(default_factory=list)
    execution: ExecutionMetadata
    tool_chain: list[ToolChainItem] = Field(default_factory=list)
    command_chain: list[CommandChainItem] = Field(default_factory=list)
    file_activity: list[FileActivityItem] = Field(default_factory=list)
    patch_activity: list[PatchActivityItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TimelineGroup(BaseModel):
    step_id: str
    label: str
    status: str
    step_type: str
    tool_name: str | None
    call_id: str | None
    parent_step_id: str | None
    event_count: int
    started_at: datetime
    ended_at: datetime
    duration_ms: int | None
    events: list[EventOut]


class TimelineResponse(BaseModel):
    run_id: str
    groups: list[TimelineGroup]


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    position: dict[str, float]
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None
    animated: bool = False


class GraphResponse(BaseModel):
    run_id: str
    view: Literal["execution", "decisions", "tool_chain"]
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ToolMetricOut(BaseModel):
    tool_name: str
    call_count: int
    success_count: int
    failure_count: int
    total_duration_ms: int
    avg_duration_ms: int
    max_duration_ms: int
    artifact_count: int
    attributed_prompt_tokens: int
    attributed_completion_tokens: int
    attributed_total_tokens: int
    estimated_cost_usd: float | None = None
    providers: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)


class SimilarRunOut(BaseModel):
    run_id: str
    agent_name: str
    goal: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    tool_count: int
    error_count: int
    retry_count: int
    provider: str | None
    model: str | None
    similarity_score: float
    shared_tools: list[str] = Field(default_factory=list)
    reason: str


class RunAnalyticsResponse(BaseModel):
    run_id: str
    tool_graph: GraphResponse
    tool_metrics: list[ToolMetricOut]
    similar_runs: list[SimilarRunOut]


class DiffTargetOut(BaseModel):
    label: str
    status: str | None = None
    summary: str | None = None
    event_ids: list[int] = Field(default_factory=list)
    step_id: str | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiffPairOut(BaseModel):
    relation: Literal["shared", "left_only", "right_only", "different"]
    kind: str
    summary: str
    left: DiffTargetOut | None = None
    right: DiffTargetOut | None = None


class OverviewDiffOut(BaseModel):
    tool_count_delta: int
    command_count_delta: int
    error_count_delta: int
    retry_count_delta: int
    artifact_count_delta: int
    token_total_delta: int
    duration_ms_delta: int | None = None


class DivergenceOut(BaseModel):
    first_mismatch_kind: str
    left_event_ids: list[int] = Field(default_factory=list)
    right_event_ids: list[int] = Field(default_factory=list)
    summary: str


class RootCauseOut(BaseModel):
    label: str
    summary: str
    first_causal_event_left: int | None = None
    first_causal_event_right: int | None = None
    supporting_event_ids: dict[str, list[int]] = Field(default_factory=dict)
    impact_summary: str
    confidence: Literal["high", "medium", "low"]


class RunCompareResponse(BaseModel):
    left_run: RunOverview
    right_run: RunOverview
    overview_diff: OverviewDiffOut
    divergence: DivergenceOut | None = None
    aligned_timeline: list[DiffPairOut] = Field(default_factory=list)
    tool_diff: list[DiffPairOut] = Field(default_factory=list)
    command_diff: list[DiffPairOut] = Field(default_factory=list)
    file_diff: list[DiffPairOut] = Field(default_factory=list)
    artifact_diff: list[DiffPairOut] = Field(default_factory=list)
    decision_diff: list[DiffPairOut] = Field(default_factory=list)
    root_cause: RootCauseOut
    evidence: dict[str, dict[str, EventOut]] = Field(default_factory=dict)


class ExplanationResponse(BaseModel):
    run_id: str
    narrative: list[NarrativeItem]
    decisions: list[DecisionOut]
    flags: list[dict[str, Any]]
    evidence: dict[str, EventOut]


class RunListItem(BaseModel):
    id: str
    agent_name: str
    goal: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    tool_count: int
    error_count: int
    retry_count: int
    artifact_count: int
    model: str | None
    provider: str | None

    model_config = ConfigDict(from_attributes=True)
