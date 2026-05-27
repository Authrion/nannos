"""Unit tests for ConditionalHumanInTheLoopMiddleware._apply_bypass_rule."""

import types

from agent_common.middleware.conditional_hitl import ConditionalHumanInTheLoopMiddleware


class TestApplyBypassRule:
    """Tests for the static _apply_bypass_rule method."""

    def _make_context(self, bypass_rules: dict | None = None) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            tool_bypass_rules=bypass_rules if bypass_rules is not None else {},
            _pending_bypass_rules=[],
        )

    def test_bypass_all(self):
        ctx = self._make_context()
        ConditionalHumanInTheLoopMiddleware._apply_bypass_rule(
            tool_name="execute",
            server_slug="_self",
            bypass_all=True,
            bypass_pattern=None,
            context=ctx,
        )
        assert ctx.tool_bypass_rules["execute::_self"] == {
            "bypass_all": True,
            "bypass_patterns": {},
        }
        assert len(ctx._pending_bypass_rules) == 1
        assert ctx._pending_bypass_rules[0]["key"] == "execute::_self"

    def test_bypass_pattern_matches_format(self):
        """Pattern from risk metadata: 'param matches `glob`'."""
        ctx = self._make_context()
        ConditionalHumanInTheLoopMiddleware._apply_bypass_rule(
            tool_name="execute",
            server_slug="_self",
            bypass_all=False,
            bypass_pattern="command matches `*python*`",
            context=ctx,
        )
        rule = ctx.tool_bypass_rules["execute::_self"]
        assert rule["bypass_all"] is False
        assert rule["bypass_patterns"] == {"command": ["*python*"]}
        assert len(ctx._pending_bypass_rules) == 1

    def test_bypass_pattern_colon_format(self):
        """Legacy format: 'param:glob'."""
        ctx = self._make_context()
        ConditionalHumanInTheLoopMiddleware._apply_bypass_rule(
            tool_name="execute",
            server_slug="_self",
            bypass_all=False,
            bypass_pattern="command:*python*",
            context=ctx,
        )
        rule = ctx.tool_bypass_rules["execute::_self"]
        assert rule["bypass_all"] is False
        assert rule["bypass_patterns"] == {"command": ["*python*"]}

    def test_bypass_pattern_merges_into_existing(self):
        ctx = self._make_context({"execute::_self": {"bypass_all": False, "bypass_patterns": {"command": ["*bash*"]}}})
        ConditionalHumanInTheLoopMiddleware._apply_bypass_rule(
            tool_name="execute",
            server_slug="_self",
            bypass_all=False,
            bypass_pattern="command matches `*python*`",
            context=ctx,
        )
        rule = ctx.tool_bypass_rules["execute::_self"]
        assert rule["bypass_patterns"]["command"] == ["*bash*", "*python*"]

    def test_unparseable_pattern_does_not_crash(self):
        """If bypass_pattern can't be parsed, no rule is stored and no KeyError."""
        ctx = self._make_context()
        ConditionalHumanInTheLoopMiddleware._apply_bypass_rule(
            tool_name="execute",
            server_slug="_self",
            bypass_all=False,
            bypass_pattern="something unparseable",
            context=ctx,
        )
        assert "execute::_self" not in ctx.tool_bypass_rules
        assert len(ctx._pending_bypass_rules) == 0

    def test_no_context_bypass_rules_is_noop(self):
        ctx = types.SimpleNamespace(tool_bypass_rules=None)
        # Should not raise
        ConditionalHumanInTheLoopMiddleware._apply_bypass_rule(
            tool_name="execute",
            server_slug="_self",
            bypass_all=True,
            bypass_pattern=None,
            context=ctx,
        )

    def test_duplicate_pattern_not_added_twice(self):
        ctx = self._make_context()
        for _ in range(2):
            ConditionalHumanInTheLoopMiddleware._apply_bypass_rule(
                tool_name="execute",
                server_slug="_self",
                bypass_all=False,
                bypass_pattern="command matches `*python*`",
                context=ctx,
            )
        rule = ctx.tool_bypass_rules["execute::_self"]
        assert rule["bypass_patterns"]["command"] == ["*python*"]


class TestIsBypassed:
    """Tests for the static _is_bypassed method."""

    def test_no_rule_returns_false(self):
        assert (
            ConditionalHumanInTheLoopMiddleware._is_bypassed(
                tool_name="execute",
                server_slug="_self",
                args={"command": "python3 script.py"},
                bypass_rules={},
            )
            is False
        )

    def test_bypass_all_returns_true(self):
        rules = {"execute::_self": {"bypass_all": True, "bypass_patterns": {}}}
        assert (
            ConditionalHumanInTheLoopMiddleware._is_bypassed(
                tool_name="execute",
                server_slug="_self",
                args={"command": "anything"},
                bypass_rules=rules,
            )
            is True
        )

    def test_matching_glob_pattern_returns_true(self):
        rules = {"execute::_self": {"bypass_all": False, "bypass_patterns": {"command": ["*python*"]}}}
        assert (
            ConditionalHumanInTheLoopMiddleware._is_bypassed(
                tool_name="execute",
                server_slug="_self",
                args={"command": "python3 /home/ubuntu/script.py"},
                bypass_rules=rules,
            )
            is True
        )

    def test_non_matching_glob_pattern_returns_false(self):
        rules = {"execute::_self": {"bypass_all": False, "bypass_patterns": {"command": ["*python*"]}}}
        assert (
            ConditionalHumanInTheLoopMiddleware._is_bypassed(
                tool_name="execute",
                server_slug="_self",
                args={"command": "rm -rf /"},
                bypass_rules=rules,
            )
            is False
        )

    def test_different_server_slug_not_matched(self):
        rules = {"execute::my-server": {"bypass_all": True, "bypass_patterns": {}}}
        assert (
            ConditionalHumanInTheLoopMiddleware._is_bypassed(
                tool_name="execute",
                server_slug="_self",
                args={"command": "python3 foo.py"},
                bypass_rules=rules,
            )
            is False
        )

    def test_missing_arg_value_returns_false(self):
        rules = {"execute::_self": {"bypass_all": False, "bypass_patterns": {"command": ["*python*"]}}}
        assert (
            ConditionalHumanInTheLoopMiddleware._is_bypassed(
                tool_name="execute",
                server_slug="_self",
                args={},  # no "command" arg
                bypass_rules=rules,
            )
            is False
        )

    def test_roundtrip_apply_then_check(self):
        """Apply a rule via _apply_bypass_rule, then verify _is_bypassed uses it."""
        ctx = types.SimpleNamespace(tool_bypass_rules={}, _pending_bypass_rules=[])
        ConditionalHumanInTheLoopMiddleware._apply_bypass_rule(
            tool_name="execute",
            server_slug="_self",
            bypass_all=False,
            bypass_pattern="command matches `*python*`",
            context=ctx,
        )
        assert (
            ConditionalHumanInTheLoopMiddleware._is_bypassed(
                tool_name="execute",
                server_slug="_self",
                args={"command": "python3 /home/ubuntu/skills/printing/scripts/print.py"},
                bypass_rules=ctx.tool_bypass_rules,
            )
            is True
        )
        assert (
            ConditionalHumanInTheLoopMiddleware._is_bypassed(
                tool_name="execute",
                server_slug="_self",
                args={"command": "ls -la"},
                bypass_rules=ctx.tool_bypass_rules,
            )
            is False
        )
