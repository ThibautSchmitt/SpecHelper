import json

import pytest

from core.discussion_output import message_text, normalize_messages


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_transport_message_is_not_user_visible(depth):
    value = "Bonjour ! Le message est bien reçu."
    encoded = value
    for _ in range(depth):
        encoded = json.dumps({"message":encoded}, ensure_ascii=False)
    assert message_text(encoded, "Bonjour") == value


@pytest.mark.parametrize("content,question", [
    ('{"message":"literal data"}', "Return a JSON object"),
    ('{"message":"literal data"}', 'Retourne exactement {"message":"literal data"}'),
    ('```json\n{"message":"literal data"}\n```', "Montre un exemple"),
    ('{"message":"literal data","status":"active"}', "Show the record"),
    ('{"message":"one","message":"two"}', "Explain the behavior"),
    ('{"message":{"field":"value"}}', "Explain the behavior"),
    ('{"message":""}', "Explain the behavior"),
])
def test_literal_json_examples_and_business_objects_are_preserved(content, question):
    assert message_text(content, question) == content


def test_nested_partial_transport_waits_for_a_complete_string():
    assert message_text('{"message":"Bonj', "Bonjour", partial=True) == ""
    assert message_text('{"message":"Bonjour"}', "Bonjour", partial=True) == "Bonjour"
    assert message_text('{"message":"Bonj', "Show JSON", partial=True) == '{"message":"Bonj'


def test_only_assistant_discussion_replies_are_unwrapped():
    envelope = '{"message":"Bonjour"}'
    records = [
        {"role":"user","kind":"need","content":envelope},
        {"role":"assistant","kind":"discussion_reply","content":envelope},
        {"role":"user","kind":"discussion","content":"Bonjour"},
        {"role":"assistant","kind":"discussion_reply","content":envelope},
        {"role":"assistant","kind":"session_notice","content":envelope},
    ]
    result = normalize_messages(records)
    assert result[0]["content"] == envelope
    assert result[1]["content"] == envelope  # User explicitly supplied a JSON object.
    assert result[3]["content"] == "Bonjour"
    assert result[4]["content"] == envelope
