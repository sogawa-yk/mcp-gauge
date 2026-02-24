"""ReportGeneratorのユニットテスト。"""

from unittest.mock import AsyncMock

import pytest

from mcp_gauge.engines.report import ReportGenerator
from mcp_gauge.models.trace import TraceSummary


def _make_summary(
    total_calls: int = 5,
    error_count: int = 0,
    redundant_calls: int = 0,
    recovery_steps: int = 0,
) -> TraceSummary:
    return TraceSummary(
        total_calls=total_calls,
        unique_tools=3,
        error_count=error_count,
        redundant_calls=redundant_calls,
        total_duration_ms=1000.0,
        recovery_steps=recovery_steps,
        tool_call_sequence=["a"] * total_calls,
    )


@pytest.fixture
def mock_storage():
    return AsyncMock()


@pytest.fixture
def generator(mock_storage):
    return ReportGenerator(mock_storage)


class TestReportGenerator:
    """ReportGeneratorのテスト。"""

    async def test_empty_report(self, generator, mock_storage):
        """空のトレースIDリストでレポート生成。"""
        report = await generator.generate([])
        assert report.aggregated_calls == 0.0
        assert len(report.sessions) == 0

    async def test_single_trace(self, generator, mock_storage):
        """単一トレースのレポート生成。"""
        mock_storage.get_summary.return_value = _make_summary(
            total_calls=5, error_count=0
        )
        report = await generator.generate(["t1"])
        assert report.aggregated_calls == 5.0
        assert report.aggregated_errors == 0.0
        assert len(report.sessions) == 1

    async def test_multiple_traces(self, generator, mock_storage):
        """複数トレースの平均計算。"""
        mock_storage.get_summary.side_effect = [
            _make_summary(total_calls=4, error_count=2),
            _make_summary(total_calls=6, error_count=0),
        ]
        report = await generator.generate(["t1", "t2"])
        assert report.aggregated_calls == 5.0
        assert report.aggregated_errors == 1.0
        assert len(report.sessions) == 2

    async def test_high_error_rate_recommendation(self, generator, mock_storage):
        """高エラー率で警告推奨。"""
        mock_storage.get_summary.return_value = _make_summary(
            total_calls=10, error_count=5
        )
        report = await generator.generate(["t1"])
        assert any("エラー率" in r for r in report.recommendations)

    async def test_high_redundant_rate_recommendation(self, generator, mock_storage):
        """高冗長率で警告推奨。"""
        mock_storage.get_summary.return_value = _make_summary(
            total_calls=10, redundant_calls=3
        )
        report = await generator.generate(["t1"])
        assert any("冗長" in r for r in report.recommendations)

    async def test_high_recovery_recommendation(self, generator, mock_storage):
        """高リカバリステップで警告推奨。"""
        mock_storage.get_summary.return_value = _make_summary(
            total_calls=10, recovery_steps=5
        )
        report = await generator.generate(["t1"])
        assert any("リカバリ" in r for r in report.recommendations)

    async def test_no_issues_recommendation(self, generator, mock_storage):
        """問題なしの場合の推奨。"""
        mock_storage.get_summary.return_value = _make_summary(
            total_calls=5,
            error_count=0,
            redundant_calls=0,
            recovery_steps=0,
        )
        report = await generator.generate(["t1"])
        assert any("問題は検出されませんでした" in r for r in report.recommendations)
