from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from trace_agent_server.models import Decision, Event, Run


def derive_explanation(session: Session, run: Run) -> dict[str, Any]:
    events = list(session.scalars(select(Event).where(Event.run_id == run.id).order_by(Event.seq)))
    session.execute(delete(Decision).where(Decision.run_id == run.id))
    session.flush()

    flags: list[dict[str, Any]] = []
    seen_flags: set[tuple[str, str]] = set()
    loop_tracker: dict[tuple[str, str], list[Event]] = defaultdict(list)
    failure_streaks: dict[str, int] = defaultdict(int)
    last_failure_by_tool: dict[str, Event] = {}
    last_failure_by_command: dict[str, Event] = {}
    retry_count = 0

    def add_flag(flag_type: str, label: str, event_ids: list[int], metadata: dict[str, Any] | None = None) -> None:
        key = (flag_type, label)
        if key in seen_flags:
            return
        seen_flags.add(key)
        flags.append({"type": flag_type, "label": label, "event_ids": event_ids, "metadata": metadata or {}})

    def add_decision(
        *,
        seq: int,
        kind: str,
        label: str,
        chosen_action: str,
        rationale_summary: str,
        evidence_event_ids: list[int],
        trigger_event_ids: list[int] | None = None,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            Decision(
                run_id=run.id,
                seq=seq,
                kind=kind,
                label=label,
                chosen_action=chosen_action,
                rationale_summary=rationale_summary,
                trigger_event_ids=trigger_event_ids or evidence_event_ids,
                evidence_event_ids=evidence_event_ids,
                alternatives=[],
                outcome=outcome,
                decision_metadata=metadata or {},
            )
        )

    for event in events:
        if event.type == "tool.requested":
            tool_name = event.tool_name or "unknown tool"
            add_decision(
                seq=event.seq,
                kind="tool_choice",
                label=f"Selected {tool_name}",
                chosen_action=tool_name,
                rationale_summary=f"The agent changed state by requesting {tool_name}.",
                evidence_event_ids=[event.id],
                outcome="requested",
            )
            key = (tool_name, event.summary)
            loop_tracker[key].append(event)
            if len(loop_tracker[key]) >= 3:
                add_flag(
                    "loop",
                    f"{tool_name} repeated {len(loop_tracker[key])} times without a new observable branch.",
                    [item.id for item in loop_tracker[key][-3:]],
                    {"tool_name": tool_name},
                )
            if tool_name in last_failure_by_tool:
                failed_event = last_failure_by_tool[tool_name]
                retry_count += 1
                add_decision(
                    seq=event.seq,
                    kind="retry",
                    label=f"Retried {tool_name}",
                    chosen_action=tool_name,
                    rationale_summary=f"The agent retried {tool_name} after a previous failure.",
                    evidence_event_ids=[failed_event.id, event.id],
                    outcome="retry",
                )

        if event.type == "tool.failed":
            tool_name = event.tool_name or "unknown tool"
            last_failure_by_tool[tool_name] = event
            failure_streaks[event.step_id or tool_name] += 1
            if failure_streaks[event.step_id or tool_name] >= 2:
                add_flag(
                    "blocker",
                    f"{tool_name} failed repeatedly on the same step.",
                    [event.id],
                    {"tool_name": tool_name, "step_id": event.step_id},
                )

        if event.type == "tool.succeeded":
            tool_name = event.tool_name or "unknown tool"
            failure_streaks[event.step_id or tool_name] = 0
            if tool_name in last_failure_by_tool:
                failed_event = last_failure_by_tool.pop(tool_name)
                add_decision(
                    seq=event.seq,
                    kind="recovery",
                    label=f"Recovered {tool_name}",
                    chosen_action=tool_name,
                    rationale_summary=f"The agent recovered by completing {tool_name} after a prior failure.",
                    evidence_event_ids=[failed_event.id, event.id],
                    outcome="succeeded",
                )

        if event.type == "command.started":
            command_name = str(event.event_metadata.get("command") or "unknown command")
            add_decision(
                seq=event.seq,
                kind="command",
                label=f"Ran command {command_name}",
                chosen_action=command_name,
                rationale_summary=f"The agent executed command {command_name}.",
                evidence_event_ids=[event.id],
                outcome="started",
            )

        if event.type == "command.failed":
            command_name = str(event.event_metadata.get("command") or "unknown command")
            last_failure_by_command[command_name] = event
            failure_streaks[event.step_id or command_name] += 1
            add_flag(
                "command_failure",
                f"{command_name} failed and may have blocked the run.",
                [event.id],
                {"command": command_name, "step_id": event.step_id},
            )

        if event.type == "command.succeeded":
            command_name = str(event.event_metadata.get("command") or "unknown command")
            failure_streaks[event.step_id or command_name] = 0
            if command_name in last_failure_by_command:
                failed_event = last_failure_by_command.pop(command_name)
                add_decision(
                    seq=event.seq,
                    kind="recovery",
                    label=f"Recovered command {command_name}",
                    chosen_action=command_name,
                    rationale_summary=f"The agent recovered by re-running {command_name} successfully.",
                    evidence_event_ids=[failed_event.id, event.id],
                    outcome="succeeded",
                )

        if event.type == "run.completed":
            add_decision(
                seq=event.seq,
                kind="completion",
                label="Completed run",
                chosen_action="complete",
                rationale_summary="The run ended with a final answer.",
                evidence_event_ids=[event.id],
                outcome="completed",
            )
        if event.type == "run.failed":
            add_decision(
                seq=event.seq,
                kind="termination",
                label="Failed run",
                chosen_action="fail",
                rationale_summary="The run ended after unresolved errors.",
                evidence_event_ids=[event.id],
                outcome="failed",
            )

    session.flush()
    ordered_decisions = list(session.scalars(select(Decision).where(Decision.run_id == run.id).order_by(Decision.seq)))
    narrative: list[dict[str, Any]] = []
    if events:
        narrative.append({"text": f"The run started with goal: {run.goal}", "evidence_event_ids": [events[0].id]})
    if run.tool_count:
        tool_names = sorted({event.tool_name for event in events if event.tool_name})
        narrative.append(
            {
                "text": f"The agent executed {run.tool_count} tool call(s) across {len(tool_names)} tool(s): {', '.join(tool_names)}.",
                "evidence_event_ids": [event.id for event in events if event.type in {"tool.succeeded", "tool.failed"}],
            }
        )
    command_events = [event for event in events if event.type in {"command.succeeded", "command.failed"}]
    if command_events:
        command_names = sorted({str(event.event_metadata.get("command") or "unknown command") for event in command_events})
        narrative.append(
            {
                "text": f"The agent executed {len(command_events)} command result(s): {', '.join(command_names[:4])}.",
                "evidence_event_ids": [event.id for event in command_events],
            }
        )
    if flags:
        narrative.append(
            {
                "text": "Observed blockers or loops were detected and attached to evidence below.",
                "evidence_event_ids": [event_id for flag in flags for event_id in flag["event_ids"]],
            }
        )
    if ordered_decisions:
        first_labels = ", ".join(decision.label for decision in ordered_decisions[:3])
        narrative.append(
            {
                "text": f"Key turning points: {first_labels}.",
                "evidence_event_ids": [event_id for decision in ordered_decisions[:3] for event_id in decision.evidence_event_ids],
            }
        )
    if run.final_output_summary:
        tail_event = events[-1] if events else None
        narrative.append(
            {
                "text": f"Final outcome: {run.final_output_summary}",
                "evidence_event_ids": [tail_event.id] if tail_event else [],
            }
        )

    run.retry_count = retry_count
    run.flag_cache = flags
    run.explanation_cache = {"narrative": narrative}
    session.flush()
    return {"narrative": narrative, "flags": flags, "decisions": ordered_decisions}
