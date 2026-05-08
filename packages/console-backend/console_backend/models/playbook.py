"""Pydantic models for the Playbook API."""

from pydantic import BaseModel, Field


class PlaybookContent(BaseModel):
    """AGENTS.md content for an agent."""

    agent_name: str
    scope: str = Field(description="'personal' or 'group'")
    content: str | None = Field(default=None, description="Markdown content of the AGENTS.md file")
    group_id: str | None = Field(default=None, description="Group ID (present for group scope)")
    group_name: str | None = Field(default=None, description="Group display name (present for group scope)")


class PlaybookUpdate(BaseModel):
    """Request body for updating AGENTS.md."""

    content: str = Field(description="Full Markdown content to write")


class SkillSummary(BaseModel):
    """Summary of a skill file (for listing)."""

    name: str = Field(description="Skill identifier (lowercase, hyphens, per SKILL.md spec)")
    title: str = Field(description="Skill name from frontmatter (or first heading for legacy)")
    description: str = Field(
        default="", description="Description from frontmatter (what the skill does and when to use it)"
    )
    scope: str = Field(description="'personal' or 'group'")
    group_id: str | None = Field(default=None, description="Group ID (present for group scope)")
    group_name: str | None = Field(default=None, description="Group display name (present for group scope)")


class SkillDetail(BaseModel):
    """Full skill file content."""

    name: str
    scope: str
    content: str = Field(description="Full SKILL.md content (frontmatter + body)")


class SkillCreate(BaseModel):
    """Request body for creating a new skill."""

    name: str = Field(description="Skill identifier (lowercase letters, numbers, hyphens only, per SKILL.md spec)")
    description: str = Field(default="", description="What the skill does and when to use it (shown in skill index)")
    content: str = Field(description="Skill instructions body (Markdown). Frontmatter is generated automatically.")


class SkillUpdate(BaseModel):
    """Request body for updating a skill."""

    content: str = Field(description="Full Markdown content to write")


class PlaybookListResponse(BaseModel):
    """Response for listing playbooks."""

    personal: PlaybookContent | None = None
    groups: list[PlaybookContent] = Field(default_factory=list, description="Playbooks from all user groups")


class SkillListResponse(BaseModel):
    """Response for listing skills."""

    items: list[SkillSummary] = Field(default_factory=list)
