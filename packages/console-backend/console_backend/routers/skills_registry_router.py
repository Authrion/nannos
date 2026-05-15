"""Skills Registry API endpoints.

Provides search, browse, and import endpoints for discovering and importing
skills from external registries (skills.sh, GitHub) into the local skill store.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from console_backend.dependencies import require_auth
from console_backend.models.skills_registry import (
    SkillAuditResponse,
    SkillDetailResponse,
    SkillFile,
    SkillImportRequest,
    SkillImportResponse,
    SkillSearchResponse,
    SkillSourceInfo,
)
from console_backend.models.user import User
from console_backend.services.skills_registry_service import skills_registry_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/skills/registry", tags=["skills-registry"])


@router.get("/search", response_model=SkillSearchResponse)
async def search_skills(
    q: str = Query(..., min_length=2, max_length=200, description="Search query"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results to return"),
    user: User = Depends(require_auth),
) -> SkillSearchResponse:
    """Search for skills on skills.sh.

    Uses semantic search for multi-word queries, fuzzy match for single-word.
    """
    results, search_type = await skills_registry_service.search_skills(query=q, limit=limit)
    return SkillSearchResponse(data=results, query=q, search_type=search_type, count=len(results))


@router.get("/browse", response_model=SkillSearchResponse)
async def browse_repo(
    repo: str = Query(..., min_length=3, max_length=200, description="GitHub repo (owner/repo)"),
    ref: str = Query(default="main", max_length=100, description="Git ref (branch/tag/SHA)"),
    user: User = Depends(require_auth),
) -> SkillSearchResponse:
    """Browse skills available in a GitHub repository.

    Scans the repo's tree for SKILL.md files and returns available skills.
    Uses authenticated GitHub API if GITHUB_TOKEN is configured.
    """
    # Basic validation: must contain exactly one slash
    parts = repo.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repo must be in 'owner/repo' format",
        )

    results = await skills_registry_service.browse_repo(repo=repo, ref=ref)
    return SkillSearchResponse(data=results, query=repo, count=len(results))


@router.get("/detail/{skill_id:path}", response_model=SkillDetailResponse)
async def get_skill_detail(
    skill_id: str,
    user: User = Depends(require_auth),
) -> SkillDetailResponse:
    """Get full skill details from skills.sh (files, hash, audit info).

    skill_id is the full path identifier like 'owner/repo/skill-name'.
    """
    detail = await skills_registry_service.get_skill_detail(skill_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_id}' not found on skills.sh",
        )
    return detail


@router.get("/audit/{skill_id:path}", response_model=SkillAuditResponse)
async def get_skill_audit(
    skill_id: str,
    user: User = Depends(require_auth),
) -> SkillAuditResponse:
    """Get security audit for a skill from skills.sh.

    Returns audit assessments from security partners (Gen Agent Trust Hub, Socket, Snyk, Runlayer, ZeroLeaks).
    Returns 404 if no partner has audited this skill yet.
    """
    audit = await skills_registry_service.get_skill_audit(skill_id)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No audit found for skill '{skill_id}'",
        )
    return audit


@router.post("/import", response_model=SkillImportResponse, status_code=status.HTTP_201_CREATED)
async def import_skill(
    body: SkillImportRequest,
    request: Request,
    user: User = Depends(require_auth),
) -> SkillImportResponse:
    """Import a skill from skills.sh or GitHub into the local skill store.

    Fetches the skill files from the external registry and writes them to the
    docstore via PlaybookService. Supports both skills.sh (by ID) and GitHub
    (by repo + skill name) as sources.

    Returns 409 if the skill already exists (unless overwrite=True).
    Returns 404 if the skill cannot be found at the source.
    """
    from console_backend.routers.playbook_router import get_playbook_service

    playbook_service = get_playbook_service(request)

    # Resolve skill files from external source
    skill_content: str | None = None
    bundled_files: list[SkillFile] = []
    source_info: SkillSourceInfo

    if body.id:
        # Fetch from skills.sh by ID
        detail = await skills_registry_service.get_skill_detail(body.id)
        if detail is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{body.id}' not found on skills.sh",
            )
        if not detail.files:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Skill '{body.id}' has no files on skills.sh",
            )
        # Find SKILL.md (entry point)
        for f in detail.files:
            if f.path == "SKILL.md":
                skill_content = f.contents
            else:
                bundled_files.append(f)

        if not skill_content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Skill '{body.id}' has no SKILL.md file",
            )

        source_info = SkillSourceInfo(
            type="skills.sh",
            id=body.id,
            hash=detail.hash,
            imported_at=datetime.now(timezone.utc).isoformat(),
        )

    elif body.repo and body.skill:
        # Fetch from GitHub
        github_detail = await skills_registry_service.fetch_skill_files_from_github(
            repo=body.repo, skill_name=body.skill, ref="main"
        )
        if github_detail is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{body.skill}' not found in repo '{body.repo}'",
            )
        # Find SKILL.md
        for f in github_detail.files:
            if f.path == "SKILL.md":
                skill_content = f.contents
            else:
                bundled_files.append(f)

        if not skill_content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Skill '{body.skill}' in '{body.repo}' has no SKILL.md file",
            )

        source_info = SkillSourceInfo(
            type="github",
            repo=body.repo,
            skill=body.skill,
            hash=github_detail.tree_sha,
            imported_at=datetime.now(timezone.utc).isoformat(),
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either 'id' (skills.sh) or both 'repo' and 'skill' (GitHub)",
        )

    # Determine skill name for storage
    if body.skill:
        skill_name = body.skill
    elif body.id:
        skill_name = body.id.split("/")[-1]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine skill name from request",
        )

    # Check if skill already exists
    if not body.overwrite:
        existing = await playbook_service.get_skill(
            user_id=user.id,
            agent_name=body.agent,
            skill_name=skill_name,
            scope=body.scope,
            group_id=body.group_id,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Skill '{skill_name}' already exists for agent '{body.agent}'. Set overwrite=true to replace.",
            )

    # Write to docstore
    files_data = [{"path": f.path, "content": f.contents} for f in bundled_files] if bundled_files else None

    try:
        await playbook_service.put_skill_with_files(
            user_id=user.id,
            agent_name=body.agent,
            skill_name=skill_name,
            scope=body.scope,
            content=skill_content,
            files=files_data,
            group_id=body.group_id,
            replace_files=body.overwrite,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    logger.info(
        "Imported skill '%s' from %s for agent '%s' (scope=%s, user=%s)",
        skill_name,
        source_info.type,
        body.agent,
        body.scope,
        user.id,
    )

    return SkillImportResponse(
        skill_name=skill_name,
        agent=body.agent,
        scope=body.scope,
        source=source_info,
        files_count=1 + len(bundled_files),
        overwritten=body.overwrite,
    )
