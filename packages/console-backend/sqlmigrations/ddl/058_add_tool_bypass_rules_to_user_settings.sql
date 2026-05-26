-- rambler up
ALTER TABLE user_settings
ADD COLUMN tool_bypass_rules JSONB NOT NULL DEFAULT '{}'::JSONB;
COMMENT ON COLUMN user_settings.tool_bypass_rules IS 'Per-tool HITL bypass rules. Format: {"tool_name::server_slug": {"bypass_all": true} | {"bypass_patterns": {"param": ["glob1"]}}}';
-- rambler down
ALTER TABLE user_settings DROP COLUMN IF EXISTS tool_bypass_rules;
