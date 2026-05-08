"""Three-tier skill resolution: personal > group > standard."""

from __future__ import annotations

import logging

from langgraph.store.postgres.aio import AsyncPostgresStore

from agent_common.core.playbook_reader import PlaybookReaderService
from agent_common.models.skill import ResolvedSkill, SkillDefinition

logger = logging.getLogger(__name__)


async def resolve_skills_for_agent(
    store: AsyncPostgresStore,
    user_id: str,
    agent_name: str,
    group_ids: list[str],
    standard_skills: list[SkillDefinition],
) -> dict[str, ResolvedSkill]:
    """Resolve skills from all three tiers, applying override semantics.

    Resolution order: personal > group > standard.
    A personal skill with the same name as a standard skill overrides it.

    Args:
        store: Document store for reading personal/group skills
        user_id: User's stable database ID
        agent_name: Sub-agent name
        group_ids: Group IDs for group-scoped skills
        standard_skills: Immutable skills from sub-agent config

    Returns:
        Dict mapping skill name -> ResolvedSkill (overrides applied)
    """
    resolved: dict[str, ResolvedSkill] = {}

    # 1. Start with standard skills (lowest priority)
    standard_names = set()
    for skill in standard_skills:
        standard_names.add(skill.name)
        resolved[skill.name] = ResolvedSkill(
            name=skill.name,
            description=skill.description,
            body=skill.body,
            scope="standard",
            files=skill.files,
        )

    # 2. Read personal + group skills from docstore via PlaybookReaderService
    reader = PlaybookReaderService(store)
    docstore_skills = await reader.list_skills(
        user_id=user_id,
        agent_name=agent_name,
        group_ids=group_ids,
    )

    # 3. Apply overrides: group skills override standard, personal overrides both
    for entry in docstore_skills:
        # Read full skill content
        content = await reader.read_skill(
            user_id=user_id,
            agent_name=agent_name,
            skill_name=entry.name,
            group_ids=group_ids,
            scope=entry.scope,
        )
        if not content:
            continue

        overrides = "standard" if entry.name in standard_names else None
        resolved[entry.name] = ResolvedSkill(
            name=entry.name,
            description=entry.description,
            body=content,
            scope=entry.scope,
            overrides=overrides,
        )

    logger.debug(
        "Resolved %d skills for agent %s (user=%s): %s",
        len(resolved),
        agent_name,
        user_id,
        list(resolved.keys()),
    )
    return resolved
