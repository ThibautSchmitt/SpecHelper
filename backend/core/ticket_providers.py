"""Bounded, credential-isolated ticket API adapters. No agent execution is involved."""

import base64
import hashlib
import html
import json
import re
import time
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import httpx
import yaml

from . import github
from .secrets import decrypt

MAX_BYTES = 2_000_000
MAX_PAGES = 10


class TicketProviderError(ValueError):
    """A safe error that never contains a remote response or credential."""


class NetworkUncertain(TicketProviderError):
    """A write might have succeeded; reconcile before allowing another attempt."""


def field(identifier, label, kind="text", required=False, options=None, default="", description=""):
    return dict(
        id=str(identifier),
        label=str(label),
        type=kind,
        required=bool(required),
        options=options or [],
        default=default,
        description=str(description),
    )


def choice(identifier, name):
    return {"id": str(identifier), "name": str(name)}


def positive_id(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, str))
        or not re.fullmatch(r"[1-9][0-9]*", str(value))
    ):
        raise NetworkUncertain("Ticket creation response contains an invalid identifier")
    return str(value)


def template_defaults(metadata):
    defaults = {}
    for name in ("title", "labels", "assignees"):
        if name not in metadata:
            continue
        value = metadata[name]
        if name == "title":
            if not isinstance(value, str) or len(value) > 1000:
                raise TicketProviderError("Invalid ticket template defaults")
        else:
            if isinstance(value, str):
                if len(value) > 20000:
                    raise TicketProviderError("Ticket template defaults are too large")
                value = [part.strip() for part in value.split(",") if part.strip()]
            if (
                not isinstance(value, list)
                or len(value) > 100
                or any(not isinstance(part, str) or len(part) > 200 for part in value)
            ):
                raise TicketProviderError("Invalid ticket template defaults")
        defaults[name] = value
    return defaults


def has_reference(text, reference):
    return bool(re.search(r"(?<![\w:.-])" + re.escape(reference) + r"(?![\w:.-])", text))


def render_body(payload, options, reference=""):
    """Render the exact plain/Markdown content before platform encoding."""
    body = payload.get("body", "")
    if options.get("render_fields"):
        for definition in options.get("fields", []):
            value = payload.get("fields", {}).get(definition["id"], definition.get("default", ""))
            if isinstance(value, list):
                value = ", ".join(map(str, value))
            if isinstance(value, bool):
                value = "[x]" if value else "[ ]"
            body += f"\n\n### {definition['label']}\n\n{value}"
    if reference and not has_reference(body, reference):
        body += "\n\n" + reference
    return body.strip()


def plain_html(value):
    """Preserve block boundaries while displaying remote HTML as safe plain text."""

    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []
            self.ignored = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.ignored += 1
            elif not self.ignored and tag in ("p", "div", "br", "li", "h1", "h2", "h3", "pre"):
                self.parts.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.ignored = max(0, self.ignored - 1)
            elif not self.ignored and tag in ("p", "div", "li", "h1", "h2", "h3", "pre"):
                self.parts.append("\n")

        def handle_data(self, text):
            if not self.ignored:
                self.parts.append(text)

    reader = Reader()
    reader.feed(value)
    return "".join(reader.parts).strip()


def structured_yaml(text):
    """Reject alias expansion and excessively complex remote form definitions."""
    if len(text.encode()) > 200_000:
        raise TicketProviderError("Ticket template is too large")
    try:
        tokens = list(yaml.scan(text))
        if len(tokens) > 10000 or any(
            isinstance(t, (yaml.AliasToken, yaml.AnchorToken)) for t in tokens
        ):
            raise TicketProviderError("Unsupported ticket template structure")
        value = yaml.safe_load(text)
        if not isinstance(value, dict):
            raise TicketProviderError("Invalid ticket template")
        return value
    except (yaml.YAMLError, RecursionError, UnicodeError):
        raise TicketProviderError("Invalid ticket template") from None


class Provider:
    def __init__(self, connector):
        self.connector = connector
        self.base = connector.base_url.rstrip("/")
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        self.auth = None
        self.deadline = time.monotonic() + 45
        self.last_content_range = ""
        self.last_status = None

    def external_url(self, value, github_url=False):
        try:
            parsed = urlsplit(value)
            allowed = urlsplit("https://github.com" if github_url else self.base)
            if (
                (parsed.scheme, parsed.hostname, parsed.port)
                != (allowed.scheme, allowed.hostname, allowed.port)
                or parsed.username
                or parsed.password
            ):
                raise ValueError
        except (TypeError, ValueError):
            raise NetworkUncertain("Ticket response contains an invalid external URL") from None
        return value

    def request(
        self,
        method,
        path,
        *,
        params=None,
        data=None,
        optional=False,
        files=None,
        extra_headers=None,
    ):
        # All paths are locally constructed. Never follow remote URLs or redirects with credentials.
        if not path.startswith("/") or path.startswith("//") or ".." in path.split("/"):
            raise TicketProviderError("Invalid ticket API path")
        remaining = self.deadline - time.monotonic()
        if remaining < 2:
            raise TicketProviderError(
                "Ticket platform operation took too long; reload and try again"
            )
        try:
            with httpx.Client(
                timeout=httpx.Timeout(min(20, remaining), connect=min(5, remaining)),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                headers = {**self.headers, **(extra_headers or {})}
                if files:
                    headers.pop("Content-Type", None)
                content_arguments = {"files": files, "data": data} if files else {"json": data}
                with client.stream(
                    method,
                    self.base + path,
                    headers=headers,
                    auth=self.auth,
                    params=params,
                    **content_arguments,
                ) as response:
                    self.last_content_range = response.headers.get("Content-Range", "")
                    self.last_status = response.status_code
                    optional_statuses = (404,) if optional is True else (optional or ())
                    if response.status_code in optional_statuses:
                        return None
                    if response.status_code in (401, 403):
                        raise TicketProviderError(
                            "Ticket platform denied authentication or permission"
                        )
                    if not 200 <= response.status_code < 300:
                        if method == "POST" and (
                            300 <= response.status_code < 400
                            or response.status_code == 408
                            or response.status_code >= 500
                        ):
                            raise NetworkUncertain(
                                "Ticket creation is uncertain; check before retrying"
                            )
                        raise TicketProviderError(
                            f"Ticket platform request failed (HTTP {response.status_code})"
                        )
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() > self.deadline:
                            error = NetworkUncertain if method == "POST" else TicketProviderError
                            raise error("Ticket platform operation exceeded its time limit")
                        content.extend(chunk)
                        if len(content) > MAX_BYTES:
                            if method == "POST":
                                raise NetworkUncertain(
                                    "Ticket creation returned an oversized response"
                                )
                            raise TicketProviderError("Ticket platform response is too large")
                    try:
                        return json.loads(content) if content else {}
                    except (ValueError, RecursionError):
                        if method == "POST":
                            raise NetworkUncertain(
                                "Ticket creation returned an invalid response"
                            ) from None
                        raise TicketProviderError("Invalid ticket platform response") from None
        except httpx.TransportError:
            error = NetworkUncertain if method == "POST" else TicketProviderError
            raise error(
                "Ticket platform network failure; check publication status before retrying"
            ) from None

    def pages(self, path, params=None, key=None):
        rows = []
        for page in range(1, MAX_PAGES + 1):
            result = self.request(
                "GET", path, params={**(params or {}), "per_page": 100, "page": page}
            )
            items = result.get(key, []) if key else result
            if not isinstance(items, list):
                raise TicketProviderError("Invalid ticket platform list response")
            rows.extend(items)
            if len(items) < 100:
                return rows
        raise TicketProviderError("Too many ticket platform results; narrow the destination")

    def attach(self, project, issue, metadata, content):
        raise TicketProviderError("This connector cannot transfer ticket attachments")

    def attachment_policy(self, project):
        return {
            "enabled": self.connector.platform in {"gitlab", "jira", "glpi"},
            "max_bytes": 25 * 1024 * 1024,
        }

    def options(self, project, template_id="", issue_type=""):
        value = self._options(str(project), template_id, issue_type)
        for key in ("templates", "issue_types", "labels", "assignees", "fields"):
            value.setdefault(key, [])
        defaults = value.get("defaults", {})
        for name in ("labels", "assignees"):
            if name not in defaults:
                continue
            allowed = {item["id"] for item in value[name]}
            unavailable = [item for item in defaults[name] if item not in allowed]
            if unavailable:
                value.setdefault("unavailable_defaults", {})[name] = unavailable
                defaults[name] = [item for item in defaults[name] if item in allowed]
        if value.get("unavailable_defaults"):
            value["notice"] = (
                value.get("notice", "")
                + " Some template defaults are unavailable; review labels and assignees before publication"
            ).strip()
        value.setdefault("template_body", "")
        value.setdefault("format", "markdown")
        value["revision"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        return value

    def validate(self, project, payload):
        options = self.options(
            project, payload.get("template_id", ""), payload.get("issue_type", "")
        )
        if payload.get("options_revision") and payload["options_revision"] != options["revision"]:
            raise TicketProviderError("Ticket options changed; review the publication again")
        if not str(payload.get("title", "")).strip() or not render_body(payload, options).strip():
            raise TicketProviderError("Ticket title and description are required")
        fields = payload.get("fields", {})
        definitions = {f["id"]: f for f in options["fields"]}
        if set(fields) - set(definitions):
            raise TicketProviderError("Ticket contains fields not allowed by the destination")
        for identifier, definition in definitions.items():
            value = fields.get(identifier, definition.get("default", ""))
            if definition.get("read_only") and value != definition.get("default"):
                raise TicketProviderError("A ticket field is fixed by the destination template")
            if definition["required"] and (
                value is None or value == "" or value == [] or value is False
            ):
                raise TicketProviderError("Complete all required ticket fields")
            if value in (None, "", []):
                continue
            kind = definition["type"]
            if kind == "checkbox" and not isinstance(value, bool):
                raise TicketProviderError("Invalid ticket checkbox value")
            if kind == "multiselect" and not isinstance(value, list):
                raise TicketProviderError("Invalid ticket selection")
            if kind in ("select", "multiselect"):
                values = value if isinstance(value, list) else [value]
                if any(str(v) not in {o["id"] for o in definition["options"]} for v in values):
                    raise TicketProviderError("Invalid ticket selection")
            if kind in ("text", "textarea") and not isinstance(value, str):
                raise TicketProviderError("Invalid ticket field value")
        for name in ("labels", "assignees"):
            if set(map(str, payload.get(name, []))) - {v["id"] for v in options[name]}:
                raise TicketProviderError("Ticket selection is no longer available")
        return options

    def test(self):
        self.projects()

    def body(self, payload, reference):
        return render_body(payload, {}, reference)


class GitHubProvider(Provider):
    def __init__(self, connector):
        super().__init__(connector)
        if self.base != "https://api.github.com":
            raise TicketProviderError("GitHub publication requires api.github.com")
        from .sensitive_data import git_credentials

        if not connector.secret:
            raise TicketProviderError("Configure a dedicated ticket publication credential.")
        credential = decrypt(connector.secret)
        if credential in git_credentials():
            raise TicketProviderError(
                "Ticket publication must use a credential distinct from Git source access."
            )
        self.headers["Authorization"] = "Bearer " + credential
        self.headers["Accept"] = "application/vnd.github+json"
        self.headers["X-GitHub-Api-Version"] = "2022-11-28"

    def repo(self, project):
        try:
            github.validate_repository(str(project))
        except ValueError:
            raise TicketProviderError("Invalid GitHub repository") from None
        return "/repos/" + str(project)

    def projects(self):
        return [
            choice(r["full_name"], r["full_name"])
            for r in self.pages("/user/repos")
            if r.get("has_issues", True) and not r.get("archived")
        ]

    def contents(self, project, path):
        return self.request(
            "GET", self.repo(project) + "/contents/" + quote(path, safe="/"), optional=True
        )

    def _options(self, project, template_id, issue_type):
        path = self.repo(project)
        template_project = project
        entries = self.contents(template_project, ".github/ISSUE_TEMPLATE") or []
        if not isinstance(entries, list):
            raise TicketProviderError("Invalid GitHub template directory")
        if not any(
            x.get("type") == "file" and x.get("name", "").lower().endswith((".md", ".yml", ".yaml"))
            for x in entries
        ):
            shared_project = project.split("/")[0] + "/.github"
            if shared_project != project:
                shared = self.request("GET", self.repo(shared_project), optional=True)
                if shared and shared.get("private") is False:
                    entries = self.contents(shared_project, ".github/ISSUE_TEMPLATE") or []
                    template_project = shared_project
            if not isinstance(entries, list):
                raise TicketProviderError("Invalid GitHub template directory")
        templates = [
            choice(x["path"], x["name"])
            for x in entries
            if x.get("type") == "file"
            and x["name"].lower().endswith((".md", ".yml", ".yaml"))
            and x["name"] != "config.yml"
        ]
        result = {
            "templates": templates,
            "template_source": template_project,
            "labels": [choice(x["name"], x["name"]) for x in self.pages(path + "/labels")],
            "assignees": [choice(x["login"], x["login"]) for x in self.pages(path + "/assignees")],
            "fields": [],
        }
        if not template_id:
            return result
        if template_id not in {t["id"] for t in templates}:
            raise TicketProviderError("Ticket template is no longer available")
        content = self.contents(template_project, template_id)
        try:
            text = base64.b64decode(content["content"], validate=False).decode()
        except (KeyError, ValueError, UnicodeError, TypeError):
            raise TicketProviderError("Invalid GitHub template content") from None
        if template_id.endswith(".md"):
            if text.startswith("---\n"):
                parts = text.split("---", 2)
                metadata = structured_yaml(parts[1])
                text = parts[2].lstrip() if len(parts) == 3 else ""
                result["defaults"] = template_defaults(metadata)
            result["template_body"] = text
            return result
        form = structured_yaml(text)
        result["defaults"] = template_defaults(form)
        sections = []
        for index, item in enumerate(form.get("body", [])):
            kind, attrs = item.get("type"), item.get("attributes", {})
            if kind == "markdown":
                sections.append(str(attrs.get("value", "")))
                continue
            identifier = str(item.get("id", f"field-{index}"))
            required = item.get("validations", {}).get("required", False)
            label = str(attrs.get("label", identifier))
            if kind == "checkboxes":
                for number, option in enumerate(attrs.get("options", [])):
                    result["fields"].append(
                        field(
                            f"{identifier}-{number}",
                            option["label"],
                            "checkbox",
                            option.get("required", False),
                            default=False,
                        )
                    )
            elif kind in ("input", "textarea", "dropdown"):
                options = [choice(x, x) for x in attrs.get("options", [])]
                field_type = {
                    "input": "text",
                    "textarea": "textarea",
                    "dropdown": "multiselect" if attrs.get("multiple") else "select",
                }[kind]
                default = attrs.get("value", "")
                if kind == "dropdown" and "default" in attrs:
                    indices = (
                        attrs["default"]
                        if isinstance(attrs["default"], list)
                        else [attrs["default"]]
                    )
                    selected = [
                        str(attrs["options"][i])
                        for i in indices
                        if isinstance(i, int) and 0 <= i < len(options)
                    ]
                    default = (
                        selected if attrs.get("multiple") else (selected[0] if selected else "")
                    )
                result["fields"].append(
                    field(
                        identifier,
                        label,
                        field_type,
                        required,
                        options,
                        default,
                        attrs.get("description", ""),
                    )
                )
            else:
                raise TicketProviderError("Unsupported GitHub issue form field")
        result["template_body"] = "\n\n".join(sections)
        result["render_fields"] = True
        return result

    def create(self, project, payload, reference):
        options = self.validate(project, payload)
        body = render_body(payload, options, reference)
        result = self.request(
            "POST",
            self.repo(project) + "/issues",
            data={
                "title": payload["title"],
                "body": body,
                "labels": payload.get("labels", []),
                "assignees": payload.get("assignees", []),
            },
        )
        return self.external(result)

    def external(self, value):
        try:
            return dict(
                external_id=positive_id(value["id"]),
                external_key=positive_id(value["number"]),
                url=self.external_url(value["html_url"], github_url=True),
            )
        except (KeyError, TypeError):
            raise NetworkUncertain("Ticket creation response is incomplete") from None

    def find(self, project, reference):
        for item in self.pages(
            self.repo(project) + "/issues", {"state": "all", "sort": "created", "direction": "desc"}
        ):
            if "pull_request" not in item and has_reference(item.get("body") or "", reference):
                return self.external(item)
        return None


class GitLabProvider(Provider):
    def __init__(self, connector):
        super().__init__(connector)
        self.headers["PRIVATE-TOKEN"] = decrypt(connector.secret)

    def project(self, project):
        return "/api/v4/projects/" + quote(str(project), safe="")

    def projects(self):
        return [
            choice(x["id"], x.get("path_with_namespace", x["name"]))
            for x in self.pages("/api/v4/projects", {"membership": "true", "archived": "false"})
        ]

    def _options(self, project, template_id, issue_type):
        path = self.project(project)
        templates = self.pages(path + "/templates/issues")
        result = {
            "templates": [choice(x["key"], x["name"]) for x in templates],
            "labels": [choice(x["name"], x["name"]) for x in self.pages(path + "/labels")],
            "assignees": [
                choice(x["id"], x.get("name", x.get("username", "")))
                for x in self.pages(path + "/members/all")
            ],
        }
        if template_id:
            if template_id not in {t["id"] for t in result["templates"]}:
                raise TicketProviderError("Ticket template is no longer available")
            result["template_body"] = self.request(
                "GET", path + "/templates/issues/" + quote(template_id, safe="")
            )["content"]
        return result

    def external(self, value):
        try:
            return dict(
                external_id=positive_id(value["id"]),
                external_key=positive_id(value["iid"]),
                url=self.external_url(value["web_url"]),
            )
        except (KeyError, TypeError):
            raise NetworkUncertain("Ticket creation response is incomplete") from None

    def create(self, project, payload, reference):
        self.validate(project, payload)
        return self.external(
            self.request(
                "POST",
                self.project(project) + "/issues",
                data={
                    "title": payload["title"],
                    "description": self.body(payload, reference),
                    "labels": ",".join(payload.get("labels", [])),
                    "assignee_ids": payload.get("assignees", []),
                },
            )
        )

    def attach(self, project, issue, metadata, content):
        result = self.request(
            "POST",
            self.project(project) + "/uploads",
            files={"file": (metadata["name"], content, metadata["mime"])},
        )
        path = result.get("url", "") if isinstance(result, dict) else ""
        # Never reflect arbitrary remote Markdown, URLs or instructions into a
        # ticket. Native GitLab upload links are relative to the current project.
        if not re.fullmatch(r"/uploads/[a-zA-Z0-9_-]+/[^\s?#()\\]+", path):
            raise NetworkUncertain("The attachment upload returned an unsafe link")
        name = metadata["name"].replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        note = self.request(
            "POST",
            self.project(project) + "/issues/" + quote(str(issue), safe="") + "/notes",
            data={"body": "[" + name + "](" + path + ")"},
        )
        return {"id": str(result.get("id", note.get("id", "")))}

    def find(self, project, reference):
        for item in self.pages(
            self.project(project) + "/issues",
            {"search": reference, "in": "description", "scope": "all"},
        ):
            if has_reference(item.get("description") or "", reference):
                return self.external(item)
        return None


class JiraProvider(Provider):
    def __init__(self, connector):
        super().__init__(connector)
        self.auth = httpx.BasicAuth(connector.username, decrypt(connector.secret))

    def jira_pages(self, path, key="values", params=None):
        rows = []
        for offset in range(0, 1000, 100):
            data = self.request(
                "GET",
                "/rest/api/3" + path,
                params={**(params or {}), "startAt": offset, "maxResults": 100},
            )
            items = data.get(key, [])
            rows.extend(items)
            if data.get("isLast") or len(items) < 100:
                return rows
        raise TicketProviderError("Too many Jira results; narrow the destination")

    def projects(self):
        return [
            choice(x["id"], x.get("name", x["key"])) for x in self.jira_pages("/project/search")
        ]

    def _options(self, project, template_id, issue_type):
        project_path = quote(project, safe="")
        types = self.jira_pages(f"/issue/createmeta/{project_path}/issuetypes", "issueTypes")
        result = {
            "issue_types": [choice(x["id"], x["name"]) for x in types],
            "format": "adf",
            "fields": [],
            "labels": [],
            "assignees": [],
        }
        if not issue_type:
            return result
        if issue_type not in {x["id"] for x in result["issue_types"]}:
            raise TicketProviderError("Ticket issue type is no longer available")
        metadata = self.jira_pages(
            f"/issue/createmeta/{project_path}/issuetypes/{quote(issue_type, safe='')}", "fields"
        )
        for item in metadata:
            identifier = item.get("fieldId", item.get("key"))
            if identifier in ("summary", "description", "project", "issuetype"):
                continue
            schema = item.get("schema", {})
            if identifier == "labels":
                # Jira labels are open strings, but only discovered values are offered in this UI.
                result["labels"] = [choice(x, x) for x in self.jira_pages("/label")]
                continue
            if identifier == "assignee":
                people = self.request(
                    "GET",
                    "/rest/api/3/user/assignable/search",
                    params={"project": project, "maxResults": 100},
                )
                result["assignees"] = [
                    choice(x["accountId"], x.get("displayName", x["accountId"])) for x in people
                ]
                if item.get("required"):
                    result["fields"].append(
                        field("assignee", item["name"], "select", True, result["assignees"])
                    )
                continue
            allowed = item.get("allowedValues", [])
            choices = [
                choice(x.get("id", x.get("value")), x.get("name", x.get("value", x.get("id", ""))))
                for x in allowed
                if isinstance(x, dict)
            ]
            if choices:
                kind = "multiselect" if schema.get("type") == "array" else "select"
            elif schema.get("type") == "string":
                kind = "textarea" if "textarea" in schema.get("custom", "") else "text"
            elif item.get("required") and not item.get("hasDefaultValue"):
                raise TicketProviderError(
                    "Jira requires a field type not supported by this connector"
                )
            else:
                continue
            result["fields"].append(
                field(
                    identifier,
                    item["name"],
                    kind,
                    item.get("required", False),
                    choices,
                    description=item.get("description", ""),
                )
            )
        return result

    def external(self, value):
        try:
            if not isinstance(value["key"], str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_]*-[1-9][0-9]*", value["key"]
            ):
                raise NetworkUncertain("Ticket creation response contains an invalid key")
            return dict(
                external_id=positive_id(value["id"]),
                external_key=value["key"],
                url=self.base + "/browse/" + quote(value["key"], safe=""),
            )
        except (KeyError, TypeError):
            raise NetworkUncertain("Ticket creation response is incomplete") from None

    def attach(self, project, issue, metadata, content):
        settings = self.request("GET", "/rest/api/3/attachment/meta")
        if not settings.get("enabled") or metadata["size"] > int(settings.get("uploadLimit", 0)):
            raise TicketProviderError(
                "Attachments are disabled or the selected file exceeds the Jira limit"
            )
        result = self.request(
            "POST",
            "/rest/api/3/issue/" + quote(str(issue), safe="") + "/attachments",
            files={"file": (metadata["name"], content, metadata["mime"])},
            extra_headers={"X-Atlassian-Token": "no-check"},
        )
        if not isinstance(result, list) or len(result) != 1:
            raise NetworkUncertain("The attachment response is incomplete")
        return {"id": positive_id(result[0].get("id"))}

    def attachment_policy(self, project):
        settings = self.request("GET", "/rest/api/3/attachment/meta")
        permissions = self.request(
            "GET",
            "/rest/api/3/mypermissions",
            params={"projectId": project, "permissions": "CREATE_ATTACHMENTS"},
        )
        allowed = (
            permissions.get("permissions", {}).get("CREATE_ATTACHMENTS", {}).get("havePermission")
            is True
        )
        return {
            "enabled": settings.get("enabled") is True and allowed,
            "max_bytes": min(25 * 1024 * 1024, int(settings.get("uploadLimit", 0))),
        }

    def create(self, project, payload, reference):
        options = self.validate(project, payload)
        if not payload.get("issue_type"):
            raise TicketProviderError("Choose a Jira issue type")
        if len(payload.get("assignees", [])) > 1:
            raise TicketProviderError("Jira permits only one assignee")
        content = [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            for line in self.body(payload, reference).splitlines()
            if line
        ]
        fields = {
            "project": {"id": str(project)},
            "issuetype": {"id": payload["issue_type"]},
            "summary": payload["title"],
            "description": {"type": "doc", "version": 1, "content": content},
        }
        if payload.get("labels"):
            fields["labels"] = payload["labels"]
        if payload.get("assignees"):
            fields["assignee"] = {"accountId": payload["assignees"][0]}
        for definition in options["fields"]:
            value = payload.get("fields", {}).get(definition["id"])
            if value in (None, "", []):
                continue
            if definition["id"] == "assignee":
                value = {"accountId": value}
            elif definition["type"] == "select":
                value = {"id": value}
            elif definition["type"] == "multiselect":
                value = [{"id": x} for x in value]
            elif definition["type"] == "textarea":
                value = {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": value}]}
                    ],
                }
            fields[definition["id"]] = value
        return self.external(self.request("POST", "/rest/api/3/issue", data={"fields": fields}))

    def find(self, project, reference):
        if not re.fullmatch(r"[\w:.-]+", reference) or not re.fullmatch(r"[\w-]+", str(project)):
            raise TicketProviderError("Invalid publication reference")
        # Search indexing can lag: a missing result must not authorize an automatic POST retry.
        data = self.request(
            "GET",
            "/rest/api/3/search/jql",
            params={
                "jql": f'project = "{project}" AND text ~ "{reference}"',
                "fields": "description",
                "maxResults": 100,
            },
        )
        for item in data.get("issues", []):
            description = json.dumps(item.get("fields", {}).get("description", {}))
            if has_reference(description, reference):
                return self.external(item)
        return None


class GLPIProvider(Provider):
    def __init__(self, connector):
        super().__init__(connector)
        if connector.api_version not in ("v1", "1", "legacy"):
            raise TicketProviderError("GLPI connector supports the legacy v1 REST API only")
        if not self.base.endswith("/apirest.php"):
            self.base += "/apirest.php"
        if connector.app_token:
            self.headers["App-Token"] = decrypt(connector.app_token)
        self.login_secret = decrypt(connector.secret)
        self.session = False

    def start(self):
        if self.session:
            return
        if self.connector.username:
            self.auth = httpx.BasicAuth(self.connector.username, self.login_secret)
        else:
            self.headers["Authorization"] = "user_token " + self.login_secret
        value = self.request("GET", "/initSession")
        if not value.get("session_token"):
            raise TicketProviderError("GLPI did not provide an API session")
        self.auth = None
        self.headers.pop("Authorization", None)
        self.headers["Session-Token"] = value["session_token"]
        self.session = True

    def items(self, name, optional=False):
        self.start()
        value = self.request("GET", "/" + name, params={"range": "0-999"}, optional=optional)
        if value is None:
            return []
        if not isinstance(value, list) or len(value) >= 1000:
            raise TicketProviderError("GLPI list is invalid or too large")
        total = self.last_content_range.rsplit("/", 1)[-1]
        if (total.isdigit() and int(total) > len(value)) or (
            self.last_status == 206 and not total.isdigit()
        ):
            raise TicketProviderError("GLPI list is incomplete; narrow the destination")
        return value

    def projects(self):
        self.start()
        data = self.request("GET", "/getMyEntities", params={"is_recursive": "true"})
        return [choice(x["id"], x.get("name", x["id"])) for x in data.get("myentities", [])]

    def _options(self, project, template_id, issue_type):
        if str(project) not in {x["id"] for x in self.projects()}:
            raise TicketProviderError("GLPI entity is not accessible")
        categories = [
            x
            for x in self.items("ITILCategory")
            if str(x.get("entities_id", project)) == project
            or (str(x.get("entities_id")) == "0" and x.get("is_recursive"))
        ]
        # Automatic category/profile/entity rules still run on the server after this preflight.
        result = {
            "format": "html",
            "fields": [
                field(
                    "itilcategories_id",
                    "Category",
                    "select",
                    options=[choice(x["id"], x["name"]) for x in categories],
                )
            ],
            "notice": "GLPI legacy REST exposes selected template fields; automatic profile/entity rules and server-side validation remain authoritative",
        }
        templates = self.items("TicketTemplate", optional=(403, 404))
        result["templates"] = [
            choice(x["id"], x["name"])
            for x in templates
            if str(x.get("entities_id", project)) == project
            or (str(x.get("entities_id")) == "0" and x.get("is_recursive"))
        ]
        if template_id:
            if template_id not in {x["id"] for x in result["templates"]}:
                raise TicketProviderError("Ticket template is no longer available")
            self.template_options(result, project, template_id)
        return result

    def template_options(self, result, project, template_id):
        """Resolve search-option IDs using the destination's own field metadata."""
        prefix = "TicketTemplate/" + quote(template_id, safe="") + "/TicketTemplate"
        rules = {
            name: self.items(prefix + name + "Field")
            for name in ("Mandatory", "Predefined", "Hidden")
        }
        # Readonly fields were introduced in GLPI 11; absent endpoint means older legacy API.
        rules["Readonly"] = self.items(prefix + "ReadonlyField", optional=True)
        search = self.request("GET", "/listSearchOptions/Ticket")
        if not isinstance(search, dict):
            raise TicketProviderError("GLPI template field metadata is unavailable")
        aliases = {
            ("glpi_itilcategories", "completename"): "itilcategories_id",
            ("glpi_requesttypes", "name"): "requesttypes_id",
            ("glpi_entities", "completename"): "entities_id",
        }
        supported = {"name", "content", "type", "urgency", "impact", "priority"}
        mapping = {}
        for number, metadata in search.items():
            if not isinstance(metadata, dict):
                continue
            table, key = metadata.get("table"), metadata.get("field")
            identifier = (
                key if table == "glpi_tickets" and key in supported else aliases.get((table, key))
            )
            if identifier:
                mapping[str(number)] = (identifier, metadata.get("name", identifier))
        required, defaults, fixed = set(), {}, set()
        for kind, entries in rules.items():
            for row in entries:
                if str(row.get("tickettemplates_id", template_id)) != str(template_id):
                    raise TicketProviderError("GLPI returned rules for another template")
                target = mapping.get(str(row.get("num")))
                if not target:
                    raise TicketProviderError(
                        "GLPI template contains an unsupported field; use a supported template or the native ticket form"
                    )
                identifier = target[0]
                if kind == "Mandatory":
                    required.add(identifier)
                elif kind == "Predefined":
                    if identifier in defaults:
                        raise TicketProviderError(
                            "GLPI template contains unsupported multiple defaults"
                        )
                    defaults[identifier] = str(row.get("value", ""))
                else:
                    fixed.add(identifier)
        if fixed & {"name", "content"}:
            raise TicketProviderError(
                "GLPI template locks the ticket title or description; use the native ticket form"
            )
        if fixed - defaults.keys() - {"entities_id"}:
            raise TicketProviderError(
                "GLPI template hides a field without an accessible default; use the native ticket form"
            )
        if defaults.get("entities_id", str(project)) != str(project):
            raise TicketProviderError("GLPI template targets a different entity")
        definitions = {item["id"]: item for item in result["fields"]}
        involved = required | defaults.keys() | fixed
        configuration = {}
        if involved & {"urgency", "impact", "priority"}:
            configuration = self.request("GET", "/getGlpiConfig").get("cfg_glpi", {})
        for identifier in sorted(involved - {"name", "content", "entities_id"}):
            if identifier not in definitions:
                if identifier == "requesttypes_id":
                    options = [choice(x["id"], x["name"]) for x in self.items("RequestType")]
                elif identifier == "type":
                    options = [choice(1, "Incident"), choice(2, "Request")]
                elif identifier in ("urgency", "impact"):
                    mask = configuration.get(identifier + "_mask")
                    # GLPI stores configuration values as strings in its real REST response.
                    if isinstance(mask, str) and mask.isascii() and mask.isdecimal():
                        mask = int(mask)
                    if type(mask) is not int or not 0 <= mask <= 62:
                        raise TicketProviderError("GLPI template severity options are unavailable")
                    options = [choice(n, str(n)) for n in range(1, 6) if mask & (1 << n)]
                elif identifier == "priority":
                    session = self.request("GET", "/getFullSession").get("session", {})
                    rights = session.get("glpiactiveprofile", {}).get("ticket", 0)
                    if not isinstance(rights, int) or not rights & 65536:
                        raise TicketProviderError("GLPI profile cannot set the template priority")
                    options = [choice(n, str(n)) for n in range(1, 7)]
                else:
                    raise TicketProviderError("Unsupported GLPI template field")
                label = next(
                    (label for key, label in mapping.values() if key == identifier), identifier
                )
                definitions[identifier] = field(identifier, label, "select", options=options)
            definition = definitions[identifier]
            definition["required"] = identifier in required
            if identifier in defaults:
                definition["default"] = defaults[identifier]
                if defaults[identifier] not in {x["id"] for x in definition["options"]}:
                    raise TicketProviderError("GLPI template default is not an accessible option")
            if identifier in fixed:
                definition["read_only"] = True
        result["fields"] = list(definitions.values())
        result["defaults"] = {}
        if "name" in defaults:
            result["defaults"]["title"] = defaults["name"]
        if "content" in defaults:
            result["template_body"] = plain_html(defaults["content"])
            result["defaults"]["body"] = result["template_body"]
        result["template_required_fields"] = sorted(required)

    def external(self, identifier):
        identifier = positive_id(identifier)
        return dict(
            external_id=str(identifier),
            external_key=str(identifier),
            url=self.base.removesuffix("/apirest.php")
            + "/front/ticket.form.php?id="
            + quote(str(identifier), safe=""),
        )

    def create(self, project, payload, reference):
        options = self.validate(project, payload)
        values = {
            "name": payload["title"],
            "content": "<p>"
            + html.escape(self.body(payload, reference)).replace("\n", "<br>")
            + "</p>",
            "entities_id": int(project),
        }
        for definition in options["fields"]:
            value = payload.get("fields", {}).get(definition["id"], definition.get("default", ""))
            if definition["required"] and value == "0":
                raise TicketProviderError("Complete all required ticket fields")
            if value not in ("", None):
                values[definition["id"]] = int(value)
        if payload.get("template_id"):
            values["_tickettemplate"] = int(payload["template_id"])
        result = self.request("POST", "/Ticket", data={"input": values})
        if not isinstance(result, dict) or not result.get("id"):
            raise NetworkUncertain("GLPI ticket creation response is incomplete")
        return self.external(result["id"])

    def find(self, project, reference):
        for item in self.items("Ticket"):
            if str(item.get("entities_id")) == str(project) and has_reference(
                html.unescape(item.get("content", "")), reference
            ):
                return self.external(item["id"])
        return None

    def attach(self, project, issue, metadata, content):
        manifest = {
            "input": {
                "name": metadata["name"],
                "_filename": [metadata["name"]],
                "entities_id": int(project),
            }
        }
        result = self.request(
            "POST",
            "/Document",
            data={"uploadManifest": json.dumps(manifest)},
            files={"filename[0]": (metadata["name"], content, metadata["mime"])},
        )
        identifier = positive_id(result.get("id"))
        linked = self.request(
            "POST",
            "/Document_Item",
            data={
                "input": {
                    "documents_id": int(identifier),
                    "itemtype": "Ticket",
                    "items_id": int(issue),
                }
            },
        )
        if not isinstance(linked, dict) or not linked.get("id"):
            raise NetworkUncertain("The uploaded document link could not be confirmed")
        return {"id": identifier}


def provider_for(connector):
    adapter = {
        "github": GitHubProvider,
        "gitlab": GitLabProvider,
        "jira": JiraProvider,
        "glpi": GLPIProvider,
    }.get(connector.platform)
    if not adapter:
        raise TicketProviderError("Unsupported ticket platform")
    return adapter(connector)
