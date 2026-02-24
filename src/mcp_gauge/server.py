"""MCP Gaugeサーバーレイヤー。"""

import json
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from mcp_gauge.config import GaugeConfig
from mcp_gauge.engines.compare import CompareEngine
from mcp_gauge.engines.lint import LintEngine
from mcp_gauge.engines.report import ReportGenerator
from mcp_gauge.engines.scenario import ScenarioRunner
from mcp_gauge.engines.trace import TraceEngine
from mcp_gauge.exceptions import (
    GaugeError,
    InvalidScenarioError,
    LLMAPIError,
    ServerConnectionError,
    TraceNotFoundError,
)
from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.scenario import ScenarioDefinition


class GaugeServer:
    """MCP Gaugeサーバー。"""

    def __init__(self, config: GaugeConfig) -> None:
        self.config = config
        self.mcp = Server("mcp-gauge")
        self.storage = TraceStorage(config.db_path)
        self.lint_engine = LintEngine()
        self.trace_engine = TraceEngine(self.storage)
        self.scenario_runner = ScenarioRunner(config)
        self.compare_engine = CompareEngine(self.storage)
        self.report_generator = ReportGenerator(self.storage)

        self._register_handlers()

    async def initialize(self) -> None:
        """DB初期化とクラッシュリカバリーを実行する。"""
        await self.storage.init_db()
        await self.storage.recover_sessions()

    def _register_handlers(self) -> None:
        """MCPツールハンドラを登録する。"""

        @self.mcp.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="gauge_lint",
                    description=(
                        "対象MCPサーバーのツール説明文をリンティングし、"
                        "改善すべき点を構造化JSONで返す。"
                        "LLM呼び出し不要で高速に実行される。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "server_command": {
                                "type": "string",
                                "description": ("対象MCPサーバーの起動コマンド"),
                            },
                            "server_args": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "対象MCPサーバーの起動引数。デフォルト: []"
                                ),
                            },
                        },
                        "required": ["server_command"],
                    },
                ),
                Tool(
                    name="gauge_trace_start",
                    description=(
                        "対象MCPサーバーへのトレースセッションを"
                        "開始し、trace_idを返す。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "server_command": {
                                "type": "string",
                                "description": ("対象MCPサーバーの起動コマンド"),
                            },
                            "server_args": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "対象MCPサーバーの起動引数。デフォルト: []"
                                ),
                            },
                        },
                        "required": ["server_command"],
                    },
                ),
                Tool(
                    name="gauge_trace_stop",
                    description=(
                        "トレースセッションを終了し、"
                        "トレースサマリー（メトリクス）を返す。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "trace_id": {
                                "type": "string",
                                "description": (
                                    "gauge_trace_startで取得したトレースID"
                                ),
                            },
                        },
                        "required": ["trace_id"],
                    },
                ),
                Tool(
                    name="gauge_run_scenario",
                    description=(
                        "テストシナリオを実行し、合否と詳細を返す。"
                        "LLMがテスト対象MCPサーバーのツールを使って"
                        "タスクを実行し、成功条件に基づいて評価する。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "server_command": {
                                "type": "string",
                                "description": ("対象MCPサーバーの起動コマンド"),
                            },
                            "scenario": {
                                "type": "object",
                                "description": (
                                    "テストシナリオ定義（id, name, "
                                    "description, task_instruction, "
                                    "success_criteria を含む）"
                                ),
                            },
                            "server_args": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "対象MCPサーバーの起動引数。デフォルト: []"
                                ),
                            },
                        },
                        "required": [
                            "server_command",
                            "scenario",
                        ],
                    },
                ),
                Tool(
                    name="gauge_run_suite",
                    description=(
                        "テストスイート（複数シナリオ）を一括実行し、"
                        "結果サマリーを返す。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "server_command": {
                                "type": "string",
                                "description": ("対象MCPサーバーの起動コマンド"),
                            },
                            "suite_path": {
                                "type": "string",
                                "description": ("スイート定義YAMLファイルのパス"),
                            },
                            "server_args": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "対象MCPサーバーの起動引数。デフォルト: []"
                                ),
                            },
                        },
                        "required": [
                            "server_command",
                            "suite_path",
                        ],
                    },
                ),
                Tool(
                    name="gauge_compare",
                    description=(
                        "ベースラインのトレースと新規実行のトレースを"
                        "比較し、メトリクスの改善/悪化を判定する。"
                        "返却値にはoverall_verdictとメトリクスごとの"
                        "比較結果を含む。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "baseline_trace_id": {
                                "type": "string",
                                "description": ("ベースライン（変更前）のトレースID"),
                            },
                            "current_trace_id": {
                                "type": "string",
                                "description": ("現在（変更後）のトレースID"),
                            },
                        },
                        "required": [
                            "baseline_trace_id",
                            "current_trace_id",
                        ],
                    },
                ),
                Tool(
                    name="gauge_report",
                    description=(
                        "複数のトレースセッションから統合レポートを"
                        "生成する。平均メトリクスと改善推奨事項を返す。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "trace_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": ("レポート対象のトレースIDリスト"),
                            },
                        },
                        "required": ["trace_ids"],
                    },
                ),
            ]

        @self.mcp.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            try:
                result = await self._dispatch(name, arguments)
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, ensure_ascii=False),
                    )
                ]
            except ServerConnectionError as e:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "connection_failed",
                                "message": str(e),
                                "suggestion": (
                                    "server_commandとserver_argsを確認してください"
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    )
                ]
            except TraceNotFoundError as e:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "trace_not_found",
                                "message": str(e),
                                "suggestion": ("有効なtrace_idを指定してください"),
                            },
                            ensure_ascii=False,
                        ),
                    )
                ]
            except InvalidScenarioError as e:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "invalid_scenario",
                                "message": str(e),
                                "suggestion": ("シナリオのYAML形式を確認してください"),
                            },
                            ensure_ascii=False,
                        ),
                    )
                ]
            except LLMAPIError as e:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "llm_api_error",
                                "message": str(e),
                                "suggestion": (
                                    "ANTHROPIC_API_KEYの設定を確認してください"
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    )
                ]
            except GaugeError as e:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": "gauge_error",
                                "message": str(e),
                                "suggestion": ("エラーの詳細を確認してください"),
                            },
                            ensure_ascii=False,
                        ),
                    )
                ]

    async def _dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """ツール名に基づいてエンジンに委譲する。"""
        await self.storage.init_db()

        if name == "gauge_lint":
            return await self._handle_lint(arguments)
        elif name == "gauge_trace_start":
            return await self._handle_trace_start(arguments)
        elif name == "gauge_trace_stop":
            return await self._handle_trace_stop(arguments)
        elif name == "gauge_run_scenario":
            return await self._handle_run_scenario(arguments)
        elif name == "gauge_run_suite":
            return await self._handle_run_suite(arguments)
        elif name == "gauge_compare":
            return await self._handle_compare(arguments)
        elif name == "gauge_report":
            return await self._handle_report(arguments)
        else:
            return {
                "error": "unknown_tool",
                "message": f"不明なツール: {name}",
                "suggestion": "利用可能なツール名を確認してください",
            }

    async def _handle_lint(self, arguments: dict[str, Any]) -> dict[str, Any]:
        server_command = arguments["server_command"]
        server_args = arguments.get("server_args")
        results, total_tools = await self.lint_engine.lint(
            server_command,
            server_args,
            timeout_sec=self.config.mcp_timeout_sec,
        )
        return {
            "total_tools": total_tools,
            "total_issues": len(results),
            "issues": [r.model_dump() for r in results],
        }

    async def _handle_trace_start(self, arguments: dict[str, Any]) -> dict[str, Any]:
        server_command = arguments["server_command"]
        server_args = arguments.get("server_args")
        trace_id = await self.trace_engine.start_session(server_command, server_args)
        return {"trace_id": trace_id}

    async def _handle_trace_stop(self, arguments: dict[str, Any]) -> dict[str, Any]:
        trace_id = arguments["trace_id"]
        summary = await self.trace_engine.stop_session(trace_id)
        return summary.model_dump()

    async def _handle_run_scenario(self, arguments: dict[str, Any]) -> dict[str, Any]:
        server_command = arguments["server_command"]
        scenario_data = arguments["scenario"]
        server_args = arguments.get("server_args")
        scenario = ScenarioDefinition(**scenario_data)
        result = await self.scenario_runner.run_scenario(
            server_command, scenario, server_args
        )
        return result.model_dump()

    async def _handle_run_suite(self, arguments: dict[str, Any]) -> dict[str, Any]:
        server_command = arguments["server_command"]
        suite_path = arguments["suite_path"]
        server_args = arguments.get("server_args")
        result = await self.scenario_runner.run_suite(
            server_command, suite_path, server_args
        )
        return result.model_dump()

    async def _handle_compare(self, arguments: dict[str, Any]) -> dict[str, Any]:
        baseline_trace_id = arguments["baseline_trace_id"]
        current_trace_id = arguments["current_trace_id"]
        result = await self.compare_engine.compare(baseline_trace_id, current_trace_id)
        return result.model_dump()

    async def _handle_report(self, arguments: dict[str, Any]) -> dict[str, Any]:
        trace_ids = arguments["trace_ids"]
        result = await self.report_generator.generate(trace_ids)
        return result.model_dump()
