"""Read recorded proofs on demand, without rerunning agents or business queries."""

import re
import subprocess
from pathlib import PurePosixPath

from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from .models import ContextResourceVersion, Job, Request, RequestMessage, ResultVersion
from .sensitive_data import configured_secrets, redact


def code_excerpt(source, baseline):
    """Read the immutable blob, never rematerialize an active agent workspace."""
    from .git import mirror_path, run

    row = next((row for row in baseline if row.get("repository") == source.get("repository")), None)
    path, commit = source.get("path", ""), source.get("commit", "")
    parts = PurePosixPath(path).parts
    if (not row or row.get("sha") != commit or not re.fullmatch(r"[a-f0-9]{40}", commit)
            or not path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
            or "\\" in path or any(ord(c) < 32 for c in path)
            or any(part in {".ssh", ".aws", ".git", "id_rsa", "id_ed25519"} or part == ".env" for part in parts)):
        return "", "Source does not match the frozen Git references."
    try:
        mirror = mirror_path(row)
        mode = run("-C", mirror, "ls-tree", commit, "--", path, timeout=5).split(" ", 1)[0]
        if mode not in {"100644", "100755"}:
            return "", "The cited source file is unavailable."
        obj = commit + ":" + path
        if int(run("-C", mirror, "cat-file", "-s", obj, timeout=5)) > 4 * 1024 * 1024:
            return "", "The cited source file is too large to preview."
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(mirror), "cat-file", "blob", obj], capture_output=True, timeout=5, check=True)
        content = result.stdout.decode("utf-8")
        if "\x00" in content:
            raise ValueError("Binary source")
        lines = content.splitlines()
        start = int(source["line_start"]) if source.get("line_start") is not None else 1
        requested_end = int(source["line_end"]) if source.get("line_end") is not None else (start if source.get("line_start") else 12)
        end = min(requested_end, start + 99, len(lines))
        if start < 1 or start > end:
            return "", "The cited line range is unavailable."
        excerpt = "\n".join(lines[start-1:end])
        note = "" if source.get("line_start") else "Preview from the beginning of the cited file; no precise line range was recorded."
        if source.get("line_start") and (requested_end > end or len(excerpt) > 12000):
            note = "Only part of the cited range is shown."
        return excerpt[:12000], note
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return "", "The frozen source excerpt is unavailable."


def inline_git_sources(content, baseline):
    """Recognize explicit locations only; never infer lines from answer keywords."""
    location = r"L?(\d+)(?:\s*[-–]\s*L?(\d+))?"
    references = re.finditer(
        r"`([^`\n]+\.[A-Za-z0-9]{1,12})(?:(?::|#)" + location + r")?`", content
    )
    for index, match in enumerate(references):
        if index >= 40:
            break
        path, start, end = match.groups()
        ranges = [(start, end or start)] if start else []
        if not ranges:
            suffix = content[match.end():match.end()+300]
            external = re.match(r"\s*(?::|#)" + location, suffix)
            parenthesis = re.match(
                r"\s*\(\s*(?:lines?|lignes?)\s+(" + location
                + r"(?:\s*(?:,|et|and)\s*" + location + r"){0,5})\s*\)", suffix, re.I
            )
            if external:
                ranges = [(external[1], external[2] or external[1])]
            elif parenthesis:
                ranges = [(a, b or a) for a, b in re.findall(location, parenthesis[1])]
        if "/" not in path and not ranges:
            continue
        for row in baseline:
            relative = path.removeprefix(row["repository"] + "/")
            for first, last in ranges or [(None, None)]:
                yield {"repository":row["repository"], "commit":row["sha"], "path":relative,
                       "line_start":int(first) if first else None, "line_end":int(last) if last else None}


def collect(value, content, observations, frozen, evidence=None):
    from .environment_context import version_dict

    evidence = evidence or {}
    baseline = frozen.get("dossier", {}).get("baseline", []) or []
    sources = [source for claim in evidence.get("claims", []) for source in claim.get("sources", [])]
    checks = observations.get("database_checks", []) or evidence.get("database", {}).get("checks", [])
    web = observations.get("web_checks", []) or evidence.get("web_references", [])
    records = []
    seen = set()
    def add(record):
        if record["id"] not in seen:
            records.append(record)
            seen.add(record["id"])

    for index, check in enumerate(checks[:100]):
        if isinstance(check, dict) and isinstance(check.get("query_id"), str) and isinstance(check.get("sql"), str):
            add({"kind":"sql", "id":check["query_id"], "number":index+1, **{key:check[key] for key in ("sql", "status", "checked_at", "row_count", "truncated") if key in check}})
    for receipt in web[:30]:
        if not isinstance(receipt, dict) or not isinstance(receipt.get("reference_id"), str):
            continue
        from .official_sources import public_reference_url
        try:
            url = public_reference_url(receipt.get("url", ""))
        except ValueError:
            continue
        citations = [s for s in sources if s.get("kind") == "web" and s.get("reference_id") == receipt["reference_id"]]
        quotes = [s.get("excerpt", "") for s in citations]
        body = receipt.get("text", "") if isinstance(receipt.get("text", ""), str) else ""
        exact = [quote for quote in quotes if quote and quote in body]
        add({"kind":"web", "id":receipt["reference_id"], "title":receipt.get("title") or url, "url":url,
             "excerpt":"\n\n".join(exact)[:12000] if exact else body[:6000], "checked_at":receipt.get("consulted_at", ""),
             "note":"" if exact else "Preview of the recorded page; no precise quoted passage was recorded.",
             "applicability":[{key:s[key] for key in ("applicability_notes", "effective_date", "version", "jurisdiction", "scope") if s.get(key)} for s in citations]})

    git_sources = [source for source in sources if source.get("kind") == "git"]
    # Inline citations can be resolved against this turn's frozen repositories.
    # They stay cited sources, not independently verified interpretations.
    git_sources.extend(inline_git_sources(content, baseline))
    precise_files = set()
    for source in sorted(git_sources, key=lambda item: not item.get("line_start"))[:20]:
        file_key = tuple(source.get(k) for k in ("repository", "commit", "path"))
        if not source.get("line_start") and file_key in precise_files:
            continue
        key = "git:" + ":".join(str(source.get(k) or "") for k in ("repository", "commit", "path", "line_start", "line_end"))
        if key in seen:
            continue
        excerpt, note = code_excerpt(source, baseline)
        # Do not add guesses for another repository when only an unqualified path was cited.
        if not excerpt and source not in sources:
            continue
        preview_start = source.get("line_start") or 1
        if excerpt and source.get("line_start"):
            precise_files.add(file_key)
        add({"kind":"git", "id":key, "title":source.get("path", ""), "repository":source.get("repository", ""),
             "commit":source.get("commit", ""), "line_start":source.get("line_start"), "line_end":source.get("line_end"),
             "preview_line_start":preview_start if excerpt else None,
             "preview_line_end":preview_start + len(excerpt.split("\n")) - 1 if excerpt else None,
             "excerpt":excerpt, "note":note})
    used = {item if isinstance(item, str) else item.get("version_id")
            for item in observations.get("context_usage", [])
            if isinstance(item, str) or isinstance(item, dict) and item.get("status") == "observed"}
    for entry in frozen.get("resources", []):
        if entry.get("version_id") not in used:
            continue
        record = {"kind":"document", "id":entry["version_id"], "title":entry.get("filename") or entry.get("name", ""),
                  "version":entry.get("version"), "excerpt":"", "note":"The recorded document excerpt is unavailable."}
        version = ContextResourceVersion.objects.select_related("resource").filter(pk=entry["version_id"], sha256=entry.get("sha256")).first()
        if version:
            record["title"] = version.filename
            if version.resource.environment_id:
                record["url"] = f"/api/environments/{version.resource.environment_id}/context/resources/{version.resource_id}/versions/{version.pk}/download"
            try:
                preview = version_dict(version, version.resource, preview=True)
                record["excerpt"] = preview.get("preview") or ""
                if record["excerpt"]:
                    record["note"] = "Preview from the retained document; the exact passage used was not recorded."
            except (OSError, ValueError, HttpError):
                record.pop("url", None)
        add(record)
    from .environment_context import TEXT_EXTENSIONS
    from .file_validation import attachment_path

    frozen_attachments = {str(item["id"]) for item in frozen.get("dossier", {}).get("attachments", [])}
    for attachment in value.attachments.filter(pk__in=frozen_attachments):
        if f"`{attachment.name}`" not in content:
            continue
        record = {"kind":"document", "id":str(attachment.pk), "title":attachment.name, "excerpt":"",
                  "note":"Cited document; a precise reading passage was not recorded."}
        try:
            path = attachment_path(attachment)
            record["url"] = f"/api/{'questions' if value.workflow == 'question' else 'requests'}/{value.pk}/attachments/{attachment.pk}"
            if path.suffix.lower() in TEXT_EXTENSIONS:
                with path.open("rb") as stream:
                    record["excerpt"] = stream.read(16000).decode("utf-8", errors="replace")[:4000]
        except (OSError, ValueError, HttpError):
            record.pop("url", None)
        add(record)
    return {"sources":redact(records, configured_secrets())}


def message_sources(analysis_id, message_id):
    value = get_object_or_404(Request, pk=analysis_id, deleted_at__isnull=True)
    message = get_object_or_404(RequestMessage, pk=message_id, request=value, role="assistant")
    job = Job.objects.filter(kind="discussion", target=str(value.pk), payload__revision=message.data.get("revision"),
                             payload__session_pk=message.data.get("session_pk")).order_by("-id").first()
    frozen = job.payload.get("snapshot", {}) if job else {}
    return collect(value, message.content, message.data.get("observations", {}), frozen)


def version_records(version):
    """Resolve only this immutable result's references, also for saved report exports."""
    frozen = {**version.context_snapshot, "dossier":{**version.context_snapshot.get("dossier", {})}}
    frozen["dossier"].setdefault("baseline", version.baseline)
    evidence = {**version.evidence}
    # Older consolidated answers can have file citations without structured claims.
    baseline = frozen["dossier"]["baseline"]
    references = []
    cited = {(source.get("repository"), source.get("path"))
             for claim in evidence.get("claims", []) for source in claim.get("sources", [])
             if source.get("kind") == "git"}
    for reference in version.explanation.get("references", []):
        if (reference.get("repository"), reference.get("path")) in cited:
            continue
        row = next((row for row in baseline if row.get("repository") == reference.get("repository")), None)
        if row:
            references.append({"kind":"git", "repository":row["repository"], "commit":row["sha"], "path":reference["path"]})
    evidence["claims"] = [*evidence.get("claims", []), {"sources":references}]
    content = "\n".join(value for value in version.explanation.values() if isinstance(value, str))
    return collect(version.request, content, {"context_usage":version.context_usage}, frozen, evidence)


def version_sources(analysis_id, number):
    version = get_object_or_404(ResultVersion.objects.select_related("request"), request_id=analysis_id,
                                request__deleted_at__isnull=True, number=number)
    return version_records(version)
