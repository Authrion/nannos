"""Unit tests for the skills registry router and service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from console_backend.models.skills_registry import (
    SkillAuditEntry,
    SkillAuditResponse,
    SkillDetailResponse,
    SkillFile,
    SkillSearchResponse,
    SkillSearchResult,
)
from console_backend.models.user import User, UserRole
from console_backend.routers.skills_registry_router import browse_repo, get_skill_audit, get_skill_detail, search_skills


def _make_user(**overrides) -> User:
    """Create a test User model."""
    defaults = {
        "id": "user-id-1",
        "sub": "user-sub-1",
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "role": UserRole.MEMBER,
    }
    defaults.update(overrides)
    return User(**defaults)


# --- Search endpoint tests ---


class TestSearchSkills:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        mock_results = [
            SkillSearchResult(
                id="vercel-labs/agent-skills/next-js-development",
                slug="next-js-development",
                name="Next.js Development",
                source="vercel-labs/agent-skills",
                installs=1500,
                url="https://skills.sh/vercel-labs/agent-skills/next-js-development",
                source_type="github",
                install_url="https://github.com/vercel-labs/agent-skills",
            )
        ]

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.search_skills",
            new_callable=AsyncMock,
            return_value=(mock_results, "fuzzy"),
        ) as mock_search:
            result = await search_skills(q="nextjs", limit=10, user=_make_user())

            assert isinstance(result, SkillSearchResponse)
            assert len(result.data) == 1
            assert result.data[0].name == "Next.js Development"
            assert result.query == "nextjs"
            assert result.count == 1
            assert result.search_type == "fuzzy"
            mock_search.assert_called_once_with(query="nextjs", limit=10)

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.search_skills",
            new_callable=AsyncMock,
            return_value=([], None),
        ):
            result = await search_skills(q="nonexistent-skill-xyz", limit=10, user=_make_user())

            assert isinstance(result, SkillSearchResponse)
            assert len(result.data) == 0
            assert result.count == 0


# --- Browse endpoint tests ---


class TestBrowseRepo:
    @pytest.mark.asyncio
    async def test_browse_valid_repo(self):
        mock_results = [
            SkillSearchResult(
                id="anthropics/skills/code-review",
                slug="code-review",
                name="code-review",
                source="anthropics/skills",
                installs=0,
                url="https://github.com/anthropics/skills/tree/main/skills/code-review",
                source_type="github",
            )
        ]

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.browse_repo",
            new_callable=AsyncMock,
            return_value=mock_results,
        ) as mock_browse:
            result = await browse_repo(repo="anthropics/skills", ref="main", user=_make_user())

            assert isinstance(result, SkillSearchResponse)
            assert len(result.data) == 1
            assert result.data[0].slug == "code-review"
            mock_browse.assert_called_once_with(repo="anthropics/skills", ref="main")

    @pytest.mark.asyncio
    async def test_browse_invalid_repo_format(self):
        with pytest.raises(Exception) as exc_info:
            await browse_repo(repo="invalid-no-slash", ref="main", user=_make_user())

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_browse_empty_repo(self):
        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.browse_repo",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await browse_repo(repo="empty/repo", ref="main", user=_make_user())

            assert result.count == 0


# --- Detail endpoint tests ---


class TestGetSkillDetail:
    @pytest.mark.asyncio
    async def test_detail_found(self):
        mock_detail = SkillDetailResponse(
            id="vercel-labs/agent-skills/next-js-development",
            source="vercel-labs/agent-skills",
            slug="next-js-development",
            installs=24531,
            hash="a1b2c3d4e5f6",
            files=[SkillFile(path="SKILL.md", contents="# Next.js Development")],
        )

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ):
            result = await get_skill_detail(
                skill_id="vercel-labs/agent-skills/next-js-development",
                user=_make_user(),
            )

            assert isinstance(result, SkillDetailResponse)
            assert result.slug == "next-js-development"
            assert result.hash == "a1b2c3d4e5f6"
            assert len(result.files) == 1

    @pytest.mark.asyncio
    async def test_detail_not_found(self):
        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_detail",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(Exception) as exc_info:
                await get_skill_detail(skill_id="nonexistent/skill", user=_make_user())

            assert exc_info.value.status_code == 404


# --- Audit endpoint tests ---


class TestGetSkillAudit:
    @pytest.mark.asyncio
    async def test_audit_found(self):
        mock_audit = SkillAuditResponse(
            id="vercel-labs/agent-skills/next-js-development",
            source="vercel-labs/agent-skills",
            slug="next-js-development",
            audits=[
                SkillAuditEntry(
                    provider="Gen Agent Trust Hub",
                    slug="agent-trust-hub",
                    status="pass",
                    summary="No risks detected",
                    audited_at="2026-04-15T12:00:00.000Z",
                    risk_level="LOW",
                )
            ],
        )

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_audit",
            new_callable=AsyncMock,
            return_value=mock_audit,
        ):
            result = await get_skill_audit(
                skill_id="vercel-labs/agent-skills/next-js-development",
                user=_make_user(),
            )

            assert isinstance(result, SkillAuditResponse)
            assert len(result.audits) == 1
            assert result.audits[0].status == "pass"
            assert result.audits[0].risk_level == "LOW"

    @pytest.mark.asyncio
    async def test_audit_not_found(self):
        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_audit",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(Exception) as exc_info:
                await get_skill_audit(skill_id="nonexistent/skill", user=_make_user())

            assert exc_info.value.status_code == 404


# --- Service unit tests ---


class TestSkillsRegistryService:
    @pytest.mark.asyncio
    async def test_search_skills_calls_skills_sh(self):
        """Verify service correctly calls skills.sh and parses response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "owner/repo/skill-name",
                    "slug": "skill-name",
                    "name": "Skill Name",
                    "source": "owner/repo",
                    "installs": 42,
                    "url": "https://skills.sh/s/skill-name",
                    "sourceType": "github",
                }
            ]
        }

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            from console_backend.services.skills_registry_service import SkillsRegistryService

            service = SkillsRegistryService()
            results, search_type = await service.search_skills("test query", limit=10)

            assert len(results) == 1
            assert results[0].id == "owner/repo/skill-name"
            assert results[0].installs == 42

    @pytest.mark.asyncio
    async def test_search_skills_handles_api_error(self):
        """Verify service returns empty list on API error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            from console_backend.services.skills_registry_service import SkillsRegistryService

            service = SkillsRegistryService()
            results, search_type = await service.search_skills("test", limit=10)

            assert results == []
            assert search_type is None

    @pytest.mark.asyncio
    async def test_search_skills_skips_short_queries(self):
        """Verify service rejects queries under 2 characters."""
        from console_backend.services.skills_registry_service import SkillsRegistryService

        service = SkillsRegistryService()
        results, search_type = await service.search_skills("x", limit=10)
        assert results == []
        assert search_type is None

    @pytest.mark.asyncio
    async def test_search_skills_filters_duplicates(self):
        """Verify service skips items marked as duplicates."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "owner/repo/skill-1",
                    "slug": "skill-1",
                    "name": "Skill 1",
                    "source": "owner/repo",
                    "isDuplicate": False,
                },
                {
                    "id": "fork/repo/skill-1",
                    "slug": "skill-1",
                    "name": "Skill 1 (fork)",
                    "source": "fork/repo",
                    "isDuplicate": True,
                },
            ]
        }

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.get = AsyncMock(return_value=mock_response)
            client_instance.__aenter__ = AsyncMock(return_value=client_instance)
            client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = client_instance

            from console_backend.services.skills_registry_service import SkillsRegistryService

            service = SkillsRegistryService()
            results, search_type = await service.search_skills("skill", limit=10)

            assert len(results) == 1
            assert results[0].id == "owner/repo/skill-1"

    def test_parse_repo_valid(self):
        from console_backend.services.skills_registry_service import SkillsRegistryService

        service = SkillsRegistryService()
        owner, repo = service._parse_repo("anthropics/skills")
        assert owner == "anthropics"
        assert repo == "skills"

    def test_parse_repo_invalid(self):
        from console_backend.services.skills_registry_service import SkillsRegistryService

        service = SkillsRegistryService()
        with pytest.raises(ValueError):
            service._parse_repo("no-slash-here")

    def test_extract_description_from_frontmatter(self):
        from console_backend.services.skills_registry_service import SkillsRegistryService

        service = SkillsRegistryService()

        content = '---\nname: my-skill\ndescription: "A great skill for testing"\n---\n# Content'
        assert service._extract_description_from_frontmatter(content) == "A great skill for testing"

    def test_extract_description_no_frontmatter(self):
        from console_backend.services.skills_registry_service import SkillsRegistryService

        service = SkillsRegistryService()

        content = "# Just a markdown file\nNo frontmatter here."
        assert service._extract_description_from_frontmatter(content) == ""


# --- Import endpoint tests ---


class TestImportSkill:
    """Tests for POST /api/v1/skills/registry/import."""

    def _mock_request(self, playbook_service):
        """Create a mock request with playbook_service on app state."""
        request = MagicMock()
        request.app.state.playbook_service = playbook_service
        return request

    def _mock_playbook_service(self, skill_exists=False):
        """Create a mock playbook service."""
        service = MagicMock()
        service.is_available = True
        service.get_skill = AsyncMock(return_value="existing content" if skill_exists else None)
        service.put_skill_with_files = AsyncMock(return_value=None)
        return service

    @pytest.mark.asyncio
    async def test_import_from_skills_sh(self):
        """Import a skill from skills.sh by ID."""
        from console_backend.models.skills_registry import (
            SkillDetailResponse,
            SkillImportRequest,
            SkillImportResponse,
        )
        from console_backend.routers.skills_registry_router import import_skill

        mock_detail = SkillDetailResponse(
            id="vercel-labs/agent-skills/next-js-development",
            source="vercel-labs/agent-skills",
            slug="next-js-development",
            installs=1500,
            hash="abc123",
            files=[
                SkillFile(path="SKILL.md", contents="---\nname: next-js-development\n---\n\n# Next.js"),
                SkillFile(path="examples/config.ts", contents="export default {}"),
            ],
        )

        playbook_service = self._mock_playbook_service()
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(
            id="vercel-labs/agent-skills/next-js-development",
            agent="orchestrator",
            scope="personal",
        )

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ):
            result = await import_skill(body=body, request=request, user=_make_user())

        assert isinstance(result, SkillImportResponse)
        assert result.skill_name == "next-js-development"
        assert result.agent == "orchestrator"
        assert result.scope == "personal"
        assert result.source.type == "skills.sh"
        assert result.source.hash == "abc123"
        assert result.files_count == 2
        assert result.overwritten is False

        playbook_service.put_skill_with_files.assert_called_once_with(
            user_id="user-id-1",
            agent_name="orchestrator",
            skill_name="next-js-development",
            scope="personal",
            content="---\nname: next-js-development\n---\n\n# Next.js",
            files=[{"path": "examples/config.ts", "content": "export default {}"}],
            group_id=None,
            replace_files=False,
        )

    @pytest.mark.asyncio
    async def test_import_from_github(self):
        """Import a skill from GitHub by repo+skill."""
        from console_backend.models.skills_registry import (
            GitHubSkillDetail,
            SkillImportRequest,
            SkillImportResponse,
        )
        from console_backend.routers.skills_registry_router import import_skill

        mock_github = GitHubSkillDetail(
            files=[
                SkillFile(path="SKILL.md", contents="---\nname: planning\n---\n\n# Planning Skill"),
            ],
            tree_sha="def456",
        )

        playbook_service = self._mock_playbook_service()
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(
            repo="OthmanAdi/planning-with-files",
            skill="planning-with-files",
            agent="orchestrator",
            scope="personal",
        )

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.fetch_skill_files_from_github",
            new_callable=AsyncMock,
            return_value=mock_github,
        ):
            result = await import_skill(body=body, request=request, user=_make_user())

        assert isinstance(result, SkillImportResponse)
        assert result.skill_name == "planning-with-files"
        assert result.source.type == "github"
        assert result.source.repo == "OthmanAdi/planning-with-files"
        assert result.source.hash == "def456"
        assert result.files_count == 1

        playbook_service.put_skill_with_files.assert_called_once_with(
            user_id="user-id-1",
            agent_name="orchestrator",
            skill_name="planning-with-files",
            scope="personal",
            content="---\nname: planning\n---\n\n# Planning Skill",
            files=None,
            group_id=None,
            replace_files=False,
        )

    @pytest.mark.asyncio
    async def test_import_conflict_without_overwrite(self):
        """Returns 409 when skill exists and overwrite is False."""
        from console_backend.models.skills_registry import SkillDetailResponse, SkillImportRequest
        from console_backend.routers.skills_registry_router import import_skill

        mock_detail = SkillDetailResponse(
            id="owner/repo/my-skill",
            source="owner/repo",
            slug="my-skill",
            installs=0,
            hash="hash1",
            files=[SkillFile(path="SKILL.md", contents="# Skill content")],
        )

        playbook_service = self._mock_playbook_service(skill_exists=True)
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(id="owner/repo/my-skill", agent="orchestrator", scope="personal")

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ):
            with pytest.raises(Exception) as exc_info:
                await import_skill(body=body, request=request, user=_make_user())

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_import_overwrite_existing(self):
        """Overwrites existing skill when overwrite=True."""
        from console_backend.models.skills_registry import (
            SkillDetailResponse,
            SkillImportRequest,
            SkillImportResponse,
        )
        from console_backend.routers.skills_registry_router import import_skill

        mock_detail = SkillDetailResponse(
            id="owner/repo/my-skill",
            source="owner/repo",
            slug="my-skill",
            installs=0,
            hash="hash2",
            files=[SkillFile(path="SKILL.md", contents="# Updated content")],
        )

        playbook_service = self._mock_playbook_service(skill_exists=True)
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(id="owner/repo/my-skill", agent="orchestrator", scope="personal", overwrite=True)

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ):
            result = await import_skill(body=body, request=request, user=_make_user())

        assert isinstance(result, SkillImportResponse)
        assert result.overwritten is True
        playbook_service.put_skill_with_files.assert_called_once()
        call_kwargs = playbook_service.put_skill_with_files.call_args[1]
        assert call_kwargs["replace_files"] is True

    @pytest.mark.asyncio
    async def test_import_skill_not_found_skills_sh(self):
        """Returns 404 when skills.sh skill doesn't exist."""
        from console_backend.models.skills_registry import SkillImportRequest
        from console_backend.routers.skills_registry_router import import_skill

        playbook_service = self._mock_playbook_service()
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(id="nonexistent/repo/skill", agent="orchestrator", scope="personal")

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_detail",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(Exception) as exc_info:
                await import_skill(body=body, request=request, user=_make_user())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_import_skill_not_found_github(self):
        """Returns 404 when GitHub skill doesn't exist."""
        from console_backend.models.skills_registry import SkillImportRequest
        from console_backend.routers.skills_registry_router import import_skill

        playbook_service = self._mock_playbook_service()
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(repo="owner/repo", skill="nonexistent-skill", agent="orchestrator", scope="personal")

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.fetch_skill_files_from_github",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(Exception) as exc_info:
                await import_skill(body=body, request=request, user=_make_user())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_import_no_skill_md(self):
        """Returns 422 when skill has no SKILL.md file."""
        from console_backend.models.skills_registry import SkillDetailResponse, SkillImportRequest
        from console_backend.routers.skills_registry_router import import_skill

        mock_detail = SkillDetailResponse(
            id="owner/repo/broken-skill",
            source="owner/repo",
            slug="broken-skill",
            installs=0,
            hash="hash3",
            files=[SkillFile(path="README.md", contents="# Not a skill")],
        )

        playbook_service = self._mock_playbook_service()
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(id="owner/repo/broken-skill", agent="orchestrator", scope="personal")

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ):
            with pytest.raises(Exception) as exc_info:
                await import_skill(body=body, request=request, user=_make_user())

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_import_missing_source_params(self):
        """Returns 400 when neither id nor repo+skill is provided."""
        from console_backend.models.skills_registry import SkillImportRequest
        from console_backend.routers.skills_registry_router import import_skill

        playbook_service = self._mock_playbook_service()
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(agent="orchestrator", scope="personal")

        with pytest.raises(Exception) as exc_info:
            await import_skill(body=body, request=request, user=_make_user())

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_import_group_scope(self):
        """Import with group scope passes group_id to playbook service."""
        from console_backend.models.skills_registry import (
            SkillDetailResponse,
            SkillImportRequest,
        )
        from console_backend.routers.skills_registry_router import import_skill

        mock_detail = SkillDetailResponse(
            id="owner/repo/team-skill",
            source="owner/repo",
            slug="team-skill",
            installs=0,
            hash="hash4",
            files=[SkillFile(path="SKILL.md", contents="# Team skill")],
        )

        playbook_service = self._mock_playbook_service()
        request = self._mock_request(playbook_service)

        body = SkillImportRequest(
            id="owner/repo/team-skill",
            agent="orchestrator",
            scope="group",
            group_id="group-123",
        )

        with patch(
            "console_backend.routers.skills_registry_router.skills_registry_service.get_skill_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ):
            result = await import_skill(body=body, request=request, user=_make_user())

        assert result.scope == "group"
        call_kwargs = playbook_service.put_skill_with_files.call_args[1]
        assert call_kwargs["group_id"] == "group-123"
        assert call_kwargs["scope"] == "group"
