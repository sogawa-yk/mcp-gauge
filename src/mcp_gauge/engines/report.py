"""統合レポート生成エンジン。"""

from datetime import UTC, datetime

from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.results import Report
from mcp_gauge.models.trace import TraceSummary


class ReportGenerator:
    """統合レポート生成エンジン。"""

    def __init__(self, storage: TraceStorage) -> None:
        self.storage = storage

    async def generate(self, trace_ids: list[str]) -> Report:
        """複数トレースの統合レポートを生成する。"""
        summaries: list[TraceSummary] = []
        for trace_id in trace_ids:
            summary = await self.storage.get_summary(trace_id)
            summaries.append(summary)

        if not summaries:
            return Report(
                trace_ids=trace_ids,
                generated_at=datetime.now(UTC).isoformat(),
                sessions=[],
                aggregated_calls=0.0,
                aggregated_errors=0.0,
                aggregated_redundant=0.0,
                recommendations=[],
            )

        n = len(summaries)
        avg_calls = sum(s.total_calls for s in summaries) / n
        avg_errors = sum(s.error_count for s in summaries) / n
        avg_redundant = sum(s.redundant_calls for s in summaries) / n

        recommendations = self._generate_recommendations(
            summaries, avg_calls, avg_errors, avg_redundant
        )

        return Report(
            trace_ids=trace_ids,
            generated_at=datetime.now(UTC).isoformat(),
            sessions=summaries,
            aggregated_calls=round(avg_calls, 2),
            aggregated_errors=round(avg_errors, 2),
            aggregated_redundant=round(avg_redundant, 2),
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        summaries: list[TraceSummary],
        avg_calls: float,
        avg_errors: float,
        avg_redundant: float,
    ) -> list[str]:
        """改善推奨事項を生成する。"""
        recommendations: list[str] = []

        if avg_errors > 0:
            error_rate = avg_errors / avg_calls if avg_calls > 0 else 0
            if error_rate > 0.3:
                recommendations.append(
                    "エラー率が30%を超えています。ツール説明文の改善を検討してください"
                )
            elif error_rate > 0.1:
                recommendations.append(
                    "エラー率が10%を超えています。"
                    "パラメータ説明の充実を検討してください"
                )

        if avg_redundant > 0:
            redundant_rate = avg_redundant / avg_calls if avg_calls > 0 else 0
            if redundant_rate > 0.2:
                recommendations.append(
                    "冗長呼び出し率が20%を超えています。"
                    "ツールの戻り値をより明確にすることを"
                    "検討してください"
                )

        avg_recovery = sum(s.recovery_steps for s in summaries) / len(summaries)
        if avg_recovery > 2:
            recommendations.append(
                "平均リカバリステップが2を超えています。"
                "エラーメッセージの改善を検討してください"
            )

        if not recommendations:
            recommendations.append("特に問題は検出されませんでした")

        return recommendations
