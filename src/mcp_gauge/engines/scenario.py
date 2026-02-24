"""シナリオベースE2Eテスト実行エンジン。"""

import json
from pathlib import Path
from typing import Any

import yaml

from mcp_gauge.config import GaugeConfig
from mcp_gauge.engines.trace import TraceEngine
from mcp_gauge.exceptions import InvalidScenarioError
from mcp_gauge.infra.llm_client import LLMClient
from mcp_gauge.infra.mcp_client import MCPClientWrapper
from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.results import (
    CriteriaEvaluation,
    ScenarioResult,
    SuiteResult,
)
from mcp_gauge.models.scenario import (
    ScenarioDefinition,
    SuccessCriteria,
)
from mcp_gauge.models.trace import TraceSummary

_SYSTEM_PROMPT = (
    "あなたはMCPサーバーのテストを実行するエージェントです。"
    "与えられたタスク指示に従い、利用可能なツールを使って"
    "タスクを完了してください。"
    "ツール呼び出しの結果を確認し、タスクが完了したら"
    "その旨を報告してください。"
)


class ScenarioRunner:
    """シナリオベースE2Eテスト実行エンジン。"""

    def __init__(self, config: GaugeConfig) -> None:
        self.config = config
        self.storage = TraceStorage(config.db_path)
        self.trace_engine = TraceEngine(self.storage)
        self.llm_client = LLMClient(
            api_key=config.anthropic_api_key,
            model=config.anthropic_model,
        )

    async def run_scenario(
        self,
        server_command: str,
        scenario: ScenarioDefinition,
        server_args: list[str] | None = None,
    ) -> ScenarioResult:
        """シナリオを実行し結果を返す。"""
        await self.storage.init_db()

        # 対象MCPサーバーに接続
        client = MCPClientWrapper(timeout_sec=self.config.mcp_timeout_sec)
        try:
            tools = await client.connect(server_command, server_args)

            # forbidden_toolsをフィルタリング
            forbidden = set(scenario.success_criteria.forbidden_tools or [])
            available_tools = [t for t in tools if t.name not in forbidden]

            # トレースセッション開始
            trace_id = await self.trace_engine.start_session(
                server_command,
                server_args,
                scenario_id=scenario.id,
            )

            # LLMにタスクを実行させる
            task_success = await self._execute_with_llm(
                scenario,
                available_tools,
                client,
                trace_id,
            )

            # セッション終了
            summary = await self.trace_engine.stop_session(
                trace_id, task_success=task_success
            )

            # 成功条件の評価
            criteria_eval = self._evaluate_criteria(
                summary,
                scenario.success_criteria,
                task_success,
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

            return ScenarioResult(
                scenario_id=scenario.id,
                trace_id=trace_id,
                passed=passed,
                task_success=task_success,
                summary=summary,
                criteria_evaluation=criteria_eval,
            )
        finally:
            await client.close()

    async def run_suite(
        self,
        server_command: str,
        suite_path: str,
        server_args: list[str] | None = None,
    ) -> SuiteResult:
        """スイート（複数シナリオ）を一括実行する。"""
        scenarios = self._load_suite(suite_path)
        results: list[ScenarioResult] = []

        for scenario in scenarios:
            result = await self.run_scenario(server_command, scenario, server_args)
            results.append(result)

        passed_count = sum(1 for r in results if r.passed)
        return SuiteResult(
            suite_path=suite_path,
            total=len(results),
            passed=passed_count,
            failed=len(results) - passed_count,
            results=results,
        )

    async def _execute_with_llm(
        self,
        scenario: ScenarioDefinition,
        tools: list[Any],
        client: MCPClientWrapper,
        trace_id: str,
    ) -> bool:
        """LLMにタスクを実行させ、ツール呼び出しをトレースする。"""
        # ツール定義をAnthropic API形式に変換
        tool_defs = self._convert_tools_for_llm(tools)

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": scenario.task_instruction,
            }
        ]

        max_iterations = 50
        for _ in range(max_iterations):
            response = self.llm_client.chat_with_history(
                system_prompt=_SYSTEM_PROMPT,
                messages=messages,
                tools=tool_defs,
            )

            # レスポンスからtool_useブロックを検出
            tool_uses = [
                block for block in response.content if block.type == "tool_use"
            ]

            if not tool_uses:
                # ツール呼び出しなし = タスク完了
                return True

            # assistantメッセージを履歴に追加
            messages.append(
                {
                    "role": "assistant",
                    "content": [_content_block_to_dict(b) for b in response.content],
                }
            )

            # 各ツール呼び出しを実行
            tool_results: list[dict[str, Any]] = []
            for tool_use in tool_uses:
                result_dict, is_error, duration_ms = await client.call_tool(
                    tool_use.name,
                    tool_use.input if isinstance(tool_use.input, dict) else {},
                )

                # トレース記録
                await self.trace_engine.record_call(
                    session_id=trace_id,
                    tool_name=tool_use.name,
                    arguments=(
                        tool_use.input if isinstance(tool_use.input, dict) else {}
                    ),
                    result=result_dict,
                    is_error=is_error,
                    duration_ms=duration_ms,
                )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result_dict, ensure_ascii=False),
                        "is_error": is_error,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

            # stop_reason確認
            if response.stop_reason == "end_turn":
                return True

        # 最大イテレーション到達
        return False

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

    def _load_suite(self, suite_path: str) -> list[ScenarioDefinition]:
        """スイート定義ファイルからシナリオを読み込む。"""
        suite_file = Path(suite_path)
        if not suite_file.exists():
            raise InvalidScenarioError(
                "suite_path",
                f"スイートファイルが見つかりません: {suite_path}",
            )

        with open(suite_file) as f:
            suite_data = yaml.safe_load(f)

        if not isinstance(suite_data, dict):
            raise InvalidScenarioError("suite_path", "スイート定義が不正です")

        scenario_paths = suite_data.get("scenarios", [])
        base_dir = suite_file.parent

        scenarios: list[ScenarioDefinition] = []
        for scenario_path in scenario_paths:
            full_path = base_dir / scenario_path
            if not full_path.exists():
                raise InvalidScenarioError(
                    "scenarios",
                    f"シナリオファイルが見つかりません: {scenario_path}",
                )
            with open(full_path) as f:
                scenario_data = yaml.safe_load(f)
            scenarios.append(ScenarioDefinition(**scenario_data))

        return scenarios

    def _convert_tools_for_llm(self, tools: list[Any]) -> list[dict[str, Any]]:
        """MCPツール定義をAnthropic API形式に変換する。"""
        result = []
        for tool in tools:
            tool_def: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema
                or {
                    "type": "object",
                    "properties": {},
                },
            }
            result.append(tool_def)
        return result


def _content_block_to_dict(block: Any) -> dict[str, Any]:
    """Anthropic APIのコンテンツブロックを辞書に変換する。"""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    elif block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return {"type": block.type}
