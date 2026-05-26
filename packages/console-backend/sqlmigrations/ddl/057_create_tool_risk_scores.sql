-- rambler up
-- Tool risk scores table: caches LLM-assessed risk profiles for MCP tools.
-- Used by the orchestrator/agent-runner in-memory cache with periodic refresh.
CREATE TABLE tool_risk_scores (
    tool_name TEXT NOT NULL,
    server_slug TEXT NOT NULL,
    schema_hash VARCHAR(64) NOT NULL DEFAULT '',
    base_score FLOAT NOT NULL DEFAULT 0.5,
    risk_factors JSONB NOT NULL DEFAULT '{}'::JSONB,
    allowed_actions JSONB NOT NULL DEFAULT '["approve", "edit", "reject"]'::JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tool_name, server_slug)
);
-- Index for paginated refresh queries (sorted by most recently scored)
CREATE INDEX idx_tool_risk_scores_updated_at ON tool_risk_scores (updated_at DESC);
-- Seed static guards (formerly in interrupt_on dicts)
-- These always trigger HITL (base_score=1.0) and cannot be bypassed by scoring
INSERT INTO tool_risk_scores (
        tool_name,
        server_slug,
        schema_hash,
        base_score,
        risk_factors,
        allowed_actions
    )
VALUES (
        'console_create_skill',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'console_update_skill',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'console_remove_skill',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'console_import_skill',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "reject"]'::JSONB
    ),
    (
        'console_activate_skill',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "reject"]'::JSONB
    ),
    (
        'console_update_playbook',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'console_write_skill_file',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'console_delete_skill_file',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'console_create_sub_agent',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'console_update_sub_agent',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'console_create_bug_report',
        'console',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "edit", "reject"]'::JSONB
    ),
    (
        'read_personal_file',
        '_self',
        '',
        1.0,
        '{}'::JSONB,
        '["approve", "reject"]'::JSONB
    ),
    (
        'docstore_search',
        '_self',
        '',
        0.3,
        '{"include_personal": {"risky_values": {"true": 1.0, "True": 1.0}, "default_contribution": 0.0}}'::JSONB,
        '["approve", "reject"]'::JSONB
    );
-- rambler down
DROP TABLE IF EXISTS tool_risk_scores;
