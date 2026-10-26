"""Antigravity's Gemini and Claude/GPT usage pools remain independent."""

import uuid

import pytest

from core.models import AIConnection, AIIdentity, AIModel
from core.providers import candidates, mark_failure, observe, public, record_quota

pytestmark = pytest.mark.django_db


def connections(*, account_key="a" * 64):
    identity = AIIdentity.objects.create(
        agent="antigravity", credential_id=uuid.uuid4(), account_key=account_key,
        status="CONNECTED", availability="AVAILABLE",
    )
    return [AIConnection.objects.create(
        agent="antigravity", identity=identity, model=model,
        status="CONNECTED", availability="AVAILABLE",
    ) for model in (
        "gemini-3.8-flash-low", "gemini-3.8-flash-high",
        "claude-sonnet-4-6", "gpt-oss-120b-medium",
    )]


def test_gemini_exhaustion_keeps_partner_pool_available_across_same_account_identities():
    first = connections()
    same_account = connections()
    other_account = connections(account_key="b" * 64)
    mark_failure(first[0].pk, "QUOTA_EXHAUSTED")
    available = {row.pk for row in candidates()}
    for rows in (first, same_account):
        assert all(row.pk not in available for row in rows[:2])
        assert all(public(row)["availability"] == "QUOTA_EXHAUSTED" for row in rows[:2])
        assert all(row.pk in available for row in rows[2:])
    assert all(row.pk in available for row in other_account)


def test_claude_and_gpt_share_the_partner_pool_but_not_gemini():
    rows = connections()
    mark_failure(rows[2].pk, "QUOTA_EXHAUSTED")
    available = {row.pk for row in candidates()}
    assert all(row.pk in available for row in rows[:2])
    assert all(row.pk not in available for row in rows[2:])
    assert public(rows[3])["availability"] == "QUOTA_EXHAUSTED"


def test_authentication_and_unavailable_metadata_do_not_clear_a_model_pool_failure():
    rows = connections()
    mark_failure(rows[0].pk, "QUOTA_EXHAUSTED")
    observe(rows[2], {"status": "CONNECTED", "quota_status": {
        "state": "unavailable", "reason": "unsupported_cli",
    }})
    assert public(rows[0])["availability"] == "QUOTA_EXHAUSTED"
    assert rows[0].pk not in {row.pk for row in candidates()}
    assert rows[2].pk in {row.pk for row in candidates()}


def test_an_unscoped_legacy_failure_still_blocks_all_models():
    rows = connections()
    AIIdentity.objects.filter(pk=rows[0].identity_id).update(availability="QUOTA_EXHAUSTED")
    assert all(row.pk not in {item.pk for item in candidates()} for row in rows)
    assert all(public(row)["availability"] == "QUOTA_EXHAUSTED" for row in rows)


def test_unknown_model_quota_failure_remains_account_wide():
    rows = connections()
    rows[0].model = "unknown-provider-model"
    rows[0].save(update_fields=["model"])
    mark_failure(rows[0].pk, "QUOTA_EXHAUSTED")
    assert all(row.pk not in {item.pk for item in candidates()} for row in rows)


def test_low_unscoped_usage_cannot_erase_a_model_pool_failure():
    rows = connections()
    mark_failure(rows[0].pk, "QUOTA_EXHAUSTED")
    record_quota(rows[0], {"session": {"used_percent": 1}})
    assert public(rows[0])["availability"] == "QUOTA_EXHAUSTED"
    assert rows[0].pk not in {row.pk for row in candidates()}


def test_explicit_provider_permission_recovers_only_the_observed_pool():
    rows = connections()
    mark_failure(rows[0].pk, "QUOTA_EXHAUSTED")
    mark_failure(rows[2].pk, "QUOTA_EXHAUSTED")
    observe(rows[0], {"status": "CONNECTED", "ordinary_usage_allowed": True,
                       "quota_status": {"state": "available"}})
    assert rows[0].pk in {row.pk for row in candidates()}
    assert public(rows[2])["availability"] == "QUOTA_EXHAUSTED"
    assert rows[2].pk not in {row.pk for row in candidates()}


@pytest.mark.parametrize("exhaustion", ["gemini", "both", "global"])
def test_editing_the_model_respects_the_target_pool_and_any_global_failure(client, exhaustion):
    import json

    rows = connections()
    for model in (rows[0].model, rows[2].model):
        AIModel.objects.create(agent='antigravity', identifier=model, source='adapter')
    mark_failure(rows[0].pk, 'QUOTA_EXHAUSTED')
    if exhaustion == 'both':
        mark_failure(rows[2].pk, 'QUOTA_EXHAUSTED')
    elif exhaustion == 'global':
        AIIdentity.objects.filter(pk=rows[0].identity_id).update(availability='QUOTA_EXHAUSTED')
    response = client.put(f'/api/ai-connections/{rows[0].pk}',
                          data=json.dumps({'model': rows[2].model}), content_type='application/json')
    assert response.status_code == 200, response.content
    assert (response.json()['availability'] != 'QUOTA_EXHAUSTED') == (exhaustion == 'gemini')
    assert (rows[0].pk in {row.pk for row in candidates()}) == (exhaustion == 'gemini')
    assert public(rows[1])['availability'] == 'QUOTA_EXHAUSTED'
