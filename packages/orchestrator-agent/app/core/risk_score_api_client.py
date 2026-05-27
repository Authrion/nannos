"""HTTP client for tool risk scores API on console-backend.

Implements the RiskScoreAPIClient protocol for ToolRiskCache persistence.

Auth strategy:
- Writes (upsert): Uses orchestrator's client_credentials token (azp = orchestrator).
  This is verified by the console-backend's require_admin_or_orchestrator dependency.
- Reads: Uses request-scoped user token (for in-request reads) or client_credentials
  token (for background refresh loop where no user context is available).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import httpx
from ringier_a2a_sdk.cost_tracking.logger import get_request_access_token

if TYPE_CHECKING:
    from ringier_a2a_sdk.oauth import OidcOAuth2Client

logger = logging.getLogger(__name__)


class HttpRiskScoreAPIClient:
    """HTTP implementation of RiskScoreAPIClient protocol.

    Uses the console-backend REST API for reading and writing tool risk scores.

    Auth:
    - For writes: client_credentials token via OidcOAuth2Client (service identity)
    - For reads: request-scoped user token OR client_credentials fallback
    """

    def __init__(
        self, base_url: str, oauth2_client: OidcOAuth2Client | None = None, audience: str = "agent-console"
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._oauth2_client = oauth2_client
        self._audience = audience
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=10.0,
            )
        return self._client

    async def _get_service_headers(self) -> dict[str, str]:
        """Get auth headers using orchestrator's client_credentials token."""
        if self._oauth2_client is None:
            return {}
        try:
            token = await self._oauth2_client.get_token(self._audience)
            return {"Authorization": f"Bearer {token}"}
        except Exception:
            logger.debug("Failed to get client_credentials token for risk score API", exc_info=True)
            return {}

    def _get_user_headers(self) -> dict[str, str]:
        """Get auth headers using request-scoped user token."""
        token = get_request_access_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def _get_read_headers(self) -> dict[str, str]:
        """Get headers for read operations: prefer user token, fall back to service token."""
        headers = self._get_user_headers()
        if headers:
            return headers
        return await self._get_service_headers()

    async def get_scores_paginated(self, limit: int, offset: int) -> Sequence[dict[str, Any]]:
        """Fetch paginated scores sorted by updated_at desc."""
        client = self._get_client()
        headers = await self._get_read_headers()
        if not headers:
            logger.debug("No access token available for risk score API refresh")
            return []

        resp = await client.get(
            "/api/mcp/tools/risk-scores",
            params={"limit": limit, "offset": offset},
            headers=headers,
        )
        if resp.status_code != 200:
            logger.warning("Risk score API returned %d on paginated GET", resp.status_code)
            return []

        data = resp.json()
        return data.get("items", [])

    async def get_score(self, tool_name: str, server_slug: str) -> dict[str, Any] | None:
        """Fetch a single score by tool_name and server_slug."""
        client = self._get_client()
        headers = await self._get_read_headers()
        if not headers:
            return None

        resp = await client.get(
            f"/api/mcp/tools/risk-scores/{tool_name}/{server_slug}",
            headers=headers,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning("Risk score API returned %d on GET", resp.status_code)
            return None

        return resp.json()

    async def upsert_score(self, data: dict[str, Any]) -> None:
        """Upsert a risk score entry using service credentials (admin-level)."""
        client = self._get_client()
        headers = await self._get_service_headers()
        if not headers:
            logger.warning("No service token available for risk score upsert — score will not be persisted")
            return

        resp = await client.put(
            "/api/mcp/tools/risk-scores",
            json=data,
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            logger.warning(
                "Risk score API returned %d on upsert for %s::%s",
                resp.status_code,
                data.get("tool_name"),
                data.get("server_slug"),
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
