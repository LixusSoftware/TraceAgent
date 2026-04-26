import type {
  Artifact,
  ExplanationResponse,
  GraphResponse,
  RunAnalytics,
  RunCompareResponse,
  RunListItem,
  RunOverview,
  TimelineResponse
} from "../types";

export const sampleRuns: RunListItem[] = [
  {
    id: "run-left",
    agent_name: "coding-agent",
    goal: "Patch app.py and run tests",
    status: "completed",
    started_at: "2026-04-16T10:00:00Z",
    ended_at: "2026-04-16T10:02:00Z",
    tool_count: 2,
    error_count: 0,
    retry_count: 0,
    artifact_count: 1,
    model: "fake-model",
    provider: "openai"
  },
  {
    id: "run-right",
    agent_name: "coding-agent",
    goal: "Patch app.py and run tests",
    status: "failed",
    started_at: "2026-04-16T10:05:00Z",
    ended_at: "2026-04-16T10:07:00Z",
    tool_count: 2,
    error_count: 1,
    retry_count: 1,
    artifact_count: 1,
    model: "fake-model",
    provider: "openai"
  }
];

export const sampleRunOverview: RunOverview = {
  id: "run-left",
  agent_name: "coding-agent",
  goal: "Patch app.py and run tests",
  status: "completed",
  provider: "openai",
  model: "fake-model",
  redaction_level: "summary",
  tool_count: 2,
  error_count: 0,
  retry_count: 0,
  artifact_count: 1,
  started_at: "2026-04-16T10:00:00Z",
  ended_at: "2026-04-16T10:02:00Z",
  metadata: { scenario: "correct_edit" },
  final_output_summary: "Patched file and tests passed.",
  flags: [],
  execution: {
    duration_ms: 120000,
    total_event_count: 8,
    model_turn_count: 2,
    assistant_turn_count: 2,
    tool_request_count: 1,
    tool_success_count: 1,
    tool_failure_count: 0,
    command_count: 1,
    command_failure_count: 0,
    file_read_count: 1,
    file_write_count: 1,
    patch_count: 1,
    registered_tool_count: 1,
    current_state: "completed",
    last_event_type: "run.completed",
    last_event_actor: "proxy",
    last_event_at: "2026-04-16T10:02:00Z",
    token_usage: {
      prompt_tokens: 10,
      completion_tokens: 20,
      total_tokens: 30,
      reasoning_tokens: 5
    }
  },
  tool_chain: [
    {
      call_id: "call-1",
      step_id: "tool-1",
      parent_step_id: null,
      tool_name: "apply_patch",
      status: "succeeded",
      event_ids: [2, 3],
      requested_at: "2026-04-16T10:00:10Z",
      started_at: "2026-04-16T10:00:11Z",
      completed_at: "2026-04-16T10:00:14Z",
      duration_ms: 3000,
      provider: "openai",
      model: "fake-model",
      args_summary: "{\"path\":\"src/app.py\"}",
      output_summary: "Patch applied.",
      error_summary: null,
      error_code: null,
      artifact_count: 0
    }
  ],
  command_chain: [
    {
      command_id: "cmd-1",
      step_id: "command-1",
      parent_step_id: null,
      command: "python -m pytest -q",
      status: "succeeded",
      event_ids: [4, 5],
      started_at: "2026-04-16T10:00:20Z",
      completed_at: "2026-04-16T10:00:25Z",
      duration_ms: 5000,
      cwd: "C:/repo",
      exit_code: 0,
      output_summary: "{\"stdout\":\"1 passed\",\"stderr\":\"\"}",
      stdout_summary: "1 passed",
      stderr_summary: null,
      error_summary: null,
      error_code: null
    }
  ],
  file_activity: [
    {
      step_id: "file-read-1",
      parent_step_id: null,
      event_id: 6,
      event_type: "file.read",
      path: "src/app.py",
      status: "observed",
      change_type: null,
      summary: "Read src/app.py",
      content_hash: "hash-a",
      before_hash: null,
      after_hash: null,
      diff_summary: null,
      line_additions: null,
      line_deletions: null,
      extension: ".py",
      size_bytes: 20,
      timestamp: "2026-04-16T10:00:30Z"
    },
    {
      step_id: "file-write-1",
      parent_step_id: null,
      event_id: 7,
      event_type: "file.written",
      path: "src/app.py",
      status: "succeeded",
      change_type: "update",
      summary: "Updated src/app.py",
      content_hash: "hash-b",
      before_hash: "hash-a",
      after_hash: "hash-b",
      diff_summary: "@@ -1 +1 @@\n-print('before')\n+print('after')",
      line_additions: 1,
      line_deletions: 1,
      extension: ".py",
      size_bytes: 19,
      timestamp: "2026-04-16T10:00:40Z"
    }
  ],
  patch_activity: [
    {
      step_id: "patch-1",
      parent_step_id: null,
      event_id: 8,
      path: "src/app.py",
      status: "succeeded",
      summary: "Applied patch to src/app.py",
      before_hash: "hash-a",
      after_hash: "hash-b",
      diff_summary: "@@ -1 +1 @@\n-print('before')\n+print('after')",
      line_additions: 1,
      line_deletions: 1,
      timestamp: "2026-04-16T10:00:41Z"
    }
  ]
};

export const sampleTimeline: TimelineResponse = {
  run_id: "run-left",
  groups: [
    {
      step_id: "command-1",
      label: "python -m pytest -q",
      status: "succeeded",
      step_type: "command",
      tool_name: null,
      call_id: null,
      parent_step_id: null,
      event_count: 2,
      started_at: "2026-04-16T10:00:20Z",
      ended_at: "2026-04-16T10:00:25Z",
      duration_ms: 5000,
      events: [
        {
          id: 4,
          seq: 4,
          timestamp: "2026-04-16T10:00:20Z",
          step_id: "command-1",
          parent_step_id: null,
          actor: "sdk",
          type: "command.started",
          summary: "Started command.",
          status: "running",
          duration_ms: null,
          provider: null,
          model: null,
          tool_name: null,
          artifact_refs: [],
          error_code: null,
          metadata: {}
        },
        {
          id: 5,
          seq: 5,
          timestamp: "2026-04-16T10:00:25Z",
          step_id: "command-1",
          parent_step_id: null,
          actor: "sdk",
          type: "command.succeeded",
          summary: "Tests passed.",
          status: "succeeded",
          duration_ms: 5000,
          provider: null,
          model: null,
          tool_name: null,
          artifact_refs: [],
          error_code: null,
          metadata: { stdout_summary: "1 passed" }
        }
      ]
    }
  ]
};

export const sampleGraph: GraphResponse = {
  run_id: "run-left",
  view: "execution",
  nodes: [
    {
      id: "node-1",
      type: "event",
      label: "command.succeeded",
      position: { x: 10, y: 10 },
      data: { evidenceIds: [5] }
    }
  ],
  edges: []
};

export const sampleExplanation: ExplanationResponse = {
  run_id: "run-left",
  narrative: [
    {
      text: "Final outcome reached after patching the target file and rerunning tests.",
      evidence_event_ids: [5, 7]
    }
  ],
  decisions: [
    {
      id: "decision-1",
      seq: 1,
      kind: "tool_selection",
      label: "Selected apply_patch",
      chosen_action: "apply_patch",
      rationale_summary: "The run used apply_patch before running tests.",
      trigger_event_ids: [2],
      evidence_event_ids: [2, 3],
      alternatives: [],
      outcome: "succeeded",
      metadata: {}
    }
  ],
  flags: [],
  evidence: {
    "5": sampleTimeline.groups[0].events[1],
    "7": {
      id: 7,
      seq: 7,
      timestamp: "2026-04-16T10:00:40Z",
      step_id: "file-write-1",
      parent_step_id: null,
      actor: "sdk",
      type: "file.written",
      summary: "Updated src/app.py",
      status: "succeeded",
      duration_ms: null,
      provider: null,
      model: null,
      tool_name: null,
      artifact_refs: [],
      error_code: null,
      metadata: { path: "src/app.py" }
    }
  }
};

export const sampleArtifacts: Artifact[] = [
  {
    id: "artifact-1",
    kind: "report",
    label: "patch-report",
    summary: "Patched src/app.py and tests passed.",
    metadata: {},
    source_event_id: 9,
    created_at: "2026-04-16T10:02:00Z"
  }
];

export const sampleAnalytics: RunAnalytics = {
  run_id: "run-left",
  tool_graph: {
    run_id: "run-left",
    view: "tool_chain",
    nodes: [
      {
        id: "tool-node",
        type: "tool",
        label: "apply_patch",
        position: { x: 0, y: 0 },
        data: { evidenceIds: [2, 3] }
      }
    ],
    edges: []
  },
  tool_metrics: [
    {
      tool_name: "apply_patch",
      call_count: 1,
      success_count: 1,
      failure_count: 0,
      total_duration_ms: 3000,
      avg_duration_ms: 3000,
      max_duration_ms: 3000,
      artifact_count: 0,
      attributed_prompt_tokens: 5,
      attributed_completion_tokens: 10,
      attributed_total_tokens: 15,
      estimated_cost_usd: 0.0004,
      providers: ["openai"],
      models: ["fake-model"]
    }
  ],
  similar_runs: [
    {
      run_id: "run-right",
      agent_name: "coding-agent",
      goal: "Patch app.py and run tests",
      status: "failed",
      started_at: "2026-04-16T10:05:00Z",
      ended_at: "2026-04-16T10:07:00Z",
      duration_ms: 120000,
      tool_count: 2,
      error_count: 1,
      retry_count: 1,
      provider: "openai",
      model: "fake-model",
      similarity_score: 0.78,
      shared_tools: ["apply_patch"],
      reason: "Shared tool chain with different failure outcome."
    }
  ]
};

export const sampleCompareResponse: RunCompareResponse = {
  left_run: sampleRunOverview,
  right_run: {
    ...sampleRunOverview,
    id: "run-right",
    status: "failed",
    error_count: 1,
    retry_count: 1,
    final_output_summary: "Patched wrong file and tests still failed."
  },
  overview_diff: {
    tool_count_delta: 0,
    command_count_delta: 1,
    error_count_delta: 1,
    retry_count_delta: 1,
    artifact_count_delta: 0,
    token_total_delta: 4,
    duration_ms_delta: 5000
  },
  divergence: {
    first_mismatch_kind: "command",
    left_event_ids: [5],
    right_event_ids: [15],
    summary: "The second run failed its command while the first one passed."
  },
  aligned_timeline: [
    {
      relation: "different",
      kind: "command",
      summary: "Pytest command ended with different outcomes.",
      left: {
        label: "python -m pytest -q",
        status: "succeeded",
        summary: "Tests passed.",
        event_ids: [5],
        step_id: "command-1",
        duration_ms: 5000,
        metadata: {}
      },
      right: {
        label: "python -m pytest -q",
        status: "failed",
        summary: "Tests failed after wrong edit.",
        event_ids: [15],
        step_id: "command-2",
        duration_ms: 5000,
        metadata: {}
      }
    }
  ],
  tool_diff: [
    {
      relation: "shared",
      kind: "tool",
      summary: "apply_patch appears in both runs.",
      left: {
        label: "apply_patch",
        status: "succeeded",
        summary: "Patch applied.",
        event_ids: [2, 3],
        step_id: "tool-1",
        duration_ms: 3000,
        metadata: {}
      },
      right: {
        label: "apply_patch",
        status: "succeeded",
        summary: "Patch applied.",
        event_ids: [12, 13],
        step_id: "tool-2",
        duration_ms: 3000,
        metadata: {}
      }
    }
  ],
  command_diff: [
    {
      relation: "different",
      kind: "command",
      summary: "Pytest command ended with different outcomes.",
      left: {
        label: "python -m pytest -q",
        status: "succeeded",
        summary: "Tests passed.",
        event_ids: [5],
        step_id: "command-1",
        duration_ms: 5000,
        metadata: {}
      },
      right: {
        label: "python -m pytest -q",
        status: "failed",
        summary: "Tests failed after wrong edit.",
        event_ids: [15],
        step_id: "command-2",
        duration_ms: 5000,
        metadata: {}
      }
    }
  ],
  file_diff: [
    {
      relation: "different",
      kind: "file",
      summary: "The failed run touched another file.",
      left: {
        label: "src/app.py",
        status: "succeeded",
        summary: "Updated src/app.py",
        event_ids: [7],
        step_id: "file-write-1",
        duration_ms: null,
        metadata: {}
      },
      right: {
        label: "src/unused.py",
        status: "succeeded",
        summary: "Updated src/unused.py",
        event_ids: [17],
        step_id: "file-write-2",
        duration_ms: null,
        metadata: {}
      }
    }
  ],
  artifact_diff: [
    {
      relation: "different",
      kind: "artifact",
      summary: "Artifact summary diverged.",
      left: {
        label: "patch-report",
        status: "created",
        summary: "Patched src/app.py and tests passed.",
        event_ids: [9],
        step_id: "artifact-1",
        duration_ms: null,
        metadata: {}
      },
      right: {
        label: "patch-report",
        status: "created",
        summary: "Patched src/unused.py and tests failed.",
        event_ids: [19],
        step_id: "artifact-2",
        duration_ms: null,
        metadata: {}
      }
    }
  ],
  decision_diff: [],
  root_cause: {
    label: "command_failure",
    summary: "The failed run never recovered after the command failed.",
    first_causal_event_left: 5,
    first_causal_event_right: 15,
    supporting_event_ids: {
      left: [5],
      right: [15, 17]
    },
    impact_summary: "The second run ended failed and produced a different artifact.",
    confidence: "high"
  },
  evidence: {
    left: {
      "5": sampleTimeline.groups[0].events[1]
    },
    right: {
      "15": {
        id: 15,
        seq: 15,
        timestamp: "2026-04-16T10:06:20Z",
        step_id: "command-2",
        parent_step_id: null,
        actor: "sdk",
        type: "command.failed",
        summary: "Tests failed after wrong edit.",
        status: "failed",
        duration_ms: 5000,
        provider: null,
        model: null,
        tool_name: null,
        artifact_refs: [],
        error_code: "CommandError",
        metadata: { stderr_summary: "1 failed" }
      },
      "17": {
        id: 17,
        seq: 17,
        timestamp: "2026-04-16T10:06:40Z",
        step_id: "file-write-2",
        parent_step_id: null,
        actor: "sdk",
        type: "file.written",
        summary: "Updated src/unused.py",
        status: "succeeded",
        duration_ms: null,
        provider: null,
        model: null,
        tool_name: null,
        artifact_refs: [],
        error_code: null,
        metadata: { path: "src/unused.py" }
      }
    }
  }
};
