"""MCP tool discovery for scheduled runs: shared catalogue + call-time bearer tokens.

Before this module the runner exchanged the user's token once per audience, baked the
results into ``StreamableHttpConnection.headers`` and ran ``MultiServerMCPClient.get_tools()``
over the whole gateway — a full SDK parse of ~500 tools into pydantic objects on every run,
with credentials frozen into every tool at discovery time.

Now a run has the same shape as an orchestrator sub-agent (see ``agent_common``):

* **Catalogue** — each server the whitelist needs is listed with a stateless JSON-RPC
  ``tools/list`` (:func:`fetch_catalogue_stateless`, no handshake, no pydantic) and the SDK
  session (:func:`fetch_catalogue_mcp`) only as fallback. Either way the result is flattened
  to bytes; no ``mcp.types.Tool`` survives discovery.
* **Tools** — :class:`LazyMcpTool` per whitelisted name, so only the tools the run binds
  pay for schema decoding.
* **Credentials** — a per-run :class:`UserTokenProvider`; tool connections carry no
  ``Authorization`` header, :func:`bearer_interceptor` mints one per call (memoised until
  ``MCP_TOKEN_LEEWAY_SECONDS`` before ``exp``), so a token expiring mid-run is re-minted.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

import httpx
from agent_common.agents.dynamic_agent import is_console_backend_tool
from agent_common.core.catalogue_ingest import (
    StatelessListError,
    StatelessListUnsupported,
    fetch_catalogue_mcp,
    fetch_catalogue_stateless,
    set_stateless_supported,
    stateless_supported,
)
from agent_common.core.token_provider import UserTokenProvider, bearer_interceptor
from agent_common.core.tool_catalogue import ServerCatalogue, make_lazy_tool
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection

logger = logging.getLogger(__name__)

GATEWAY_SERVER = "gateway"
CONSOLE_SERVER = "console"

# Console-backend tools (``console_*``, ``scheduler_*``) go to the console MCP; the rest to the gateway.
is_console_tool = is_console_backend_tool

# A ``tools/list`` is a per-user view (a Gatana profile can hide tools of a server from one
# user and not another), so every run lists with its own token; nothing is shared between runs
# except the per-URL "does this endpoint serve stateless requests" memo in catalogue_ingest.


class McpToolResolver:
    """Resolve a scheduled run's tool whitelist to token-free :class:`LazyMcpTool` instances.

    One instance per run: it owns that run's :class:`UserTokenProvider` and the two
    possible connections (gateway, console).
    """

    def __init__(
        self,
        *,
        token_provider: UserTokenProvider,
        gateway_url: str,
        gateway_client_id: str,
        console_mcp_url: str,
        console_client_id: str,
        timeout: timedelta,
        stateless_list: bool = True,
    ) -> None:
        self.token_provider = token_provider
        self.gateway_client_id = gateway_client_id
        self.console_client_id = console_client_id
        self.stateless_list = stateless_list
        self._urls = {GATEWAY_SERVER: gateway_url, CONSOLE_SERVER: console_mcp_url}
        self._timeout = timeout
        # Discovery statistics for the last resolve(); logged and surfaced for measurements.
        self.stats: dict[str, Any] = {}

    # -- audiences / connections -------------------------------------------------------
    def audience_for(self, server_name: str) -> str:
        return self.console_client_id if server_name == CONSOLE_SERVER else self.gateway_client_id

    def _connection(self, server_name: str, *, bearer: str | None = None) -> StreamableHttpConnection:
        """A connection for ``server_name``; token-free unless ``bearer`` is given (listing only)."""
        connection = StreamableHttpConnection(
            transport="streamable_http",
            url=self._urls[server_name],
            timeout=self._timeout,
            sse_read_timeout=self._timeout,
        )
        if bearer is not None:
            connection["headers"] = {"Authorization": f"Bearer {bearer}"}
        return connection

    # -- listing -------------------------------------------------------------------------
    async def _list_server(self, server_name: str, http_client: httpx.AsyncClient) -> ServerCatalogue:
        """``tools/list`` for one server: stateless POST first, SDK session as fallback.

        The listing itself needs a bearer (the gateway filters the catalogue per user), so
        it asks the provider for one — the only place discovery touches a token. Whether an
        endpoint serves stateless requests is memoised per URL for the process lifetime.
        """
        url = self._urls[server_name]
        bearer = await self.token_provider.get(self.audience_for(server_name))
        if self.stateless_list and stateless_supported(url) is not False:
            try:
                catalogue = await fetch_catalogue_stateless(
                    http_client, url=url, headers={"Authorization": f"Bearer {bearer}"}, server_slug=server_name
                )
            except StatelessListUnsupported as e:
                set_stateless_supported(url, False)
                logger.warning(
                    "MCP endpoint refuses stateless tools/list — using SDK session for '%s' (%s)", server_name, e
                )
            except StatelessListError as e:
                logger.warning("Stateless tools/list failed for '%s', falling back to SDK session: %s", server_name, e)
            else:
                set_stateless_supported(url, True)
                self.stats["source"][server_name] = "stateless"
                return catalogue
        client = MultiServerMCPClient({server_name: self._connection(server_name, bearer=bearer)})
        catalogue = await fetch_catalogue_mcp(lambda: client.session(server_name), server_slug=server_name)
        self.stats["source"][server_name] = "mcp"
        return catalogue

    # -- resolution ----------------------------------------------------------------------
    async def resolve(self, wanted: Iterable[str]) -> list[BaseTool]:
        """Tools for ``wanted`` names: one ``tools/list`` per server the whitelist needs.

        Always listed with this run's own token, so the run only ever binds tools this user
        is offered; names no server lists are logged and skipped (the whitelist filter the
        runner always applied).
        """
        started = time.monotonic()
        names = set(wanted)
        self.stats = {"source": {}}
        interceptors = [bearer_interceptor(self.token_provider, self.audience_for)]
        connections = {
            server: self._connection(server)
            for server, predicate in (
                (GATEWAY_SERVER, lambda n: not is_console_tool(n)),
                (CONSOLE_SERVER, is_console_tool),
            )
            if any(predicate(n) for n in names)
        }

        def _server_for(name: str) -> str:
            return CONSOLE_SERVER if is_console_tool(name) else GATEWAY_SERVER

        # Exchange up front for every audience the run needs: discovery used to do this, and
        # a user token that is expired or revoked must fail the run here, not surface as a
        # run that "succeeded" without ever being able to call a tool.
        for server in connections:
            await self.token_provider.get(self.audience_for(server))

        tools: list[BaseTool] = []
        # follow_redirects: console-backend's ``/mcp`` mount answers ``307 → /mcp/``.
        async with httpx.AsyncClient(timeout=self._timeout.total_seconds(), follow_redirects=True) as http_client:
            for server, connection in connections.items():
                catalogue = await self._list_server(server, http_client)
                for name in sorted(n for n in names if _server_for(n) == server):
                    entry = catalogue.tools.get(name)
                    if entry is None:
                        continue  # not offered to this user by this server
                    tools.append(
                        make_lazy_tool(
                            entry,
                            server_name=server,
                            connection=connection,
                            tool_interceptors=interceptors,
                        )
                    )

        unresolved = names - {t.name for t in tools}
        self.stats["unresolved"] = sorted(unresolved)
        self.stats["seconds"] = round(time.monotonic() - started, 3)
        logger.info(
            "Resolved %d/%d MCP tools in %.3fs via tools/list (%s)%s",
            len(tools),
            len(names),
            self.stats["seconds"],
            ", ".join(f"{s}={src}" for s, src in self.stats["source"].items()) or "no listing",
            f"; not offered by any server: {sorted(unresolved)}" if unresolved else "",
        )
        return tools
