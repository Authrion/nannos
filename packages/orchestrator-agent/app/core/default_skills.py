"""Default skills bundled with the orchestrator.

These are always available to the orchestrator regardless of user configuration.
Users can override them with personal/group skills of the same name.
"""

from agent_common.models.skill import SkillDefinition

FIND_SKILLS_BODY = """\
# find-skills

Discover and activate reusable skills from the platform skill registry.

## When to Use

Use this skill when:
- A task could benefit from an existing skill you don't currently have
- The user asks to find, search, or install/activate a skill
- You recognize a recurring pattern that likely has a registry skill available
- The user mentions a technology or framework that may have a specialized skill

## Available Tools

- `console_search_skills` — Search the skill registry (source of truth for all skills)
- `console_activate_skill` — Activate a registry skill on a sub-agent
- `console_import_skill` — Import a skill from a GitHub repository into the registry

## Workflow

1. **Search the skill registry** (all available skills live here):
   ```
   console_search_skills(query="next.js development", source="registry")
   ```

2. **If nothing found internally, search external sources**:
   ```
   console_search_skills(query="next.js development", source="external")
   ```

3. **Or browse a known repository**:
   ```
   console_search_skills(query="", source="repo:anthropics/skills")
   ```

4. **Present options to the user** — never auto-activate without confirmation. Show:
   - Skill name and description
   - Source (registry vs external)
   - Let the user choose which to activate/import

5. **Activate a registry skill** (if skill already exists in registry):
   ```
   console_activate_skill(
       skill_name="skill-slug",
       scope="personal"
   )
   ```

6. **Import an external skill** (adds to registry then activates):
   ```
   console_import_skill(
       repo="owner/repo",
       skill="skill-name",
       scope="personal"
   )
   ```

## Guidelines

- **Always ask before activating** — present search results and let the user decide
- **Prefer registry results** — they're vetted and instantly activatable
- **Use `console_activate_skill`** for skills already in the registry
- **Use `console_import_skill`** only for external GitHub skills not yet in the registry
- **Use personal scope** for experimentation, group scope for team-wide skills
- **Check security verdicts** — if a skill is marked 'caution' or 'unsafe', warn the user
- **Known quality repositories**: `anthropics/skills`, `OthmanAdi/planning-with-files`
- **Don't search for every task** — only when there's a clear skill gap or user request
"""

FIND_SKILLS = SkillDefinition(
    name="find-skills",
    description="Discover and activate reusable skills from the platform skill registry or GitHub repositories.",
    body=FIND_SKILLS_BODY,
)

# All default skills for the orchestrator
ORCHESTRATOR_DEFAULT_SKILLS: list[SkillDefinition] = [
    FIND_SKILLS,
]
