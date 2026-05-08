"""Playbook management API endpoints.

Provides CRUD operations for AGENTS.md playbooks and skill files.
Reads/writes directly to the LangGraph store table in the docstore database.
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from console_backend.db.session import DbSession
from console_backend.dependencies import require_auth
from console_backend.models.playbook import (
    PlaybookContent,
    PlaybookListResponse,
    PlaybookUpdate,
    SkillCreate,
    SkillDetail,
    SkillListResponse,
    SkillSummary,
    SkillUpdate,
)
from console_backend.models.user import User
from console_backend.services.playbook_service import PlaybookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])


def _build_skill_content(name: str, description: str, body: str) -> str:
    """Build SKILL.md content with YAML frontmatter.

    Follows the Agent Skills spec (agentskills.io/specification).
    """
    lines = ["---", f"name: {name}"]
    if description:
        lines.append(f"description: {description}")
    lines.append("---")
    lines.append("")
    if body:
        lines.append(body)
    content = "\n".join(lines)
    if not content.endswith("\n"):
        content += "\n"
    return content


def get_playbook_service(request: Request) -> PlaybookService:
    """Get the playbook service from app state."""
    service: PlaybookService = request.app.state.playbook_service
    if not service.is_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Playbook service is not configured (docstore connection unavailable)",
        )
    return service


async def _get_user_group_context(
    request: Request, db: Any, user: User, group_id: str | None = None
) -> list[dict[str, Any]]:
    """Get the user's group memberships.

    Returns list of dicts with 'id', 'name', 'group_role'.
    """
    user_group_service = request.app.state.user_group_service
    return await user_group_service.get_user_group_memberships(db, user.id)


def _resolve_group(memberships: list[dict[str, Any]], group_id: str | None) -> tuple[str | None, str | None]:
    """Resolve which group to use and the user's role in it.

    If group_id is provided, validates the user is a member.
    If not provided, uses the first group (primary).
    Returns (group_id, group_role).
    """
    if not memberships:
        return None, None

    if group_id:
        for m in memberships:
            if str(m["id"]) == group_id:
                return str(m["id"]), m["group_role"]
        return None, None  # User is not a member of requested group

    # Default to first group
    primary = memberships[0]
    return str(primary["id"]), primary["group_role"]


def _validate_skill_name(name: str) -> None:
    """Validate skill name per the SKILL.md spec (agentskills.io/specification).

    Rules:
    - 1-64 characters
    - Lowercase alphanumeric + hyphens only
    - Must not start or end with a hyphen
    - Must not contain consecutive hyphens (--)
    """
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skill name is required",
        )
    if len(name) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skill name must be at most 64 characters",
        )
    if "--" in name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skill name must not contain consecutive hyphens (--)",
        )
    if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skill name must contain only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen",
        )


# --- AGENTS.md Endpoints ---


@router.get("/agents/{agent_name}", response_model=PlaybookListResponse)
async def get_playbook(
    agent_name: str,
    request: Request,
    db: DbSession,
    current_user: User = Depends(require_auth),
) -> PlaybookListResponse:
    """Get AGENTS.md content for an agent (personal + all user groups)."""
    service = get_playbook_service(request)
    memberships = await _get_user_group_context(request, db, current_user)

    personal_content = await service.get_agents_md(
        user_id=current_user.id,
        agent_name=agent_name,
        scope="personal",
    )

    group_playbooks: list[PlaybookContent] = []
    for m in memberships:
        gid = str(m["id"])
        group_content = await service.get_agents_md(
            user_id=current_user.id,
            agent_name=agent_name,
            scope="group",
            group_id=gid,
        )
        if group_content is not None:
            group_playbooks.append(
                PlaybookContent(
                    agent_name=agent_name,
                    scope="group",
                    content=group_content,
                    group_id=gid,
                    group_name=m.get("name"),
                )
            )

    return PlaybookListResponse(
        personal=PlaybookContent(agent_name=agent_name, scope="personal", content=personal_content)
        if personal_content is not None
        else None,
        groups=group_playbooks,
    )


@router.put("/agents/{agent_name}/{scope}", response_model=PlaybookContent)
async def update_playbook(
    agent_name: str,
    scope: str,
    body: PlaybookUpdate,
    request: Request,
    db: DbSession,
    group_id: str | None = Query(None, description="Group ID (required for group scope)"),
    current_user: User = Depends(require_auth),
) -> PlaybookContent:
    """Update AGENTS.md for an agent in the specified scope."""
    if scope not in ("personal", "group"):
        raise HTTPException(status_code=400, detail="scope must be 'personal' or 'group'")

    service = get_playbook_service(request)
    memberships = await _get_user_group_context(request, db, current_user)
    resolved_group_id, group_role = _resolve_group(memberships, group_id)

    if scope == "group":
        if not resolved_group_id:
            raise HTTPException(
                status_code=400, detail="No group context available or not a member of the specified group"
            )
        if group_role not in ("write", "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You need at least 'write' group role to modify group playbooks",
            )

    await service.put_agents_md(
        user_id=current_user.id,
        agent_name=agent_name,
        scope=scope,
        content=body.content,
        group_id=resolved_group_id,
    )

    return PlaybookContent(agent_name=agent_name, scope=scope, content=body.content)


@router.delete("/agents/{agent_name}/{scope}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    agent_name: str,
    scope: str,
    request: Request,
    db: DbSession,
    group_id: str | None = Query(None, description="Group ID (required for group scope)"),
    current_user: User = Depends(require_auth),
) -> None:
    """Delete AGENTS.md for an agent in the specified scope."""
    if scope not in ("personal", "group"):
        raise HTTPException(status_code=400, detail="scope must be 'personal' or 'group'")

    service = get_playbook_service(request)
    memberships = await _get_user_group_context(request, db, current_user)
    resolved_group_id, group_role = _resolve_group(memberships, group_id)

    if scope == "group":
        if not resolved_group_id:
            raise HTTPException(
                status_code=400, detail="No group context available or not a member of the specified group"
            )
        if group_role not in ("write", "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You need at least 'write' group role to modify group playbooks",
            )

    deleted = await service.delete_agents_md(
        user_id=current_user.id,
        agent_name=agent_name,
        scope=scope,
        group_id=resolved_group_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Playbook not found")


# --- Skills Endpoints ---


@router.get("/agents/{agent_name}/skills", response_model=SkillListResponse)
async def list_skills(
    agent_name: str,
    request: Request,
    db: DbSession,
    current_user: User = Depends(require_auth),
) -> SkillListResponse:
    """List all skill files for an agent (personal + all user groups)."""
    service = get_playbook_service(request)
    memberships = await _get_user_group_context(request, db, current_user)

    personal_skills = await service.list_skills(
        user_id=current_user.id,
        agent_name=agent_name,
        scope="personal",
    )

    group_skills: list[dict[str, str]] = []
    for m in memberships:
        gid = str(m["id"])
        skills = await service.list_skills(
            user_id=current_user.id,
            agent_name=agent_name,
            scope="group",
            group_id=gid,
        )
        for s in skills:
            s["group_id"] = gid
            s["group_name"] = m.get("name", "")
        group_skills.extend(skills)

    items = [SkillSummary(**s) for s in personal_skills + group_skills]
    return SkillListResponse(items=items)


@router.get("/agents/{agent_name}/skills/{skill_name}", response_model=SkillDetail)
async def get_skill(
    agent_name: str,
    skill_name: str,
    request: Request,
    db: DbSession,
    scope: str = "auto",
    group_id: str | None = Query(None, description="Group ID (required when scope='group')"),
    current_user: User = Depends(require_auth),
) -> SkillDetail:
    """Get a skill file's content.

    scope: 'personal', 'group', or 'auto' (tries personal first, then all groups).
    """
    _validate_skill_name(skill_name)
    service = get_playbook_service(request)
    memberships = await _get_user_group_context(request, db, current_user)

    if scope == "auto":
        # Try personal first
        content = await service.get_skill(
            user_id=current_user.id,
            agent_name=agent_name,
            skill_name=skill_name,
            scope="personal",
        )
        if content:
            return SkillDetail(name=skill_name, scope="personal", content=content)

        # Fallback: search all groups
        for m in memberships:
            gid = str(m["id"])
            content = await service.get_skill(
                user_id=current_user.id,
                agent_name=agent_name,
                skill_name=skill_name,
                scope="group",
                group_id=gid,
            )
            if content:
                return SkillDetail(name=skill_name, scope="group", content=content)

        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    if scope == "group":
        resolved_group_id, _ = _resolve_group(memberships, group_id)
        if not resolved_group_id:
            raise HTTPException(status_code=400, detail="group_id required for group scope")
        content = await service.get_skill(
            user_id=current_user.id,
            agent_name=agent_name,
            skill_name=skill_name,
            scope="group",
            group_id=resolved_group_id,
        )
        if not content:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found in group scope")
        return SkillDetail(name=skill_name, scope="group", content=content)

    if scope == "personal":
        content = await service.get_skill(
            user_id=current_user.id,
            agent_name=agent_name,
            skill_name=skill_name,
            scope="personal",
        )
        if not content:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found in personal scope")
        return SkillDetail(name=skill_name, scope="personal", content=content)

    raise HTTPException(status_code=400, detail="scope must be 'personal', 'group', or 'auto'")


@router.post("/agents/{agent_name}/skills/{scope}", response_model=SkillDetail, status_code=status.HTTP_201_CREATED)
async def create_skill(
    agent_name: str,
    scope: str,
    body: SkillCreate,
    request: Request,
    db: DbSession,
    group_id: str | None = Query(None, description="Group ID (required for group scope)"),
    current_user: User = Depends(require_auth),
) -> SkillDetail:
    """Create a new skill file."""
    if scope not in ("personal", "group"):
        raise HTTPException(status_code=400, detail="scope must be 'personal' or 'group'")

    _validate_skill_name(body.name)
    service = get_playbook_service(request)
    memberships = await _get_user_group_context(request, db, current_user)
    resolved_group_id, group_role = _resolve_group(memberships, group_id)

    if scope == "group":
        if not resolved_group_id:
            raise HTTPException(
                status_code=400, detail="No group context available or not a member of the specified group"
            )
        if group_role not in ("write", "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You need at least 'write' group role to create group skills",
            )

    # Check if skill already exists
    existing = await service.get_skill(
        user_id=current_user.id,
        agent_name=agent_name,
        skill_name=body.name,
        scope=scope,
        group_id=resolved_group_id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Skill '{body.name}' already exists. Use PUT to update.",
        )

    # Build SKILL.md content with frontmatter
    skill_content = _build_skill_content(body.name, body.description, body.content)

    await service.put_skill(
        user_id=current_user.id,
        agent_name=agent_name,
        skill_name=body.name,
        scope=scope,
        content=skill_content,
        group_id=resolved_group_id,
    )

    return SkillDetail(name=body.name, scope=scope, content=skill_content)


@router.put("/agents/{agent_name}/skills/{scope}/{skill_name}", response_model=SkillDetail)
async def update_skill(
    agent_name: str,
    scope: str,
    skill_name: str,
    body: SkillUpdate,
    request: Request,
    db: DbSession,
    group_id: str | None = Query(None, description="Group ID (required for group scope)"),
    current_user: User = Depends(require_auth),
) -> SkillDetail:
    """Update an existing skill file."""
    if scope not in ("personal", "group"):
        raise HTTPException(status_code=400, detail="scope must be 'personal' or 'group'")

    _validate_skill_name(skill_name)
    service = get_playbook_service(request)
    memberships = await _get_user_group_context(request, db, current_user)
    resolved_group_id, group_role = _resolve_group(memberships, group_id)

    if scope == "group":
        if not resolved_group_id:
            raise HTTPException(
                status_code=400, detail="No group context available or not a member of the specified group"
            )
        if group_role not in ("write", "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You need at least 'write' group role to modify group skills",
            )

    # Verify skill exists
    existing = await service.get_skill(
        user_id=current_user.id,
        agent_name=agent_name,
        skill_name=skill_name,
        scope=scope,
        group_id=resolved_group_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found in {scope} scope")

    await service.put_skill(
        user_id=current_user.id,
        agent_name=agent_name,
        skill_name=skill_name,
        scope=scope,
        content=body.content,
        group_id=resolved_group_id,
    )

    return SkillDetail(name=skill_name, scope=scope, content=body.content)


@router.delete("/agents/{agent_name}/skills/{scope}/{skill_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    agent_name: str,
    scope: str,
    skill_name: str,
    request: Request,
    db: DbSession,
    group_id: str | None = Query(None, description="Group ID (required for group scope)"),
    current_user: User = Depends(require_auth),
) -> None:
    """Delete a skill file."""
    if scope not in ("personal", "group"):
        raise HTTPException(status_code=400, detail="scope must be 'personal' or 'group'")

    _validate_skill_name(skill_name)
    service = get_playbook_service(request)
    memberships = await _get_user_group_context(request, db, current_user)
    resolved_group_id, group_role = _resolve_group(memberships, group_id)

    if scope == "group":
        if not resolved_group_id:
            raise HTTPException(
                status_code=400, detail="No group context available or not a member of the specified group"
            )
        if group_role not in ("write", "manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You need at least 'write' group role to delete group skills",
            )

    deleted = await service.delete_skill(
        user_id=current_user.id,
        agent_name=agent_name,
        skill_name=skill_name,
        scope=scope,
        group_id=resolved_group_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
