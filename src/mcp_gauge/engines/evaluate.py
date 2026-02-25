"""成功条件評価エンジン。"""

from typing import Any

from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.results import CriteriaEvaluation
from mcp_gauge.models.scenario import SuccessCriteria
from mcp_gauge.models.trace import TraceSummary


class EvaluateEngine:
    """トレースデータに基づく成功条件評価エンジン。"""

    def __init__(self, storage: TraceStorage) -> None:
        self.storage = storage

    async def evaluate(
        self,
        session_id: str,
        success_criteria: SuccessCriteria,
        task_success: bool | None = None,
    ) -> dict[str, Any]:
        """セッションのトレースデータを成功条件で評価する。"""
        summary = await self.storage.get_summary(session_id)
        session = await self.storage.get_session(session_id)

        effective_task_success = (
            task_success if task_success is not None else session.task_success
        )

        criteria_eval = self._evaluate_criteria(
            summary, success_criteria, effective_task_success or False
        )

        passed = all(
            v.get("passed", False)
            for v in [
                criteria_eval.max_steps,
                criteria_eval.required_tools,
                criteria_eval.forbidden_tools,
                criteria_eval.must_succeed,
            ]
            if v is not None
        )

        return {
            "passed": passed,
            "task_success": effective_task_success,
            "summary": summary.model_dump(),
            "criteria_evaluation": criteria_eval.model_dump(),
        }

    def _evaluate_criteria(
        self,
        summary: TraceSummary,
        criteria: SuccessCriteria,
        task_success: bool,
    ) -> CriteriaEvaluation:
        """成功条件を評価する。"""
        evaluation = CriteriaEvaluation()

        if criteria.max_steps is not None:
            evaluation.max_steps = {
                "passed": summary.total_calls <= criteria.max_steps,
                "limit": criteria.max_steps,
                "actual": summary.total_calls,
            }

        if criteria.required_tools is not None:
            called_tools = set(summary.tool_call_sequence)
            missing = [t for t in criteria.required_tools if t not in called_tools]
            evaluation.required_tools = {
                "passed": len(missing) == 0,
                "missing": missing,
            }

        if criteria.forbidden_tools is not None:
            called_tools = set(summary.tool_call_sequence)
            violated = [t for t in criteria.forbidden_tools if t in called_tools]
            evaluation.forbidden_tools = {
                "passed": len(violated) == 0,
                "violated": violated,
            }

        if criteria.must_succeed:
            evaluation.must_succeed = {
                "passed": task_success,
            }

        return evaluation
