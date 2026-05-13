"""Tests for SkillsStoreBackend."""

import pytest

from agent_common.backends.skills_store import SkillsStoreBackend
from agent_common.models.skill import ResolvedSkill, SkillFile


def _make_skills() -> dict[str, ResolvedSkill]:
    return {
        "incident-triage": ResolvedSkill(
            name="incident-triage",
            description="Handle production incidents step by step.",
            body="# Steps\n\n1. Check alerts\n2. Investigate\n3. Resolve",
            scope="standard",
            files=[
                SkillFile(path="scripts/check.py", content="print('checking')"),
                SkillFile(path="references/runbook.md", content="# Runbook\nDo things."),
            ],
        ),
        "weekly-report": ResolvedSkill(
            name="weekly-report",
            description="Generate a weekly report.",
            body="Summarize the week's work.",
            scope="personal",
            overrides="standard",
        ),
    }


@pytest.fixture
def backend():
    return SkillsStoreBackend(_make_skills())


# ---- aread tests ----


@pytest.mark.asyncio
async def test_read_skill_md(backend):
    result = await backend.aread("/skills/incident-triage/SKILL.md")
    assert result.error is None
    assert result.file_data is not None
    content = result.file_data["content"]
    assert "name: incident-triage" in content
    assert "description: Handle production incidents step by step." in content
    assert "# Steps" in content


@pytest.mark.asyncio
async def test_read_skill_md_without_prefix(backend):
    result = await backend.aread("incident-triage/SKILL.md")
    assert result.error is None
    assert "name: incident-triage" in result.file_data["content"]


@pytest.mark.asyncio
async def test_read_bundled_file(backend):
    result = await backend.aread("/skills/incident-triage/scripts/check.py")
    assert result.error is None
    assert result.file_data["content"] == "print('checking')"


@pytest.mark.asyncio
async def test_read_bundled_file_reference(backend):
    result = await backend.aread("/skills/incident-triage/references/runbook.md")
    assert result.error is None
    assert "# Runbook" in result.file_data["content"]


@pytest.mark.asyncio
async def test_read_nonexistent_skill(backend):
    result = await backend.aread("/skills/nonexistent/SKILL.md")
    assert result.error is not None
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_read_nonexistent_file(backend):
    result = await backend.aread("/skills/incident-triage/missing.txt")
    assert result.error is not None
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_read_invalid_path(backend):
    result = await backend.aread("/skills/")
    assert result.error is not None


@pytest.mark.asyncio
async def test_read_offset_limit(backend):
    """Verify offset/limit (line-based) works."""
    result = await backend.aread("/skills/incident-triage/SKILL.md", offset=0, limit=2)
    assert result.error is None
    lines = result.file_data["content"].splitlines()
    assert len(lines) == 2


# ---- als tests ----


@pytest.mark.asyncio
async def test_ls_root(backend):
    result = await backend.als("/skills/")
    assert result.error is None
    assert result.entries is not None
    paths = [e["path"] for e in result.entries]
    assert "/incident-triage/" in paths
    assert "/weekly-report/" in paths


@pytest.mark.asyncio
async def test_ls_root_bare(backend):
    result = await backend.als("/")
    assert result.error is None
    assert len(result.entries) == 2


@pytest.mark.asyncio
async def test_ls_skill_directory(backend):
    result = await backend.als("/skills/incident-triage/")
    assert result.error is None
    paths = [e["path"] for e in result.entries]
    assert "/SKILL.md" in paths
    assert "/scripts/check.py" in paths
    assert "/references/runbook.md" in paths


@pytest.mark.asyncio
async def test_ls_skill_no_files(backend):
    result = await backend.als("/skills/weekly-report/")
    assert result.error is None
    paths = [e["path"] for e in result.entries]
    assert paths == ["/SKILL.md"]


@pytest.mark.asyncio
async def test_ls_nonexistent(backend):
    result = await backend.als("/skills/nonexistent/")
    assert result.error is not None


@pytest.mark.asyncio
async def test_ls_entries_mark_directories(backend):
    result = await backend.als("/skills/")
    for entry in result.entries:
        assert entry.get("is_dir") is True


# ---- agrep tests ----


@pytest.mark.asyncio
async def test_grep_finds_match(backend):
    result = await backend.agrep("Check alerts")
    assert result.error is None
    assert len(result.matches) >= 1
    match = result.matches[0]
    assert match["path"] == "/skills/incident-triage/SKILL.md"
    assert match["line"] > 0
    assert "Check alerts" in match["text"]


@pytest.mark.asyncio
async def test_grep_case_insensitive(backend):
    result = await backend.agrep("CHECK ALERTS")
    assert result.error is None
    assert len(result.matches) >= 1


@pytest.mark.asyncio
async def test_grep_no_match(backend):
    result = await backend.agrep("zzz_nonexistent_pattern_zzz")
    assert result.error is None
    assert result.matches == []


# ---- aglob tests ----


@pytest.mark.asyncio
async def test_glob_all_skill_mds(backend):
    result = await backend.aglob("*.md")
    assert result.error is None
    paths = [e["path"] for e in result.matches]
    assert "/skills/incident-triage/SKILL.md" in paths
    assert "/skills/weekly-report/SKILL.md" in paths
    assert "/skills/incident-triage/references/runbook.md" in paths


@pytest.mark.asyncio
async def test_glob_scripts(backend):
    result = await backend.aglob("*.py")
    assert result.error is None
    paths = [e["path"] for e in result.matches]
    assert "/skills/incident-triage/scripts/check.py" in paths


# ---- write operations (blocked) ----


@pytest.mark.asyncio
async def test_write_blocked(backend):
    result = await backend.awrite("/skills/test/SKILL.md", "content")
    assert result.error is not None
    assert "read-only" in result.error.lower()


@pytest.mark.asyncio
async def test_edit_blocked(backend):
    result = await backend.aedit("/skills/test/SKILL.md", "old", "new")
    assert result.error is not None
    assert "read-only" in result.error.lower()


# ---- _parse_path tests ----


def test_parse_path_full():
    name, rel = SkillsStoreBackend._parse_path("/skills/my-skill/SKILL.md")
    assert name == "my-skill"
    assert rel == "SKILL.md"


def test_parse_path_nested_file():
    name, rel = SkillsStoreBackend._parse_path("/skills/my-skill/scripts/check.py")
    assert name == "my-skill"
    assert rel == "scripts/check.py"


def test_parse_path_no_file_defaults_to_skill_md():
    name, rel = SkillsStoreBackend._parse_path("/skills/my-skill")
    assert name == "my-skill"
    assert rel == "SKILL.md"


def test_parse_path_without_prefix():
    name, rel = SkillsStoreBackend._parse_path("my-skill/SKILL.md")
    assert name == "my-skill"
    assert rel == "SKILL.md"


def test_parse_path_skills_root():
    name, rel = SkillsStoreBackend._parse_path("skills")
    assert name is None


# ---- empty backend ----


@pytest.mark.asyncio
async def test_empty_backend_ls():
    backend = SkillsStoreBackend({})
    result = await backend.als("/skills/")
    assert result.error is None
    assert result.entries == []


@pytest.mark.asyncio
async def test_empty_backend_read():
    backend = SkillsStoreBackend({})
    result = await backend.aread("/skills/anything/SKILL.md")
    assert result.error is not None
