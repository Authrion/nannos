"""Skill definition models for agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkillFile:
    """A file bundled with a standard skill."""

    path: str
    content: str


@dataclass
class SkillDefinition:
    """A standard (immutable) skill bundled with a sub-agent config version."""

    name: str
    description: str
    body: str
    files: list[SkillFile] = field(default_factory=list)


@dataclass
class ResolvedSkill:
    """A skill after three-tier resolution (personal > group > standard)."""

    name: str
    description: str
    body: str
    scope: str  # "personal", "group", or "standard"
    files: list[SkillFile] = field(default_factory=list)
    overrides: str | None = None  # scope that this skill overrides (e.g., "standard")
