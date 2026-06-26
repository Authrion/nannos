-- rambler up

-- ============================================================================
-- Make the agent-creator emit absolute, clickable links to created sub-agents.
--
-- The agent-creator is a LOCAL sub-agent (see migration 065). Its stored prompt
-- told the model to construct relative paths ("/app/subagents/{sub_agent_id}"),
-- which aren't clickable and can't be completed by the model — it has no idea of
-- the console host. We now use the whitelisted {{CONSOLE_FRONTEND_URL}} placeholder,
-- which the orchestrator resolves from the environment at prompt-materialization
-- time (registry._resolve_prompt_placeholders). The DB stays env-agnostic.
-- ============================================================================

UPDATE sub_agent_config_versions cv
SET system_prompt = replace(
        replace(cv.system_prompt,
                '/app/subagents/{sub_agent_id}',
                '{{CONSOLE_FRONTEND_URL}}/app/subagents/{sub_agent_id}'),
        -- the <important_rules> line uses a shorter relative form
        'link to the created agent: /subagents/{sub_agent_id}',
        'link to the created agent: {{CONSOLE_FRONTEND_URL}}/app/subagents/{sub_agent_id}')
FROM sub_agents sa
WHERE cv.sub_agent_id = sa.id
  AND sa.owner_user_id = 'system'
  AND sa.name = 'agent-creator'
  AND cv.system_prompt LIKE '%/subagents/{sub_agent_id}%';

-- rambler down

UPDATE sub_agent_config_versions cv
SET system_prompt = replace(
        replace(cv.system_prompt,
                '{{CONSOLE_FRONTEND_URL}}/app/subagents/{sub_agent_id}',
                '/app/subagents/{sub_agent_id}'),
        'link to the created agent: /app/subagents/{sub_agent_id}',
        'link to the created agent: /subagents/{sub_agent_id}')
FROM sub_agents sa
WHERE cv.sub_agent_id = sa.id
  AND sa.owner_user_id = 'system'
  AND sa.name = 'agent-creator'
  AND cv.system_prompt LIKE '%{{CONSOLE_FRONTEND_URL}}%';
