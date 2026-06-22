"""Minimal chat helper for console-backend's own LLM calls via the Model Gateway.

console-backend's utility LLM calls (watch-param generation, catalog summarization)
used raw boto3 `invoke_model`. They now go through the gateway like all
other LLM traffic — one OpenAI-compatible call with the app's virtual key. Kept
dependency-light (httpx only; no langchain in console-backend).
"""

import json
import logging
import os

import httpx

from ..config import config

logger = logging.getLogger(__name__)


async def gateway_registered_aliases(timeout: float = 10.0) -> set[str] | None:
    """Model aliases currently registered on the gateway, read with the app's virtual key
    (like ``gateway_chat`` — no master key, so this works from the catalog-worker deployment).

    Returns ``None`` when the gateway list can't be read, so callers fail open (treat
    registration as unknown rather than hard-blocking) — matching ``get_model_registry`` and
    agent-common's ``is_valid_model``.
    """
    headers = {"Authorization": f"Bearer {os.getenv('LLM_GATEWAY_API_KEY', 'sk-nannos-gateway')}"}
    url = f"{config.model_gateway.url.rstrip('/')}/v1/model/info"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        return {m["model_name"] for m in data if m.get("model_name")}
    except Exception as e:
        logger.warning("Gateway model list unreadable (%s); treating registration as unknown", e)
        return None


async def gateway_chat(
    prompt: str,
    *,
    model: str,
    max_tokens: int = 1024,
    metadata: dict | None = None,
    timeout: float = 60.0,
) -> str:
    """Single-turn completion through the gateway; returns the assistant text.

    `metadata` (e.g. {"user_sub": ...}) rides on x-litellm-spend-logs-metadata so the
    proxy attributes the cost. Without a user_sub the proxy logs nothing.

    Note: the canonical attribution-header builder lives in agent-common
    (`attribution.attribution_header`, used by the chat client + embeddings adapter). It is
    intentionally NOT imported here — console-backend is dependency-light (httpx only, no
    agent-common), and gateway_chat's only callers (watch-param generation, catalog
    summarization) run outside any sub-agent / scheduled-job context, so the richer
    attribution dimensions would always be empty. The caller passes whatever applies.
    """
    headers = {
        # Match the default every other gateway caller uses (agent-common._gateway_api_key,
        # the embeddings adapter): a consistent key avoids silent 401s when the env is unset.
        # console-backend is dependency-light (no agent-common), so the value is duplicated.
        "Authorization": f"Bearer {os.getenv('LLM_GATEWAY_API_KEY', 'sk-nannos-gateway')}",
        "Content-Type": "application/json",
    }
    if metadata:
        headers["x-litellm-spend-logs-metadata"] = json.dumps({k: v for k, v in metadata.items() if v is not None})

    url = f"{config.model_gateway.url.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url,
            headers=headers,
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
        )
        resp.raise_for_status()
        # content is null on a refusal / tool-call-only / empty completion — that's a
        # *successful* response with no text, not a transport failure. Return "" so callers'
        # str ops (re.sub/.strip) don't crash; they treat empty as "no usable output" and
        # apply their own fallback, distinct from the gateway error path (which raises above).
        content = resp.json()["choices"][0]["message"].get("content")
        return content or ""
