"""Contract fixtures use httpx's real request/response handling without external calls."""

import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from core import ticket_providers as adapters


def connector(platform, **kwargs):
    return SimpleNamespace(
        platform=platform,
        base_url="https://tickets.example.test",
        username="",
        secret="test-secret",
        app_token="",
        api_version="v1",
        **kwargs,
    )


@pytest.fixture
def transport(monkeypatch):
    original = httpx.Client
    calls = []

    def install(routes):
        def handle(request):
            calls.append(request)
            key = (request.method, request.url.path)
            assert key in routes, f"Unexpected HTTP request: {key}"
            value = routes[key]
            if callable(value):
                return value(request)
            status, body = value
            return httpx.Response(status, json=body)

        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
        )
        monkeypatch.setattr(adapters, "decrypt", lambda value: value)
        monkeypatch.setattr(adapters.github, "token", lambda: "shared-test-token")
        return calls

    return install


def github_routes(template=None):
    routes = {
        ("GET", "/repos/org/app/contents/.github/ISSUE_TEMPLATE"): (404, {}),
        ("GET", "/repos/org/.github/contents/.github/ISSUE_TEMPLATE"): (404, {}),
        ("GET", "/repos/org/.github"): (404, {}),
        ("GET", "/repos/org/app/labels"): (200, [{"name": "bug"}]),
        ("GET", "/repos/org/app/assignees"): (200, [{"login": "alice"}]),
    }
    if template:
        name, text = template
        path = ".github/ISSUE_TEMPLATE/" + name
        routes[("GET", "/repos/org/app/contents/.github/ISSUE_TEMPLATE")] = (
            200,
            [{"path": path, "name": name, "type": "file"}],
        )
        routes[("GET", "/repos/org/app/contents/" + path)] = (
            200,
            {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()},
        )
    return routes


def github_connector():
    value = connector("github")
    value.base_url = "https://api.github.com"
    return value


def test_github_forms_required_fields_defaults_and_create(transport):
    form = """name: Bug report
title: 'Bug: '
labels: [bug]
body:
  - type: input
    id: expected
    attributes: {label: Expected behavior, description: Describe the outcome}
    validations: {required: true}
  - type: dropdown
    id: severity
    attributes: {label: Severity, options: [Low, High], default: 0}
  - type: checkboxes
    id: agreement
    attributes:
      label: Confirmation
      options:
        - {label: I checked the issue, required: true}
"""
    routes = github_routes(("bug.yml", form))
    routes[("POST", "/repos/org/app/issues")] = (
        201,
        {"id": 42, "number": 7, "html_url": "https://github.com/org/app/issues/7"},
    )
    calls = transport(routes)
    provider = adapters.provider_for(github_connector())
    options = provider.options("org/app", ".github/ISSUE_TEMPLATE/bug.yml")
    assert options["fields"][0]["required"]
    assert options["fields"][1]["default"] == "Low"
    payload = dict(
        title="New issue",
        body="Business context",
        template_id=".github/ISSUE_TEMPLATE/bug.yml",
        fields={},
    )
    with pytest.raises(adapters.TicketProviderError, match="required"):
        provider.create("org/app", payload, "spechelper:123")
    assert all(call.method != "POST" for call in calls)
    payload.update(
        fields={"expected": "Correct result", "agreement-0": True},
        labels=["bug"],
        assignees=["alice"],
    )
    assert provider.create("org/app", payload, "spechelper:123")["external_key"] == "7"
    sent = json.loads(calls[-1].content)
    assert "Correct result" in sent["body"] and "spechelper:123" in sent["body"]
    assert calls[-1].headers["Authorization"] == "Bearer shared-test-token"
    assert sent["body"].count("### Expected behavior") == 1
    assert sent["body"] == adapters.render_body(payload, options, "spechelper:123")


def test_github_markdown_revision_and_missing_template(transport):
    routes = github_routes(
        ("feature.md", "---\nname: Feature\nlabels: [enhancement]\n---\n## Context\n")
    )
    transport(routes)
    provider = adapters.provider_for(github_connector())
    first = provider.options("org/app", ".github/ISSUE_TEMPLATE/feature.md")
    assert first["template_body"] == "## Context\n"
    routes[("GET", "/repos/org/app/contents/.github/ISSUE_TEMPLATE/feature.md")] = (
        200,
        {"content": base64.b64encode(b"## Revised context").decode()},
    )
    assert (
        provider.options("org/app", ".github/ISSUE_TEMPLATE/feature.md")["revision"]
        != first["revision"]
    )
    with pytest.raises(adapters.TicketProviderError, match="no longer"):
        provider.options("org/app", "unlisted.md")


@pytest.mark.parametrize(
    "text",
    ["name: &a [*a]", "!!python/object/apply:os.system ['touch /tmp/unsafe']", "- not a form"],
)
def test_untrusted_yaml_rejected(text):
    with pytest.raises(adapters.TicketProviderError):
        adapters.structured_yaml(text)


@pytest.mark.parametrize("status", [401, 403, 302])
def test_permission_errors_and_redirects_never_expose_secrets(transport, status):
    calls = transport({("GET", "/api/v4/projects"): (status, {"error": "test-secret"})})
    provider = adapters.provider_for(connector("gitlab"))
    with pytest.raises(adapters.TicketProviderError) as error:
        provider.test()
    assert "test-secret" not in str(error.value)
    assert len(calls) == 1


def test_gitlab_inherited_templates_and_creation(transport):
    routes = {
        ("GET", "/api/v4/projects"): (
            200,
            [{"id": 8, "name": "Application", "path_with_namespace": "org/app"}],
        ),
        ("GET", "/api/v4/projects/8/templates/issues"): (
            200,
            [{"key": "Default", "name": "Default"}],
        ),
        ("GET", "/api/v4/projects/8/templates/issues/Default"): (
            200,
            {"content": "## Context\n\n## Expected behavior"},
        ),
        ("GET", "/api/v4/projects/8/labels"): (200, [{"name": "feature"}]),
        ("GET", "/api/v4/projects/8/members/all"): (200, [{"id": 3, "name": "Alice"}]),
        ("POST", "/api/v4/projects/8/issues"): (
            201,
            {"id": 90, "iid": 4, "web_url": "https://tickets.example.test/org/app/-/issues/4"},
        ),
        ("GET", "/api/v4/projects/8/issues"): (
            200,
            [
                {
                    "id": 90,
                    "iid": 4,
                    "web_url": "https://tickets.example.test/org/app/-/issues/4",
                    "description": "spechelper:123",
                }
            ],
        ),
    }
    calls = transport(routes)
    provider = adapters.provider_for(connector("gitlab"))
    assert provider.projects()[0]["id"] == "8"
    assert provider.options("8", "Default")["template_body"].startswith("## Context")
    result = provider.create(
        "8",
        dict(
            title="Ticket",
            body="Context",
            template_id="Default",
            labels=["feature"],
            assignees=["3"],
        ),
        "spechelper:123",
    )
    assert result == provider.find("8", "spechelper:123")
    sent = json.loads(next(c for c in calls if c.method == "POST").content)
    assert sent["assignee_ids"] == ["3"]


def jira_routes():
    return {
        ("GET", "/rest/api/3/project/search"): (
            200,
            {"values": [{"id": "100", "key": "APP", "name": "App"}], "isLast": True},
        ),
        ("GET", "/rest/api/3/issue/createmeta/100/issuetypes"): (
            200,
            {"issueTypes": [{"id": "1", "name": "Task"}]},
        ),
        ("GET", "/rest/api/3/issue/createmeta/100/issuetypes/1"): (
            200,
            {
                "fields": [
                    {
                        "fieldId": "summary",
                        "name": "Summary",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "fieldId": "customfield_10",
                        "name": "Business area",
                        "required": True,
                        "schema": {"type": "option"},
                        "allowedValues": [{"id": "5", "value": "Sales"}],
                    },
                    {
                        "fieldId": "customfield_11",
                        "name": "Details",
                        "required": False,
                        "schema": {
                            "type": "string",
                            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
                        },
                    },
                ]
            },
        ),
        ("POST", "/rest/api/3/issue"): (201, {"id": "900", "key": "APP-9"}),
    }


def test_jira_metadata_required_custom_fields_and_adf(transport):
    calls = transport(jira_routes())
    provider = adapters.provider_for(connector("jira"))
    assert provider.projects()[0]["id"] == "100"
    assert provider.options("100", issue_type="1")["format"] == "adf"
    payload = dict(
        title="Business change", body="## Context\nImprove reporting", issue_type="1", fields={}
    )
    with pytest.raises(adapters.TicketProviderError, match="required"):
        provider.create("100", payload, "spechelper:123")
    payload["fields"] = {"customfield_10": "5", "customfield_11": "Additional evidence"}
    assert provider.create("100", payload, "spechelper:123")["external_key"] == "APP-9"
    sent = json.loads(calls[-1].content)["fields"]
    assert sent["description"]["type"] == "doc"
    assert "spechelper:123" in json.dumps(sent["description"])
    assert sent["customfield_10"] == {"id": "5"}
    assert sent["customfield_11"]["type"] == "doc"


def test_jira_unknown_required_field_is_explicit(transport):
    routes = jira_routes()
    routes[("GET", "/rest/api/3/issue/createmeta/100/issuetypes/1")][1]["fields"].append(
        {
            "fieldId": "special",
            "name": "Special",
            "required": True,
            "schema": {"type": "unrecognized"},
        }
    )
    transport(routes)
    with pytest.raises(adapters.TicketProviderError, match="not supported"):
        adapters.provider_for(connector("jira")).options("100", issue_type="1")


def glpi_routes():
    return {
        ("GET", "/apirest.php/initSession"): (200, {"session_token": "session-test"}),
        ("GET", "/apirest.php/getMyEntities"): (
            200,
            {"myentities": [{"id": 0, "name": "Root entity"}]},
        ),
        ("GET", "/apirest.php/ITILCategory"): (
            200,
            [{"id": 2, "name": "Applications", "entities_id": 0}],
        ),
        ("GET", "/apirest.php/TicketTemplate"): (404, {}),
        ("POST", "/apirest.php/Ticket"): (201, {"id": 12, "message": "Item added"}),
        ("GET", "/apirest.php/Ticket"): (
            200,
            [{"id": 12, "entities_id": 0, "content": "<p>spechelper:123</p>"}],
        ),
    }


def test_glpi_legacy_session_headers_html_and_template_fallback(transport):
    calls = transport(glpi_routes())
    value = connector("glpi")
    value.app_token = "app-test"
    provider = adapters.provider_for(value)
    options = provider.options("0")
    assert options["templates"] == [] and "legacy" in options["notice"]
    result = provider.create(
        "0",
        dict(title="Ticket", body="<script>unsafe</script>", fields={"itilcategories_id": "2"}),
        "spechelper:123",
    )
    assert result == provider.find("0", "spechelper:123")
    assert calls[0].headers["Authorization"] == "user_token test-secret"
    assert calls[0].headers["App-Token"] == "app-test"
    assert calls[1].headers["Session-Token"] == "session-test"
    assert "Authorization" not in calls[1].headers
    sent = json.loads(next(c for c in calls if c.method == "POST").content)
    assert "&lt;script&gt;" in sent["input"]["content"]


def test_glpi_v2_rejected():
    value = connector("glpi")
    value.api_version = "v2"
    with pytest.raises(adapters.TicketProviderError, match="legacy v1"):
        adapters.provider_for(value)


def test_timeout_after_post_is_uncertain_without_retry(transport):
    routes = github_routes()

    def timeout(request):
        raise httpx.ReadTimeout("test-secret", request=request)

    routes[("POST", "/repos/org/app/issues")] = timeout
    calls = transport(routes)
    with pytest.raises(adapters.NetworkUncertain) as error:
        adapters.provider_for(github_connector()).create(
            "org/app", {"title": "Ticket", "body": "Context"}, "spechelper:123"
        )
    assert "test-secret" not in str(error.value)
    assert len([c for c in calls if c.method == "POST"]) == 1


def test_github_reconciliation_uses_exact_reference_not_similar_text(transport):
    routes = github_routes()
    routes[("GET", "/repos/org/app/issues")] = (
        200,
        [
            {
                "id": 1,
                "number": 1,
                "html_url": "https://github.com/org/app/issues/1",
                "body": "spechelper:1234",
            }
        ],
    )
    transport(routes)
    assert adapters.provider_for(github_connector()).find("org/app", "spechelper:123") is None


def test_metadata_revision_changes_are_rejected_before_post(transport):
    calls = transport(github_routes())
    provider = adapters.provider_for(github_connector())
    with pytest.raises(adapters.TicketProviderError, match="changed"):
        provider.create(
            "org/app",
            {"title": "Ticket", "body": "Context", "options_revision": "outdated"},
            "spechelper:123",
        )
    assert not any(call.method == "POST" for call in calls)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://untrusted.example.test/ticket",
        "https://user:pass@github.com/org/app/issues/1",
    ],
)
def test_remote_ticket_urls_cannot_inject_navigation(transport, url):
    routes = github_routes()
    routes[("POST", "/repos/org/app/issues")] = (201, {"id": 1, "number": 1, "html_url": url})
    transport(routes)
    with pytest.raises(adapters.NetworkUncertain, match="invalid external URL"):
        adapters.provider_for(github_connector()).create(
            "org/app", {"title": "Ticket", "body": "Context"}, "spechelper:123"
        )


def glpi_template_routes():
    routes = glpi_routes()
    routes[("GET", "/apirest.php/TicketTemplate")] = (
        200,
        [{"id": 7, "name": "Required organization fields", "entities_id": 0}],
    )
    for suffix in ("Mandatory", "Predefined", "Hidden", "Readonly"):
        routes[("GET", f"/apirest.php/TicketTemplate/7/TicketTemplate{suffix}Field")] = (200, [])
    routes[("GET", "/apirest.php/listSearchOptions/Ticket")] = (
        200,
        {
            "1": {"table": "glpi_tickets", "field": "name", "name": "Title"},
            "21": {"table": "glpi_tickets", "field": "content", "name": "Description"},
            "7": {"table": "glpi_itilcategories", "field": "completename", "name": "Category"},
            "14": {"table": "glpi_tickets", "field": "type", "name": "Ticket type"},
            "10": {"table": "glpi_tickets", "field": "urgency", "name": "Urgency"},
            "11": {"table": "glpi_tickets", "field": "impact", "name": "Impact"},
            "3": {"table": "glpi_tickets", "field": "priority", "name": "Priority"},
            "9": {"table": "glpi_requesttypes", "field": "name", "name": "Request source"},
        },
    )
    return routes


def test_glpi_unsupported_template_rule_is_not_silently_ignored(transport):
    routes = glpi_template_routes()
    routes[("GET", "/apirest.php/TicketTemplate/7/TicketTemplateMandatoryField")] = (
        200,
        [{"num": 999, "tickettemplates_id": 7}],
    )
    calls = transport(routes)
    provider = adapters.provider_for(connector("glpi"))
    with pytest.raises(adapters.TicketProviderError, match="unsupported field"):
        provider.create(
            "0", {"title": "Ticket", "body": "Context", "template_id": "7"}, "spechelper:123"
        )
    assert not any(call.method == "POST" for call in calls)


def test_glpi_supported_template_required_defaults_and_real_form_key(transport):
    routes = glpi_template_routes()
    routes[("GET", "/apirest.php/TicketTemplate/7/TicketTemplateMandatoryField")] = (
        200,
        [{"num": 1}, {"num": 21}, {"num": 7}],
    )
    routes[("GET", "/apirest.php/TicketTemplate/7/TicketTemplatePredefinedField")] = (
        200,
        [
            {"num": 1, "value": "Application request"},
            {"num": 21, "value": "<p>Business context</p>"},
            {"num": 7, "value": 2},
            {"num": 14, "value": 2},
        ],
    )
    calls = transport(routes)
    provider = adapters.provider_for(connector("glpi"))
    options = provider.options("0", "7")
    assert options["defaults"]["title"] == "Application request"
    assert options["template_body"] == "Business context"
    assert options["fields"][0]["required"]
    payload = {
        "title": "Application request",
        "body": "Business context: requested improvement",
        "template_id": "7",
        "fields": {},
    }
    provider.create("0", payload, "spechelper:123")
    sent = json.loads(calls[-1].content)["input"]
    assert sent["_tickettemplate"] == 7
    assert "_tickettemplates_id" not in sent
    assert sent["itilcategories_id"] == 2 and sent["type"] == 2


def test_glpi_hidden_defaults_cannot_be_changed(transport):
    routes = glpi_template_routes()
    routes[("GET", "/apirest.php/TicketTemplate/7/TicketTemplatePredefinedField")] = (
        200,
        [{"num": 7, "value": 2}],
    )
    routes[("GET", "/apirest.php/TicketTemplate/7/TicketTemplateHiddenField")] = (200, [{"num": 7}])
    calls = transport(routes)
    provider = adapters.provider_for(connector("glpi"))
    assert provider.options("0", "7")["fields"][0]["read_only"]
    with pytest.raises(adapters.TicketProviderError, match="fixed"):
        provider.create(
            "0",
            {
                "title": "Ticket",
                "body": "Context",
                "template_id": "7",
                "fields": {"itilcategories_id": "3"},
            },
            "spechelper:123",
        )
    assert not any(call.method == "POST" for call in calls)


@pytest.mark.parametrize("mask", [20, "20"])
def test_glpi_template_mask_and_requesttype_choices_come_from_server(transport, mask):
    routes = glpi_template_routes()
    routes[("GET", "/apirest.php/TicketTemplate/7/TicketTemplateMandatoryField")] = (
        200,
        [{"num": 10}, {"num": 9}],
    )
    routes[("GET", "/apirest.php/getGlpiConfig")] = (200, {"cfg_glpi": {"urgency_mask": mask}})
    routes[("GET", "/apirest.php/RequestType")] = (200, [{"id": 1, "name": "Helpdesk"}])
    transport(routes)
    options = adapters.provider_for(connector("glpi")).options("0", "7")
    fields = {x["id"]: x for x in options["fields"]}
    assert fields["urgency"]["options"] == [{"id": "2", "name": "2"}, {"id": "4", "name": "4"}]
    assert fields["requesttypes_id"]["required"]


def test_glpi_template_permissions_have_documented_fallback(transport):
    routes = glpi_routes()
    routes[("GET", "/apirest.php/TicketTemplate")] = (403, {"error": "Permission denied"})
    transport(routes)
    options = adapters.provider_for(connector("glpi")).options("0")
    assert options["templates"] == []
    assert "server-side validation" in options["notice"]


def test_jira_reconciliation_matches_adf_reference(transport):
    routes = jira_routes()
    routes[("GET", "/rest/api/3/search/jql")] = (
        200,
        {
            "issues": [
                {
                    "id": "900",
                    "key": "APP-9",
                    "fields": {
                        "description": {
                            "type": "doc",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "spechelper:123"}],
                                }
                            ],
                        }
                    },
                }
            ]
        },
    )
    transport(routes)
    provider = adapters.provider_for(connector("jira"))
    assert provider.find("100", "spechelper:123")["external_key"] == "APP-9"
    assert provider.find("100", "spechelper:12") is None


def test_provider_deadline_blocks_new_network_calls(transport):
    calls = transport(github_routes())
    provider = adapters.provider_for(github_connector())
    provider.deadline = 0
    with pytest.raises(adapters.TicketProviderError, match="too long"):
        provider.options("org/app")
    assert calls == []


def test_github_public_account_templates_are_inherited_only_without_local_configuration(transport):
    routes = github_routes()
    routes[("GET", "/repos/org/.github")] = (200, {"private": False})
    routes[("GET", "/repos/org/.github/contents/.github/ISSUE_TEMPLATE")] = (
        200,
        [{"type": "file", "name": "default.md", "path": ".github/ISSUE_TEMPLATE/default.md"}],
    )
    routes[("GET", "/repos/org/.github/contents/.github/ISSUE_TEMPLATE/default.md")] = (
        200,
        {"content": base64.b64encode(b"## Organization context").decode()},
    )
    calls = transport(routes)
    provider = adapters.provider_for(github_connector())
    options = provider.options("org/app", ".github/ISSUE_TEMPLATE/default.md")
    assert options["template_source"] == "org/.github"
    assert options["template_body"] == "## Organization context"
    routes[("GET", "/repos/org/app/contents/.github/ISSUE_TEMPLATE")] = (
        200,
        [{"type": "file", "name": "config.yml", "path": ".github/ISSUE_TEMPLATE/config.yml"}],
    )
    calls.clear()
    assert provider.options("org/app")["templates"] == []
    assert all("/repos/org/.github" not in call.url.path for call in calls)


def test_github_private_account_templates_are_not_native_defaults(transport):
    routes = github_routes()
    routes[("GET", "/repos/org/.github")] = (200, {"private": True})
    calls = transport(routes)
    assert adapters.provider_for(github_connector()).options("org/app")["templates"] == []
    assert all("/repos/org/.github/contents" not in call.url.path for call in calls)


def test_glpi_partial_template_rules_never_allow_publication(transport):
    routes = glpi_template_routes()
    routes[("GET", "/apirest.php/TicketTemplate/7/TicketTemplateMandatoryField")] = lambda request: (
        httpx.Response(206, json=[{"num": 1}], headers={"Content-Range": "0-0/2"})
    )
    calls = transport(routes)
    with pytest.raises(adapters.TicketProviderError, match="incomplete"):
        adapters.provider_for(connector("glpi")).create(
            "0", {"title": "Ticket", "body": "Context", "template_id": "7"}, "spechelper:123"
        )
    assert not any(call.method == "POST" for call in calls)


@pytest.mark.parametrize("status", [301, 302, 307, 308, 408, 500])
def test_post_redirects_and_timeout_status_are_uncertain_without_following(transport, status):
    routes = github_routes()
    routes[("POST", "/repos/org/app/issues")] = lambda request: httpx.Response(
        status, headers={"Location": "https://untrusted.example.test"}, json={}
    )
    calls = transport(routes)
    with pytest.raises(adapters.NetworkUncertain):
        adapters.provider_for(github_connector()).create(
            "org/app", {"title": "Ticket", "body": "Context"}, "spechelper:123"
        )
    assert len([call for call in calls if call.method == "POST"]) == 1


@pytest.mark.parametrize("identifier", [None, False, True, 0, -1, "", "null", "-2", 1.5])
@pytest.mark.parametrize("platform", ["github", "gitlab", "jira", "glpi"])
def test_null_or_invalid_external_ids_never_publish(transport, identifier, platform):
    transport({})
    provider = adapters.provider_for(
        github_connector() if platform == "github" else connector(platform)
    )
    value = {
        "id": identifier,
        "number": 1,
        "iid": 1,
        "key": "APP-1",
        "html_url": "https://github.com/org/app/issues/1",
        "web_url": "https://tickets.example.test/issues/1",
    }
    with pytest.raises(adapters.NetworkUncertain, match="invalid identifier"):
        provider.external(identifier if platform == "glpi" else value)


def test_markdown_defaults_normalize_csv_and_disclose_unavailable_choices(transport):
    routes = github_routes(
        (
            "feature.md",
            "---\nname: Feature\nlabels: 'bug, missing-label'\nassignees: 'alice, missing-user'\n---\n## Context",
        )
    )
    transport(routes)
    options = adapters.provider_for(github_connector()).options(
        "org/app", ".github/ISSUE_TEMPLATE/feature.md"
    )
    assert options["defaults"]["labels"] == ["bug"]
    assert options["defaults"]["assignees"] == ["alice"]
    assert options["unavailable_defaults"] == {
        "labels": ["missing-label"],
        "assignees": ["missing-user"],
    }
    assert "review labels and assignees" in options["notice"]
