"""Measured costs include failed calls and repairs without fabricating unknowns."""

from scripts.qualification.harness import measured_usage

from core.usage_evidence import capture_usage


def test_multiple_responses_include_the_first_attempt_and_its_format_repair():
    step = {}
    capture_usage({"usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25}}, step)
    capture_usage({"usage": {"input_tokens": 30, "output_tokens": 7, "total_tokens": 37}}, step)
    assert step["usage"]["total_tokens"] == 62
    assert step["usage"]["input_tokens"] == 50
    assert len(step["usage_observations"]) == 2
    assert step["usage"]["cached_input_tokens"] is None


def test_missing_counts_cannot_be_reported_as_zero_or_as_a_complete_total():
    step = {}
    capture_usage({"usage": {"total_tokens": 12}}, step)
    capture_usage({"usage": {}}, step)
    assert all(value is None for value in step["usage"].values())
    capture_usage({}, step)
    assert len(step["usage_observations"]) == 2


def test_usage_accepts_only_nonnegative_integer_counts_without_private_fields():
    step = {}
    capture_usage({"usage": {"input_tokens": True, "output_tokens": -1,
                             "total_tokens": "12", "cached_input_tokens": 0,
                             "api_key": "private-provider-text"}}, step)
    assert step["usage_observations"] == [{"cached_input_tokens": 0}]
    assert "private-provider-text" not in str(step)


def test_partial_measurement_retains_known_tokens_without_calling_them_the_total():
    totals, coverage = measured_usage([
        {"usage": {"input_tokens": 100, "output_tokens": 5}},
        {"usage": {"input_tokens": 200, "output_tokens": 7}},
        {"usage": {}},
    ])
    assert totals["input_tokens"] is None
    assert coverage["input_tokens"] == {"observed_attempts": 2, "unknown_attempts": 1, "observed_tokens": 300}
    assert coverage["total_tokens"]["observed_tokens"] is None
