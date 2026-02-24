"""Prompts品質評価（比較）エンジン。"""

from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.results import (
    ComparisonResult,
    MetricComparison,
)


class CompareEngine:
    """ベースライン比較エンジン。"""

    def __init__(self, storage: TraceStorage) -> None:
        self.storage = storage

    async def compare(
        self,
        baseline_trace_id: str,
        current_trace_id: str,
    ) -> ComparisonResult:
        """2つのトレースセッションを比較する。"""
        baseline_session = await self.storage.get_session(baseline_trace_id)
        current_session = await self.storage.get_session(current_trace_id)

        baseline_summary = await self.storage.get_summary(baseline_trace_id)
        current_summary = await self.storage.get_summary(current_trace_id)

        metrics: dict[str, MetricComparison] = {}

        # 数値メトリクス（少ないほど良い）
        metrics["total_calls"] = self._compare_metric(
            float(baseline_summary.total_calls),
            float(current_summary.total_calls),
            lower_is_better=True,
        )
        metrics["error_count"] = self._compare_metric(
            float(baseline_summary.error_count),
            float(current_summary.error_count),
            lower_is_better=True,
        )
        metrics["redundant_calls"] = self._compare_metric(
            float(baseline_summary.redundant_calls),
            float(current_summary.redundant_calls),
            lower_is_better=True,
        )
        metrics["total_duration_ms"] = self._compare_metric(
            baseline_summary.total_duration_ms,
            current_summary.total_duration_ms,
            lower_is_better=True,
        )
        metrics["recovery_steps"] = self._compare_metric(
            float(baseline_summary.recovery_steps),
            float(current_summary.recovery_steps),
            lower_is_better=True,
        )

        # タスク成功（boolメトリクス）
        baseline_success = baseline_session.task_success or False
        current_success = current_session.task_success or False
        if baseline_success == current_success:
            success_verdict = "unchanged"
        elif current_success and not baseline_success:
            success_verdict = "improved"
        else:
            success_verdict = "degraded"
        metrics["task_success"] = MetricComparison(
            baseline=baseline_success,
            current=current_success,
            change=None,
            verdict=success_verdict,
        )

        # 総合判定
        overall_verdict = self._determine_overall_verdict(metrics)

        return ComparisonResult(
            baseline_trace_id=baseline_trace_id,
            current_trace_id=current_trace_id,
            overall_verdict=overall_verdict,
            metrics=metrics,
        )

    def _compare_metric(
        self,
        baseline: float,
        current: float,
        lower_is_better: bool,
    ) -> MetricComparison:
        """個別メトリクスの改善/悪化を判定する。"""
        change = current - baseline
        if change == 0:
            verdict = "unchanged"
        elif lower_is_better:
            verdict = "improved" if change < 0 else "degraded"
        else:
            verdict = "improved" if change > 0 else "degraded"

        return MetricComparison(
            baseline=baseline,
            current=current,
            change=change,
            verdict=verdict,
        )

    def _determine_overall_verdict(
        self,
        metrics: dict[str, MetricComparison],
    ) -> str:
        """全メトリクスの総合判定を行う。"""
        improved = 0
        degraded = 0
        for m in metrics.values():
            if m.verdict == "improved":
                improved += 1
            elif m.verdict == "degraded":
                degraded += 1

        if degraded > 0 and improved == 0:
            return "degraded"
        if improved > 0 and degraded == 0:
            return "improved"
        if improved > 0 and degraded > 0:
            return "mixed"
        return "unchanged"
