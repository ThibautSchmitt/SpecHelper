"""Read-only, per-invocation skill files with kernel-observed lazy-load auditing."""

import copy
import hashlib
import re
import tempfile
from pathlib import Path

from runtime.context_resources import ResourceReads

CAPABILITIES = {
    "read_sources",
    "read_attachments",
    "read_database",
    "structured_output",
    "read_web",
}


class SkillResources:
    """Materialize frozen procedures privately; expose only exact files under /skills.

    The caller supplies its private invocation directory and closes this context
    after the sandbox exits. No shared parent or directory containing credentials
    is mounted. Observed reads establish loading, never comprehension or accuracy.
    """

    def __init__(self, definitions, directory, agent, has_database=False, has_web=False):
        self.definitions = copy.deepcopy(definitions)
        self.directory = Path(directory)
        self.agent = agent
        self.capabilities = CAPABILITIES - ({"read_database"} if not has_database else set())
        if not has_web:
            self.capabilities.discard("read_web")
        self.temporary = None
        self.resources = []
        self.mounts = ["--dir", "/skills"]
        self.reads = None
        self.observation = None
        self.versions = {}

    def __enter__(self):
        if not isinstance(self.definitions, list) or len(self.definitions) > 100:
            raise ValueError("Invalid frozen skill library")
        self.temporary = tempfile.TemporaryDirectory(prefix="skills-", dir=self.directory)
        root = Path(self.temporary.name)
        try:
            for value in self.definitions:
                if not isinstance(value, dict):
                    raise ValueError("Invalid frozen skill")
                slug = value.get("slug", "")
                version = value.get("version")
                text = value.get("instructions", "")
                if (
                    not isinstance(slug, str)
                    or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
                    or len(slug) > 50
                    or type(version) is not int
                    or version < 1
                    or not isinstance(text, str)
                    or not text.strip()
                    or len(text) > 12000
                    or "\x00" in text
                    or not value.get("enabled", True)
                    or value.get("deleted", False)
                    or (value.get("compatibility") and self.agent not in value["compatibility"])
                    or not set(value.get("required_capabilities", [])) <= self.capabilities
                    or slug in self.versions
                ):
                    raise ValueError("Invalid or non-applicable frozen skill")
                # The content is declarative instruction, never executed by this helper.
                checks = value.get("expected_checks", [])
                objective = value.get("objective", "")
                name = value.get("name", slug)
                if (
                    not isinstance(name, str)
                    or len(name) > 100
                    or not isinstance(objective, str)
                    or len(objective) > 4000
                    or not isinstance(checks, list)
                    or len(checks) > 20
                    or any(not isinstance(check, str) or len(check) > 1000 for check in checks)
                ):
                    raise ValueError("Invalid frozen skill metadata")
                document = f"# {name} (v{version})\n\n{objective}\n\n{text}\n"
                if checks:
                    document += (
                        "\nExpected checks:\n" + "\n".join("- " + check for check in checks) + "\n"
                    )
                encoded = document.encode()
                source = root / (slug + ".md")
                source.write_bytes(encoded)
                # The parent directory stays private; the exact bind-mounted file
                # must be readable by the sandbox's unprivileged uid 10001.
                source.chmod(0o444)
                identifier = f"{slug}@{version}"
                relative = f"{slug}/v{version}.md"
                self.resources.append((identifier, source, relative))
                self.versions[slug] = {
                    "slug": slug,
                    "version": version,
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                }
                self.mounts += [
                    "--dir",
                    "/skills/" + slug,
                    "--ro-bind",
                    str(source),
                    "/skills/" + relative,
                ]
            self.reads = ResourceReads(self.resources)
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def finish(self):
        if self.observation is None:
            value = (
                self.reads.finish()
                if self.reads
                else {"context_audit": "unavailable", "context_usage": []}
            )
            used = set(value["context_usage"]) if value["context_audit"] == "observed" else set()
            self.observation = {
                "loaded_skills": [
                    copy.deepcopy(self.versions[slug])
                    for slug in sorted(self.versions)
                    if f"{slug}@{self.versions[slug]['version']}" in used
                ],
                "skills_audit": value["context_audit"],
            }
        return copy.deepcopy(self.observation)

    def __exit__(self, *args):
        if self.reads:
            self.reads.close()
        if self.temporary:
            self.temporary.cleanup()
