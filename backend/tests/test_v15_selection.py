from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.orchestration import RoleUnavailable, family, select_connection


def connection(pk, agent, roles=("analyst", "counter_analyst", "verifier"), model=""):
    return SimpleNamespace(pk=pk, agent=agent, roles=list(roles), model=model)


def test_three_families_prefer_unused_verifier_and_respect_role_eligibility():
    values = [connection(1, "codex"), connection(2, "claude"), connection(3, "third")]
    config = {"allow_same_family_fallback": True}
    with patch("core.orchestration.candidates", return_value=values):
        assert select_connection("analyst", config)[0].pk == 1
        assert select_connection("counter_analyst", config, "openai", ["openai"])[0].pk == 2
        assert (
            select_connection("verifier", config, "anthropic", ["openai", "anthropic"])[0].pk == 3
        )
        values[2].roles = ["analyst"]
        assert (
            select_connection("verifier", config, "anthropic", ["openai", "anthropic"])[0].pk == 1
        )


def test_accounts_and_model_names_do_not_fabricate_family_diversity():
    values = [connection(1, "codex", model="gpt-5"), connection(2, "codex", model="gpt-6")]
    assert family(values[0]) == family(values[1]) == "openai"
    with patch("core.orchestration.candidates", return_value=values):
        selected, warning = select_connection(
            "counter_analyst", {"allow_same_family_fallback": True}, "openai"
        )
        assert selected.pk == 1 and warning
        with pytest.raises(RoleUnavailable, match="different model family"):
            select_connection("counter_analyst", {"allow_same_family_fallback": False}, "openai")


def test_empty_roles_never_satisfy_assignment():
    with patch("core.orchestration.candidates", return_value=[connection(1, "codex", roles=[])]):
        with pytest.raises(RoleUnavailable, match="No available AI connection"):
            select_connection("analyst", {"allow_same_family_fallback": True})
