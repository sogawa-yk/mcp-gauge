"""プロンプト定義のユニットテスト。"""

import pytest
from mcp.types import GetPromptResult, TextContent

from mcp_gauge.prompts import PROMPTS, get_prompt


class TestPromptMetadata:
    """PROMPTSメタデータのテスト。"""

    def test_prompts_count(self) -> None:
        """3つのプロンプトが定義されている。"""
        assert len(PROMPTS) == 3

    def test_prompt_names(self) -> None:
        """全プロンプト名が正しい。"""
        names = {p.name for p in PROMPTS}
        assert names == {
            "mcp-server-dev-workflow",
            "fix-quality-issues",
            "regression-test",
        }

    def test_all_prompts_have_description(self) -> None:
        """全プロンプトにdescriptionがある。"""
        for prompt in PROMPTS:
            assert prompt.description is not None
            assert len(prompt.description) > 0

    def test_dev_workflow_arguments(self) -> None:
        """dev-workflowに必要な引数が定義されている。"""
        prompt = next(p for p in PROMPTS if p.name == "mcp-server-dev-workflow")
        assert prompt.arguments is not None
        arg_names = {a.name for a in prompt.arguments}
        assert "task_description" in arg_names
        assert "server_command" in arg_names
        assert "server_url" in arg_names

        task_arg = next(a for a in prompt.arguments if a.name == "task_description")
        assert task_arg.required is True

    def test_regression_test_arguments(self) -> None:
        """regression-testに必要な引数が定義されている。"""
        prompt = next(p for p in PROMPTS if p.name == "regression-test")
        assert prompt.arguments is not None
        arg_names = {a.name for a in prompt.arguments}
        assert "baseline_trace_id" in arg_names

        baseline_arg = next(
            a for a in prompt.arguments if a.name == "baseline_trace_id"
        )
        assert baseline_arg.required is True


class TestGetPrompt:
    """get_prompt関数のテスト。"""

    def test_unknown_prompt_raises(self) -> None:
        """存在しないプロンプト名でValueErrorが発生する。"""
        with pytest.raises(ValueError, match="不明なプロンプト"):
            get_prompt("nonexistent", None)


class TestDevWorkflowPrompt:
    """mcp-server-dev-workflowプロンプトのテスト。"""

    def test_returns_get_prompt_result(self) -> None:
        """GetPromptResultが返される。"""
        result = get_prompt(
            "mcp-server-dev-workflow",
            {"task_description": "テスト用サーバー"},
        )
        assert isinstance(result, GetPromptResult)
        assert len(result.messages) == 1
        assert result.messages[0].role == "user"

    def test_contains_task_description(self) -> None:
        """タスク説明がプロンプトに含まれる。"""
        result = get_prompt(
            "mcp-server-dev-workflow",
            {"task_description": "ファイル管理MCPサーバーのテスト"},
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "ファイル管理MCPサーバーのテスト" in content.text

    def test_contains_workflow_phases(self) -> None:
        """5つのPhaseがプロンプトに含まれる。"""
        result = get_prompt(
            "mcp-server-dev-workflow",
            {"task_description": "テスト"},
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "Phase 1" in content.text
        assert "Phase 2" in content.text
        assert "Phase 3" in content.text
        assert "Phase 4" in content.text
        assert "Phase 5" in content.text

    def test_contains_tool_names(self) -> None:
        """mcp-gaugeのツール名がプロンプトに含まれる。"""
        result = get_prompt(
            "mcp-server-dev-workflow",
            {"task_description": "テスト"},
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "gauge_lint" in content.text
        assert "gauge_connect" in content.text
        assert "gauge_proxy_call" in content.text
        assert "gauge_disconnect" in content.text
        assert "gauge_evaluate" in content.text
        assert "gauge_compare" in content.text
        assert "gauge_report" in content.text

    def test_with_server_url(self) -> None:
        """server_url指定時にHTTP接続情報が含まれる。"""
        result = get_prompt(
            "mcp-server-dev-workflow",
            {
                "task_description": "テスト",
                "server_url": "http://localhost:8000/mcp",
            },
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "Streamable HTTP" in content.text
        assert "http://localhost:8000/mcp" in content.text

    def test_with_server_command(self) -> None:
        """server_command指定時にstdio接続情報が含まれる。"""
        result = get_prompt(
            "mcp-server-dev-workflow",
            {
                "task_description": "テスト",
                "server_command": "python",
                "server_args": "server.py,--debug",
            },
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "stdio" in content.text
        assert "python" in content.text

    def test_without_connection_info(self) -> None:
        """接続情報未指定時に注意メッセージが含まれる。"""
        result = get_prompt(
            "mcp-server-dev-workflow",
            {"task_description": "テスト"},
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "接続情報が未指定" in content.text

    def test_none_arguments(self) -> None:
        """arguments=Noneでもエラーにならない。"""
        result = get_prompt("mcp-server-dev-workflow", None)
        assert isinstance(result, GetPromptResult)


class TestFixQualityPrompt:
    """fix-quality-issuesプロンプトのテスト。"""

    def test_returns_get_prompt_result(self) -> None:
        """GetPromptResultが返される。"""
        result = get_prompt("fix-quality-issues", None)
        assert isinstance(result, GetPromptResult)
        assert len(result.messages) == 1

    def test_contains_all_rules(self) -> None:
        """全lintルールの修正ガイドが含まれる。"""
        result = get_prompt("fix-quality-issues", None)
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "missing-param-description" in content.text
        assert "ambiguous-description" in content.text
        assert "missing-default-value" in content.text
        assert "missing-return-description" in content.text
        assert "description-too-short" in content.text
        assert "description-too-long" in content.text

    def test_with_lint_json(self) -> None:
        """lint_json指定時に結果がプロンプトに含まれる。"""
        lint_json = '{"total_issues": 2, "issues": []}'
        result = get_prompt(
            "fix-quality-issues",
            {"lint_json": lint_json},
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert lint_json in content.text


class TestRegressionTestPrompt:
    """regression-testプロンプトのテスト。"""

    def test_returns_get_prompt_result(self) -> None:
        """GetPromptResultが返される。"""
        result = get_prompt(
            "regression-test",
            {"baseline_trace_id": "abc-123"},
        )
        assert isinstance(result, GetPromptResult)
        assert len(result.messages) == 1

    def test_contains_baseline_id(self) -> None:
        """ベースラインtrace IDがプロンプトに含まれる。"""
        result = get_prompt(
            "regression-test",
            {"baseline_trace_id": "trace-xyz-789"},
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "trace-xyz-789" in content.text

    def test_contains_comparison_workflow(self) -> None:
        """比較ワークフローの手順が含まれる。"""
        result = get_prompt(
            "regression-test",
            {"baseline_trace_id": "abc"},
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "gauge_compare" in content.text
        assert "gauge_report" in content.text
        assert "overall_verdict" in content.text

    def test_contains_verdict_explanations(self) -> None:
        """verdict値の説明が含まれる。"""
        result = get_prompt(
            "regression-test",
            {"baseline_trace_id": "abc"},
        )
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "improved" in content.text
        assert "degraded" in content.text
        assert "unchanged" in content.text
        assert "mixed" in content.text

    def test_without_baseline_id(self) -> None:
        """baseline_trace_id未指定時に注意メッセージが含まれる。"""
        result = get_prompt("regression-test", None)
        content = result.messages[0].content
        assert isinstance(content, TextContent)
        assert "未指定" in content.text
