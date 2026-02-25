"""EvaluateEngineのユニットテスト。"""

from unittest.mock import AsyncMock

import pytest

from mcp_gauge.engines.evaluate import EvaluateEngine
from mcp_gauge.models.scenario import SuccessCriteria
from mcp_gauge.models.trace import SessionStatus, TraceSession, TraceSummary


def _make_summary(
    total_calls: int = 3,
    tool_call_sequence: list[str] | None = None,
    error_count: int = 0,
) -> TraceSummary:
    """テスト用のTraceSummaryを作成する。"""
    return TraceSummary(
        total_calls=total_calls,
        unique_tools=len(set(tool_call_sequence or ["create", "list"])),
        error_count=error_count,
        redundant_calls=0,
        total_duration_ms=300.0,
        recovery_steps=0,
        tool_call_sequence=tool_call_sequence or ["create", "list", "get"],
    )


def _make_session(task_success: bool | None = None) -> TraceSession:
    """テスト用のTraceSessionを作成する。"""
    return TraceSession(
        id="sess-001",
        server_command="python -m server",
        server_args=[],
        status=SessionStatus.COMPLETED,
        started_at="2026-01-01T00:00:00Z",
        task_success=task_success,
    )


@pytest.fixture
def mock_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.get_summary = AsyncMock(return_value=_make_summary())
    storage.get_session = AsyncMock(return_value=_make_session(True))
    return storage


@pytest.fixture
def engine(mock_storage: AsyncMock) -> EvaluateEngine:
    return EvaluateEngine(mock_storage)


class TestEvaluateCriteria:
    """_evaluate_criteriaのテスト。"""

    def test_max_steps_passed(self, engine: EvaluateEngine):
        """max_steps以内で合格。"""
        criteria = SuccessCriteria(max_steps=5)
        summary = _make_summary(total_calls=3)
        result = engine._evaluate_criteria(summary, criteria, True)
        assert result.max_steps is not None
        assert result.max_steps["passed"] is True

    def test_max_steps_failed(self, engine: EvaluateEngine):
        """max_steps超過で不合格。"""
        criteria = SuccessCriteria(max_steps=2)
        summary = _make_summary(total_calls=3)
        result = engine._evaluate_criteria(summary, criteria, True)
        assert result.max_steps is not None
        assert result.max_steps["passed"] is False

    def test_required_tools_passed(self, engine: EvaluateEngine):
        """必須ツールが全て呼ばれて合格。"""
        criteria = SuccessCriteria(required_tools=["create", "list"])
        summary = _make_summary(tool_call_sequence=["create", "list", "get"])
        result = engine._evaluate_criteria(summary, criteria, True)
        assert result.required_tools is not None
        assert result.required_tools["passed"] is True

    def test_required_tools_failed(self, engine: EvaluateEngine):
        """必須ツールが不足で不合格。"""
        criteria = SuccessCriteria(required_tools=["create", "delete"])
        summary = _make_summary(tool_call_sequence=["create", "list"])
        result = engine._evaluate_criteria(summary, criteria, True)
        assert result.required_tools is not None
        assert result.required_tools["passed"] is False
        assert "delete" in result.required_tools["missing"]

    def test_forbidden_tools_passed(self, engine: EvaluateEngine):
        """禁止ツールが呼ばれず合格。"""
        criteria = SuccessCriteria(forbidden_tools=["delete"])
        summary = _make_summary(tool_call_sequence=["create", "list"])
        result = engine._evaluate_criteria(summary, criteria, True)
        assert result.forbidden_tools is not None
        assert result.forbidden_tools["passed"] is True

    def test_forbidden_tools_failed(self, engine: EvaluateEngine):
        """禁止ツールが呼ばれて不合格。"""
        criteria = SuccessCriteria(forbidden_tools=["list"])
        summary = _make_summary(tool_call_sequence=["create", "list"])
        result = engine._evaluate_criteria(summary, criteria, True)
        assert result.forbidden_tools is not None
        assert result.forbidden_tools["passed"] is False

    def test_must_succeed_passed(self, engine: EvaluateEngine):
        """タスク成功で合格。"""
        criteria = SuccessCriteria(must_succeed=True)
        result = engine._evaluate_criteria(_make_summary(), criteria, True)
        assert result.must_succeed is not None
        assert result.must_succeed["passed"] is True

    def test_must_succeed_failed(self, engine: EvaluateEngine):
        """タスク失敗で不合格。"""
        criteria = SuccessCriteria(must_succeed=True)
        result = engine._evaluate_criteria(_make_summary(), criteria, False)
        assert result.must_succeed is not None
        assert result.must_succeed["passed"] is False

    def test_no_criteria(self, engine: EvaluateEngine):
        """条件なしの場合は全てNone。"""
        criteria = SuccessCriteria(must_succeed=False)
        result = engine._evaluate_criteria(_make_summary(), criteria, True)
        assert result.max_steps is None
        assert result.required_tools is None
        assert result.forbidden_tools is None
        assert result.must_succeed is None

    def test_all_criteria_combined(self, engine: EvaluateEngine):
        """全条件を組み合わせて評価。"""
        criteria = SuccessCriteria(
            max_steps=10,
            required_tools=["create"],
            forbidden_tools=["delete"],
            must_succeed=True,
        )
        summary = _make_summary(
            total_calls=3,
            tool_call_sequence=["create", "list", "get"],
        )
        result = engine._evaluate_criteria(summary, criteria, True)
        assert result.max_steps is not None
        assert result.max_steps["passed"] is True
        assert result.required_tools is not None
        assert result.required_tools["passed"] is True
        assert result.forbidden_tools is not None
        assert result.forbidden_tools["passed"] is True
        assert result.must_succeed is not None
        assert result.must_succeed["passed"] is True


class TestEvaluateEngine:
    """EvaluateEngine.evaluateのテスト。"""

    async def test_evaluate_passed(
        self, engine: EvaluateEngine, mock_storage: AsyncMock
    ):
        """全条件クリアでpassedがTrue。"""
        result = await engine.evaluate(
            "sess-001",
            SuccessCriteria(max_steps=10, must_succeed=True),
            task_success=True,
        )
        assert result["passed"] is True
        assert result["task_success"] is True

    async def test_evaluate_failed(
        self, engine: EvaluateEngine, mock_storage: AsyncMock
    ):
        """条件不合格でpassedがFalse。"""
        mock_storage.get_summary.return_value = _make_summary(total_calls=10)
        result = await engine.evaluate(
            "sess-001",
            SuccessCriteria(max_steps=5),
        )
        assert result["passed"] is False

    async def test_evaluate_uses_session_task_success(
        self, engine: EvaluateEngine, mock_storage: AsyncMock
    ):
        """task_success未指定時はセッションの値を使用。"""
        mock_storage.get_session.return_value = _make_session(task_success=True)
        result = await engine.evaluate(
            "sess-001",
            SuccessCriteria(must_succeed=True),
        )
        assert result["task_success"] is True
