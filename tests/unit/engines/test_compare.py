"""CompareEngineのユニットテスト。"""

from unittest.mock import AsyncMock

import pytest

from mcp_gauge.engines.compare import CompareEngine
from mcp_gauge.models.trace import (
    SessionStatus,
    TraceSession,
    TraceSummary,
)


@pytest.fixture
def mock_storage():
    return AsyncMock()


@pytest.fixture
def engine(mock_storage):
    return CompareEngine(mock_storage)


def _make_session(session_id: str, task_success: bool = True) -> TraceSession:
    return TraceSession(
        id=session_id,
        server_command="python -m server",
        server_args=[],
        status=SessionStatus.COMPLETED,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
        task_success=task_success,
    )


def _make_summary(
    total_calls: int = 5,
    error_count: int = 1,
    redundant_calls: int = 1,
    total_duration_ms: float = 1000.0,
    recovery_steps: int = 1,
) -> TraceSummary:
    return TraceSummary(
        total_calls=total_calls,
        unique_tools=3,
        error_count=error_count,
        redundant_calls=redundant_calls,
        total_duration_ms=total_duration_ms,
        recovery_steps=recovery_steps,
        tool_call_sequence=["a"] * total_calls,
    )


class TestCompareEngine:
    """CompareEngineのテスト。"""

    async def test_improved(self, engine, mock_storage):
        """改善された場合にimprovedと判定する。"""
        mock_storage.get_session.side_effect = [
            _make_session("base"),
            _make_session("curr"),
        ]
        mock_storage.get_summary.side_effect = [
            _make_summary(
                total_calls=7,
                error_count=2,
                redundant_calls=2,
            ),
            _make_summary(
                total_calls=4,
                error_count=0,
                redundant_calls=0,
            ),
        ]

        result = await engine.compare("base", "curr")
        assert result.overall_verdict == "improved"
        assert result.metrics["total_calls"].verdict == "improved"
        assert result.metrics["error_count"].verdict == "improved"

    async def test_degraded(self, engine, mock_storage):
        """悪化した場合にdegradedと判定する。"""
        mock_storage.get_session.side_effect = [
            _make_session("base"),
            _make_session("curr"),
        ]
        mock_storage.get_summary.side_effect = [
            _make_summary(
                total_calls=3,
                error_count=0,
                redundant_calls=0,
            ),
            _make_summary(
                total_calls=7,
                error_count=3,
                redundant_calls=2,
            ),
        ]

        result = await engine.compare("base", "curr")
        assert result.overall_verdict == "degraded"

    async def test_unchanged(self, engine, mock_storage):
        """変化なしの場合にunchangedと判定する。"""
        summary = _make_summary()
        mock_storage.get_session.side_effect = [
            _make_session("base"),
            _make_session("curr"),
        ]
        mock_storage.get_summary.side_effect = [
            summary,
            summary,
        ]

        result = await engine.compare("base", "curr")
        assert result.overall_verdict == "unchanged"

    async def test_mixed(self, engine, mock_storage):
        """一部改善・一部悪化の場合にmixedと判定する。"""
        mock_storage.get_session.side_effect = [
            _make_session("base"),
            _make_session("curr"),
        ]
        mock_storage.get_summary.side_effect = [
            _make_summary(
                total_calls=5,
                error_count=2,
                total_duration_ms=1000.0,
            ),
            _make_summary(
                total_calls=3,
                error_count=2,
                total_duration_ms=2000.0,
            ),
        ]

        result = await engine.compare("base", "curr")
        assert result.overall_verdict == "mixed"

    async def test_task_success_changed(self, engine, mock_storage):
        """タスク成功の変化を検出する。"""
        mock_storage.get_session.side_effect = [
            _make_session("base", task_success=False),
            _make_session("curr", task_success=True),
        ]
        mock_storage.get_summary.side_effect = [
            _make_summary(),
            _make_summary(),
        ]

        result = await engine.compare("base", "curr")
        assert result.metrics["task_success"].verdict == "improved"


class TestCompareMetric:
    """_compare_metricのテスト。"""

    def test_lower_is_better_improved(self, engine):
        m = engine._compare_metric(5.0, 3.0, lower_is_better=True)
        assert m.verdict == "improved"
        assert m.change == -2.0

    def test_lower_is_better_degraded(self, engine):
        m = engine._compare_metric(3.0, 5.0, lower_is_better=True)
        assert m.verdict == "degraded"
        assert m.change == 2.0

    def test_unchanged(self, engine):
        m = engine._compare_metric(5.0, 5.0, lower_is_better=True)
        assert m.verdict == "unchanged"
        assert m.change == 0
