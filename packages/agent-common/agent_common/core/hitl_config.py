"""Shared HITL (Human-In-The-Loop) guard configuration.

DEPRECATED: Static HITL guards have been migrated to the tool_risk_scores
database table (migration 056). The dynamic risk scoring system now handles
all tool guarding via LLM-based risk assessment + DB-stored scores.

This module is kept for backward compatibility but exports empty dicts.
Remove once all consumers are updated.
"""

from typing import Any

# These are now managed in the tool_risk_scores DB table.
# Kept as empty dicts for any code that still references them during transition.
PRIVACY_HITL_GUARDS: dict[str, dict[str, Any]] = {}
SELF_IMPROVEMENT_HITL_GUARDS: dict[str, dict] = {}
