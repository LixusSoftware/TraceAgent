from __future__ import annotations

from trace_agent_sdk.redaction import redact_keys, redact_payload, stable_hash, summarize_value


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


class TestRedactKeys:
    def test_masks_listed_keys_at_any_depth_and_keeps_the_rest_in_full(self) -> None:
        long_text = "x" * 500
        payload = {"api_key": "k", "nested": {"api_key": "k2", "text": long_text}, "items": [{"api_key": "k3"}]}

        masked = redact_keys(payload, ["api_key"])

        assert masked == {"api_key": "[redacted]", "nested": {"api_key": "[redacted]", "text": long_text}, "items": [{"api_key": "[redacted]"}]}

    def test_does_not_mutate_the_input_and_ignores_an_empty_list(self) -> None:
        payload = {"api_key": "k"}

        assert redact_keys(payload, ["api_key"]) == {"api_key": "[redacted]"}
        assert payload == {"api_key": "k"}
        assert redact_keys(payload, []) is payload
        assert redact_keys(payload, None) is payload


class TestSummarizeValue:
    def test_strings_are_returned_as_is(self) -> None:
        assert summarize_value("hello") == "hello"

    def test_dicts_are_rendered_as_sorted_json(self) -> None:
        assert summarize_value({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'

    def test_keys_can_keep_the_order_they_came_in_so_the_decisive_one_is_not_cut_off_last(self) -> None:
        assert summarize_value({"zeta": 1, "alfa": 2}, sort_keys=False) == '{"zeta": 1, "alfa": 2}'
        assert summarize_value({"zeta": 1, "alfa": 2}) == '{"alfa": 2, "zeta": 1}'

    def test_output_is_capped_at_max_length(self) -> None:
        summary = summarize_value({"items": list(range(500))}, max_length=50)
        assert len(summary) == 50
        assert summary.endswith("...")

    def test_applies_redaction(self) -> None:
        assert "secret" not in summarize_value({"password": "secret"}, ["password"])

    def test_keeps_accents_and_other_non_ascii_text_readable(self) -> None:
        summary = summarize_value({"mensaje": "El OEE bajó", "línea": "3", "nota": "日本語 ✓"})

        assert summary == '{"línea": "3", "mensaje": "El OEE bajó", "nota": "日本語 ✓"}'
        assert "\\u" not in summary

    def test_a_cut_summary_never_ends_inside_an_escape_sequence(self) -> None:
        summary = summarize_value({"texto": "ó" * 100}, max_length=40)

        assert len(summary) == 40
        assert summary.endswith("...")
        assert "\\u" not in summary
