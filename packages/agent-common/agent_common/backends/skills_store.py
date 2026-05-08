"""Read-only backend serving three-tier resolved skills at /skills/{name}/..."""

from __future__ import annotations

import logging
import re

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import create_file_data

from agent_common.core.skill_frontmatter import build_skill_content
from agent_common.models.skill import ResolvedSkill

logger = logging.getLogger(__name__)

_READ_ONLY_MSG = "/skills/ is read-only. Use create_skill_md or update_skill_md to modify skills."


class SkillsStoreBackend(BackendProtocol):
    """Read-only backend serving merged skills at /skills/{name}/...

    Resolution order (applied upstream by skills_resolver):
      personal > group > standard.

    Built once per agent invocation with pre-resolved skills.
    """

    def __init__(self, merged_skills: dict[str, ResolvedSkill]):
        self._skills = merged_skills

    # ---- read operations ----

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        name, rel = self._parse_path(file_path)
        if not name:
            return ReadResult(error=f"Invalid path: {file_path}")

        skill = self._skills.get(name)
        if not skill:
            return ReadResult(error=f"Skill not found: {name}")

        if rel == "SKILL.md":
            content = build_skill_content(
                name=skill.name,
                description=skill.description,
                body=skill.body,
            )
        else:
            # Look for bundled file
            matched = next((f for f in skill.files if f.path == rel), None)
            if not matched:
                return ReadResult(error=f"File not found: {file_path}")
            content = matched.content

        # Apply offset/limit (line-based)
        lines = content.splitlines(keepends=True)
        sliced = lines[offset : offset + limit]
        return ReadResult(file_data=create_file_data("".join(sliced)))

    async def als(self, path: str) -> LsResult:
        normalized = path.rstrip("/") + "/"

        if normalized == "/skills/" or normalized == "/":
            entries = [FileInfo(path=f"{name}/", is_dir=True) for name in sorted(self._skills)]
            return LsResult(entries=entries)

        # /skills/{name}/ — list files in a skill
        name, _ = self._parse_path(path)
        if name and name in self._skills:
            skill = self._skills[name]
            entries: list[FileInfo] = [FileInfo(path="SKILL.md")]
            for f in skill.files:
                entries.append(FileInfo(path=f.path))
            return LsResult(entries=entries)

        return LsResult(error=f"Directory not found: {path}")

    async def agrep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        regex = re.compile(pattern, re.IGNORECASE)
        matches: list[GrepMatch] = []

        for name, skill in self._skills.items():
            content = build_skill_content(name=skill.name, description=skill.description, body=skill.body)
            for i, line in enumerate(content.splitlines()):
                if regex.search(line):
                    matches.append(
                        GrepMatch(
                            path=f"/skills/{name}/SKILL.md",
                            line=i + 1,
                            text=line,
                        )
                    )

        return GrepResult(matches=matches)

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        entries: list[FileInfo] = []
        for name, skill in self._skills.items():
            skill_path = f"/skills/{name}/SKILL.md"
            if re.search(pattern.replace("*", ".*").replace("?", "."), skill_path):
                entries.append(FileInfo(path=skill_path))
            for f in skill.files:
                fpath = f"/skills/{name}/{f.path}"
                if re.search(pattern.replace("*", ".*").replace("?", "."), fpath):
                    entries.append(FileInfo(path=fpath))
        return GlobResult(matches=entries)

    # ---- write operations (blocked) ----

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_READ_ONLY_MSG)

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return EditResult(error=_READ_ONLY_MSG)

    # ---- sync stubs (required by protocol, delegate to async) ----

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        raise NotImplementedError("Use aread()")

    def ls(self, path: str) -> LsResult:
        raise NotImplementedError("Use als()")

    def write(self, file_path: str, content: str) -> WriteResult:
        raise NotImplementedError("Use awrite()")

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        raise NotImplementedError("Use aedit()")

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        raise NotImplementedError("Use agrep()")

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        raise NotImplementedError("Use aglob()")

    # ---- helpers ----

    @staticmethod
    def _parse_path(path: str) -> tuple[str | None, str]:
        """Parse /skills/{name}/{rest} into (name, rest).

        Returns (None, "") if path doesn't match expected pattern.
        """
        cleaned = path.strip("/")
        # Remove "skills/" prefix if present
        if cleaned.startswith("skills/"):
            cleaned = cleaned[len("skills/") :]
        elif cleaned == "skills":
            return (None, "")

        parts = cleaned.split("/", 1)
        name = parts[0]
        rest = parts[1] if len(parts) > 1 else "SKILL.md"
        return (name, rest)
