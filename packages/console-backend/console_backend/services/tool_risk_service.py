"""Service for tool risk scores CRUD operations.

This is a system-level cache service (not user-owned data), so it uses
direct SQL rather than the AuditedRepository pattern. Tool risk scores
are auto-populated by LLM scoring in the orchestrator/agent-runner.
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ToolRiskService:
    """CRUD service for tool_risk_scores table."""

    async def get_score(
        self,
        db: AsyncSession,
        tool_name: str,
        server_slug: str,
    ) -> dict[str, Any] | None:
        """Get a single risk score by tool_name and server_slug."""
        result = await db.execute(
            text("""
                SELECT tool_name, server_slug, schema_hash, base_score,
                       risk_factors, allowed_actions, updated_at, created_at
                FROM tool_risk_scores
                WHERE tool_name = :tool_name AND server_slug = :server_slug
            """),
            {"tool_name": tool_name, "server_slug": server_slug},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_scores_paginated(
        self,
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get paginated scores sorted by updated_at desc (most recent first)."""
        result = await db.execute(
            text("""
                SELECT tool_name, server_slug, schema_hash, base_score,
                       risk_factors, allowed_actions, updated_at, created_at
                FROM tool_risk_scores
                ORDER BY updated_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        )
        return [dict(row) for row in result.mappings().all()]

    async def upsert_score(
        self,
        db: AsyncSession,
        tool_name: str,
        server_slug: str,
        schema_hash: str,
        base_score: float,
        risk_factors: dict[str, Any],
        allowed_actions: list[str],
    ) -> dict[str, Any]:
        """Upsert a risk score entry. Updates on conflict (tool_name, server_slug)."""
        result = await db.execute(
            text("""
                INSERT INTO tool_risk_scores
                    (tool_name, server_slug, schema_hash, base_score, risk_factors, allowed_actions, updated_at)
                VALUES
                    (:tool_name, :server_slug, :schema_hash, :base_score,
                     CAST(:risk_factors AS jsonb), CAST(:allowed_actions AS jsonb), NOW())
                ON CONFLICT (tool_name, server_slug)
                DO UPDATE SET
                    schema_hash = EXCLUDED.schema_hash,
                    base_score = EXCLUDED.base_score,
                    risk_factors = EXCLUDED.risk_factors,
                    allowed_actions = EXCLUDED.allowed_actions,
                    updated_at = NOW()
                RETURNING tool_name, server_slug, schema_hash, base_score,
                          risk_factors, allowed_actions, updated_at, created_at
            """),
            {
                "tool_name": tool_name,
                "server_slug": server_slug,
                "schema_hash": schema_hash,
                "base_score": base_score,
                "risk_factors": _json_dumps(risk_factors),
                "allowed_actions": _json_dumps(allowed_actions),
            },
        )
        row = result.mappings().first()
        await db.commit()
        return dict(row) if row else {}

    async def delete_score(
        self,
        db: AsyncSession,
        tool_name: str,
        server_slug: str,
    ) -> bool:
        """Delete a risk score (admin invalidation). Returns True if deleted."""
        result = await db.execute(
            text("""
                DELETE FROM tool_risk_scores
                WHERE tool_name = :tool_name AND server_slug = :server_slug
            """),
            {"tool_name": tool_name, "server_slug": server_slug},
        )
        await db.commit()
        return result.rowcount > 0

    async def get_count(self, db: AsyncSession) -> int:
        """Get total count of risk scores."""
        result = await db.execute(text("SELECT COUNT(*) FROM tool_risk_scores"))
        return result.scalar() or 0


def _json_dumps(obj: Any) -> str:
    """Serialize to JSON string for PostgreSQL JSONB parameters."""
    import json

    return json.dumps(obj)


# Singleton instance
tool_risk_service = ToolRiskService()
