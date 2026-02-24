"""ScenarioRunnerのユニットテスト（成功条件評価ロジック）。"""

import pytest

from mcp_gauge.config import GaugeConfig
from mcp_gauge.engines.scenario import ScenarioRunner
from mcp_gauge.models.scenario import SuccessCriteria
from mcp_gauge.models.trace import TraceSummary


def _make_summary(
    total_calls: int = 3,
    tool_sequence: list[str] | None = None,
) -> TraceSummary:
    seq = tool_sequence or ["create", "list", "get"]
    return TraceSummary(
        total_calls=total_calls,
        unique_tools=len(set(seq)),
        error_count=0,
        redundant_calls=0,
        total_duration_ms=300.0,
        recovery_steps=0,
        tool_call_sequence=seq,
    )


@pytest.fixture
def runner():
    config = GaugeConfig(
        db_path=":memory:",
        anthropic_api_key="test-key",
        anthropic_model="test-model",
        mcp_timeout_sec=10,
    )
    return ScenarioRunner(config)


class TestEvaluateCriteria:
    """_evaluate_criteriaメソッドのテスト。"""

    def test_max_steps_passed(self, runner):
        """ステップ数が上限以内なら合格。"""
        summary = _make_summary(total_calls=3)
        criteria = SuccessCriteria(max_steps=5)
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.max_steps is not None
        assert result.max_steps["passed"] is True
        assert result.max_steps["actual"] == 3

    def test_max_steps_failed(self, runner):
        """ステップ数が上限超過なら不合格。"""
        summary = _make_summary(total_calls=10)
        criteria = SuccessCriteria(max_steps=5)
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.max_steps["passed"] is False

    def test_required_tools_passed(self, runner):
        """必須ツールが全て呼ばれていれば合格。"""
        summary = _make_summary(tool_sequence=["create", "list", "get"])
        criteria = SuccessCriteria(required_tools=["create", "list"])
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.required_tools is not None
        assert result.required_tools["passed"] is True
        assert result.required_tools["missing"] == []

    def test_required_tools_failed(self, runner):
        """必須ツールが不足していれば不合格。"""
        summary = _make_summary(tool_sequence=["create", "get"])
        criteria = SuccessCriteria(required_tools=["create", "list", "delete"])
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.required_tools["passed"] is False
        assert "list" in result.required_tools["missing"]
        assert "delete" in result.required_tools["missing"]

    def test_forbidden_tools_passed(self, runner):
        """禁止ツールが呼ばれていなければ合格。"""
        summary = _make_summary(tool_sequence=["create", "list"])
        criteria = SuccessCriteria(forbidden_tools=["delete", "destroy"])
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.forbidden_tools is not None
        assert result.forbidden_tools["passed"] is True

    def test_forbidden_tools_failed(self, runner):
        """禁止ツールが呼ばれていれば不合格。"""
        summary = _make_summary(tool_sequence=["create", "delete"])
        criteria = SuccessCriteria(forbidden_tools=["delete"])
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.forbidden_tools["passed"] is False
        assert "delete" in result.forbidden_tools["violated"]

    def test_must_succeed_passed(self, runner):
        """タスク成功が必須で成功していれば合格。"""
        summary = _make_summary()
        criteria = SuccessCriteria(must_succeed=True)
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.must_succeed is not None
        assert result.must_succeed["passed"] is True

    def test_must_succeed_failed(self, runner):
        """タスク成功が必須で失敗していれば不合格。"""
        summary = _make_summary()
        criteria = SuccessCriteria(must_succeed=True)
        result = runner._evaluate_criteria(summary, criteria, task_success=False)
        assert result.must_succeed["passed"] is False

    def test_no_criteria(self, runner):
        """条件未設定の場合はNone。"""
        summary = _make_summary()
        criteria = SuccessCriteria(must_succeed=False)
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.max_steps is None
        assert result.required_tools is None
        assert result.forbidden_tools is None

    def test_all_criteria_combined(self, runner):
        """全条件を組み合わせたテスト。"""
        summary = _make_summary(
            total_calls=3,
            tool_sequence=["create", "list", "get"],
        )
        criteria = SuccessCriteria(
            max_steps=5,
            required_tools=["create", "list"],
            forbidden_tools=["delete"],
            must_succeed=True,
        )
        result = runner._evaluate_criteria(summary, criteria, task_success=True)
        assert result.max_steps["passed"] is True
        assert result.required_tools["passed"] is True
        assert result.forbidden_tools["passed"] is True
        assert result.must_succeed["passed"] is True
