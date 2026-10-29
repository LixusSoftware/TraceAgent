from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.models import Event, Run
from trace_agent_server.schemas import ToolResultInput
from trace_agent_server.services.events import record_event
from trace_agent_server.services.run_lifecycle import (
    apply_llm_usage,
    complete_run,
    expire_inactive_runs,
    fail_run_with,
    record_tool_result,
    token_count,
)

START = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def session(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", cors_origins=["http://localhost:5173"])
    app = create_app(settings)
    with TestClient(app).app.state.session_factory() as session:
        yield session


@pytest.fixture
def run(session) -> Run:
    run = Run(agent_name="agent", goal="goal")
    session.add(run)
    session.flush()
    return run


def as_utc(value: datetime) -> datetime:
    # SQLite hands datetimes back without a time zone: they are stored as UTC.
    return value.replace(tzinfo=timezone.utc)


def events_of(session, run: Run) -> list[Event]:
    return session.query(Event).filter_by(run_id=run.id).order_by(Event.seq).all()


class TestRecordEventTimestamp:
    def test_uses_the_given_timestamp(self, session, run) -> None:
        event = record_event(session, run, actor="otlp", event_type="x", summary="s", timestamp=START)
        assert as_utc(event.timestamp) == START

    def test_defaults_to_now(self, session, run) -> None:
        event = record_event(session, run, actor="otlp", event_type="x", summary="s")
        assert abs((datetime.now(timezone.utc) - as_utc(event.timestamp)).total_seconds()) < 5


class TestTokenCount:
    @pytest.mark.parametrize("value, expected", [(5, 5), (0, 0), (-1, 0), (True, 0), ("7", 0), (None, 0), (2.5, 0)])
    def test_only_positive_integers_count(self, value, expected) -> None:
        assert token_count(value) == expected


class TestApplyLlmUsage:
    def test_accumulates_and_keeps_the_first_identity(self, run) -> None:
        apply_llm_usage(run, provider="openai", model="m1", prompt_tokens=10, completion_tokens=2)
        apply_llm_usage(run, provider="anthropic", model="m2", prompt_tokens=5, completion_tokens=1)

        assert (run.provider, run.model) == ("openai", "m1")
        assert (run.total_prompt_tokens, run.total_completion_tokens) == (15, 3)

    def test_unknown_provider_is_ignored(self, run) -> None:
        apply_llm_usage(run, provider="unknown", model=None)
        assert run.provider is None
        assert run.model is None


class TestRecordToolResult:
    def result(self, **extra) -> ToolResultInput:
        return ToolResultInput(call_id="c1", name="search", step_id="s1", status="succeeded", args={"q": "x"}, **extra)

    def test_reported_times_stamp_both_events(self, session, run) -> None:
        end = START + timedelta(seconds=3)
        record_tool_result(session, run, self.result(duration_ms=3000), capture_full=True, started_at=START, ended_at=end)

        started, completed = [e for e in events_of(session, run) if e.type.startswith("tool.")]
        assert (as_utc(started.timestamp), as_utc(completed.timestamp)) == (START, end)
        assert completed.duration_ms == 3000
        assert run.tool_count == 1
        assert run.error_count == 0

    def test_a_failed_result_counts_an_error(self, session, run) -> None:
        failed = ToolResultInput(call_id="c1", name="search", step_id="s1", status="failed", error_code="Boom", error_summary="no")
        record_tool_result(session, run, failed, capture_full=False)

        assert (run.tool_count, run.error_count) == (1, 1)
        assert [e.type for e in events_of(session, run)] == ["tool.started", "tool.failed"]
        assert all(e.payload_full is None for e in events_of(session, run))


class TestFinalOutputAndToolOutput:
    def test_the_whole_final_output_is_kept_with_full_payloads_on_and_only_the_summary_without(self, session, run) -> None:
        long_output = {"recomendacion": "x" * 600, "causa": "avería"}

        complete_run(session, run, long_output, capture_full=True)
        completed = [e for e in events_of(session, run) if e.type == "run.completed"][0]

        assert completed.payload_full == {"final_output": long_output}
        assert len(completed.summary) <= 220

    def test_without_full_payloads_only_the_summary_is_stored(self, session, run) -> None:
        complete_run(session, run, {"a": 1})

        assert [e for e in events_of(session, run) if e.type == "run.completed"][0].payload_full is None

    def test_the_whole_tool_output_is_kept_next_to_its_summary(self, session, run) -> None:
        result = ToolResultInput(call_id="c1", name="check", step_id="s1", status="succeeded", args={}, output_summary="{...}", output={"veredicto": "descartado", "ventana": [60, 120]})

        record_tool_result(session, run, result, capture_full=True)

        done = [e for e in events_of(session, run) if e.type == "tool.succeeded"][0]
        assert done.payload_full == {"output_summary": "{...}", "output": {"veredicto": "descartado", "ventana": [60, 120]}}

    def test_a_tool_without_output_is_stored_as_before(self, session, run) -> None:
        record_tool_result(session, run, ToolResultInput(call_id="c1", name="check", step_id="s1", status="succeeded", args={}, output_summary="ok"), capture_full=True)

        done = [e for e in events_of(session, run) if e.type == "tool.succeeded"][0]
        assert done.payload_full == {"output_summary": "ok"}


class TestRunEnd:
    def test_complete_run_sets_status_summary_and_end_time(self, session, run) -> None:
        derivation = complete_run(session, run, {"answer": 42}, ended_at=START)

        assert run.status == "completed"
        assert as_utc(run.ended_at) == START
        assert "42" in run.final_output_summary
        assert "decisions" in derivation
        assert events_of(session, run)[-1].type == "run.completed"

    def test_fail_run_counts_the_error(self, session, run) -> None:
        fail_run_with(session, run, "ValueError", "boom", ended_at=START)

        assert (run.status, run.error_count, run.final_output_summary) == ("failed", 1, "boom")
        last = events_of(session, run)[-1]
        assert (last.type, last.error_code) == ("run.failed", "ValueError")


class TestExpireInactiveRuns:
    def stale_run(self, session, *, minutes_ago: int, status: str = "running") -> Run:
        run = Run(agent_name="agent", goal="goal", status=status)
        session.add(run)
        session.flush()
        run.updated_at = START - timedelta(minutes=minutes_ago)
        session.flush()
        return run

    def test_a_run_with_no_activity_is_failed_with_a_clear_reason(self, session) -> None:
        run = self.stale_run(session, minutes_ago=90)

        closed = expire_inactive_runs(session, timeout=timedelta(minutes=60), now=START)

        assert closed == 1
        assert run.status == "failed"
        assert "No activity for 60 minutes" in run.final_output_summary
        last = events_of(session, run)[-1]
        assert (last.type, last.error_code) == ("run.failed", "RunAbandoned")

    def test_a_recent_run_is_left_running(self, session) -> None:
        run = self.stale_run(session, minutes_ago=5)

        assert expire_inactive_runs(session, timeout=timedelta(minutes=60), now=START) == 0
        assert run.status == "running"

    def test_finished_runs_are_not_touched(self, session) -> None:
        run = self.stale_run(session, minutes_ago=500, status="completed")

        assert expire_inactive_runs(session, timeout=timedelta(minutes=60), now=START) == 0
        assert run.status == "completed"

    def test_an_active_run_keeps_going_as_events_arrive(self, session) -> None:
        run = self.stale_run(session, minutes_ago=90)
        record_event(session, run, actor="sdk", event_type="tool.started", summary="still working", timestamp=START)
        run.updated_at = START

        assert expire_inactive_runs(session, timeout=timedelta(minutes=60), now=START) == 0
        assert run.status == "running"
