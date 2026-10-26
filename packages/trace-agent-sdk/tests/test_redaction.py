from __future__ import annotations

from trace_agent_sdk.redaction import redact_payload, stable_hash, summarize_value


class TestStableHash:
    def test_is_independent_of_key_order(self) -> None:
        assert stable_hash({"a": 1, "b": [1, 2]}) == stable_hash({"b": [1, 2], "a": 1})

    def test_differs_for_different_values(self) -> None:
        assert stable_hash({"a": 1}) != stable_hash({"a": 2})

    def test_handles_values_json_cannot_encode(self) -> None:
        assert stable_hash({"when": object}) == stable_hash({"when": object})


class TestRedactPayload:
    def test_redacts_listed_fields_at_any_depth(self) -> None:
        payload = {"token": "abc", "nested": {"token": "def", "keep": 1}, "items": [{"token": "ghi"}]}

        redacted = redact_payload(payload, ["token"])

        assert redacted == {"token": "[redacted]", "nested": {"token": "[redacted]", "keep": 1}, "items": [{"token": "[redacted]"}]}

    def test_does_not_mutate_the_input(self) -> None:
        payload = {"token": "abc"}
        redact_payload(payload, ["token"])
        assert payload == {"token": "abc"}

    def test_truncates_long_strings_but_not_short_ones(self) -> None:
        assert redact_payload("short") == "short"
        long_value = "x" * 500
        redacted = redact_payload(long_value)
        assert len(redacted) == 160
        assert redacted.endswith("...")

    def test_leaves_other_types_untouched(self) -> None:
        assert redact_payload({"n": 3, "ok": True, "none": None}) == {"n": 3, "ok": True, "none": None}


class TestSummarizeValue:
    def test_strings_are_returned_as_is(self) -> None:
        assert summarize_value("hello") == "hello"

    def test_dicts_are_rendered_as_sorted_json(self) -> None:
        assert summarize_value({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'

    def test_output_is_capped_at_max_length(self) -> None:
        summary = summarize_value({"items": list(range(500))}, max_length=50)
        assert len(summary) == 50
        assert summary.endswith("...")

    def test_applies_redaction(self) -> None:
        assert "secret" not in summarize_value({"password": "secret"}, ["password"])
