"""実行結果のデータモデル。"""

from typing import Any

from pydantic import BaseModel

from mcp_gauge.models.trace import TraceSummary


class CriteriaEvaluation(BaseModel):
    """成功条件の個別評価結果。"""

    max_steps: dict[str, Any] | None = None
    required_tools: dict[str, Any] | None = None
    forbidden_tools: dict[str, Any] | None = None
    must_succeed: dict[str, Any] | None = None


class ScenarioResult(BaseModel):
    """シナリオ実行結果。"""

    scenario_id: str
    trace_id: str
    passed: bool
    task_success: bool
    summary: TraceSummary
    criteria_evaluation: CriteriaEvaluation


class SuiteResult(BaseModel):
    """テストスイート実行結果。"""

    suite_path: str
    total: int
    passed: int
    failed: int
    results: list[ScenarioResult]


class MetricComparison(BaseModel):
    """個別メトリクスの比較結果。"""

    baseline: float | bool
    current: float | bool
    change: float | None = None
    verdict: str


class ComparisonResult(BaseModel):
    """ベースライン比較結果。"""

    baseline_trace_id: str
    current_trace_id: str
    overall_verdict: str
    metrics: dict[str, MetricComparison]


class Report(BaseModel):
    """統合レポート。"""

    trace_ids: list[str]
    generated_at: str
    sessions: list[TraceSummary]
    aggregated_calls: float
    aggregated_errors: float
    aggregated_redundant: float
    recommendations: list[str]
