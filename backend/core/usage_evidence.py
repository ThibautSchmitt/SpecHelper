"""Retain measured provider usage for every observed response, including failures."""

METRICS = ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens")


def capture_usage(response, step):
    """Never invent missing counts or retain arbitrary provider fields."""
    if "usage" not in response:
        return
    supplied = response["usage"]
    observed = {
        key: supplied[key] for key in METRICS
        if isinstance(supplied, dict) and type(supplied.get(key)) is int and supplied[key] >= 0
    }
    observations = step.setdefault("usage_observations", [])
    observations.append(observed)
    step["usage"] = {
        key: sum(row[key] for row in observations) if all(key in row for row in observations) else None
        for key in METRICS
    }
