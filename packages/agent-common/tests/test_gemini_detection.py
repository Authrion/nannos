"""is_gemini_model: which models get Google's server-side built-in tools.

Built-in tools (google_search, code_execution) are Google-product-specific and have no
gateway capability flag yet, so detection is by provider — but NOT a bare "vertex" match,
since Vertex also hosts Claude/Llama that must never be bound Google tools.
"""

from unittest.mock import patch

import pytest

from agent_common.core.model_factory import is_gemini_model

_PATCH = "agent_common.core.model_factory.get_model_provider"


def _provider(value: str):
    return patch(_PATCH, return_value=value)


@pytest.mark.parametrize("alias", ["gemini-3-flash-preview", "anything", ""])
def test_ai_studio_gemini_provider_is_gemini(alias):
    # The 'gemini' provider (AI Studio) is unambiguously Gemini regardless of alias.
    with _provider("gemini"):
        assert is_gemini_model(alias) is True


def test_vertex_gemini_is_gemini():
    with _provider("vertex_ai"):
        assert is_gemini_model("gemini-3-flash-preview") is True
        assert is_gemini_model("my-Gemini-Embedding") is True  # case-insensitive


def test_vertex_non_gemini_is_not_gemini():
    # The bug this fixes: Vertex-hosted Claude/Llama must NOT be treated as Gemini, or the
    # orchestrator would bind google_search/code_execution and the gateway would 4xx.
    with _provider("vertex_ai"):
        assert is_gemini_model("claude-sonnet-4-6") is False
        assert is_gemini_model("llama-3-on-vertex") is False


@pytest.mark.parametrize("provider", ["bedrock_converse", "openai", "azure", ""])
def test_other_providers_are_not_gemini(provider):
    # Including the unknown/cold-cache provider ("") — fails safe (no built-in tools bound).
    with _provider(provider):
        assert is_gemini_model("gemini-shaped-name") is False
