"""MCP Gaugeサーバーレイヤー。"""

import json
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import Field

from mcp_gauge.config import GaugeConfig
from mcp_gauge.engines.compare import CompareEngine
from mcp_gauge.engines.evaluate import EvaluateEngine
from mcp_gauge.engines.lint import LintEngine
from mcp_gauge.engines.report import ReportGenerator
from mcp_gauge.engines.session import SessionManager
from mcp_gauge.engines.trace import TraceEngine
from mcp_gauge.exceptions import (
    ConnectionLostError,
    GaugeError,
    InvalidScenarioError,
    ServerConnectionError,
    SessionNotFoundError,
    ToolCallTimeoutError,
    TraceNotFoundError,
)
from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.scenario import SuccessCriteria
from mcp_gauge.models.trace import ConnectionParams, TransportType
from mcp_gauge.prompts import FASTMCP_PROMPTS


class GaugeServer:
    """MCP Gaugeサーバー。"""

    def __init__(self, config: GaugeConfig) -> None:
        self.config = config
        self.mcp = FastMCP("mcp-gauge")
        self.storage = TraceStorage(config.db_path)
        self.lint_engine = LintEngine()
        self.trace_engine = TraceEngine(self.storage)
        self.session_manager = SessionManager(
            self.trace_engine,
            config.mcp_timeout_sec,
            config.mcp_tool_timeout_sec,
        )
        self.evaluate_engine = EvaluateEngine(self.storage)
        self.compare_engine = CompareEngine(self.storage)
        self.report_generator = ReportGenerator(self.storage)

        self._register_tools()
        self._register_prompts()

    async def initialize(self) -> None:
        """DB初期化とクラッシュリカバリーを実行する。"""
        await self.storage.init_db()
        await self.storage.recover_sessions()

    # ------------------------------------------------------------------
    # ツール登録
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """FastMCPにツールをバウンドメソッドとして登録する。"""
        self.mcp.add_tool(
            self.gauge_lint,
            name="gauge_lint",
            description=(
                "対象MCPサーバーのツール説明文をリンティングし、"
                "改善すべき点を構造化JSONで返す。"
                "LLM呼び出し不要で高速に実行される。"
            ),
        )
        self.mcp.add_tool(
            self.gauge_connect,
            name="gauge_connect",
            description=(
                "対象MCPサーバーに接続し、トレースセッションを"
                "開始する。session_idと利用可能なツール一覧を返す。"
                "呼び出し元はツール一覧を見て、"
                "gauge_proxy_callでツールを呼び出す。"
            ),
        )
        self.mcp.add_tool(
            self.gauge_proxy_call,
            name="gauge_proxy_call",
            description=(
                "gauge_connectで確立した接続を通じて、"
                "対象MCPサーバーのツールを呼び出す。"
                "呼び出しはトレースとして自動記録される。"
                "結果には対象ツールの応答と"
                "呼び出しメトリクスが含まれる。"
            ),
        )
        self.mcp.add_tool(
            self.gauge_disconnect,
            name="gauge_disconnect",
            description=(
                "対象MCPサーバーとの接続を切断し、"
                "トレースセッションを終了する。"
                "トレースサマリー（メトリクス）を返す。"
            ),
        )
        self.mcp.add_tool(
            self.gauge_evaluate,
            name="gauge_evaluate",
            description=(
                "トレースセッションの結果を成功条件に基づいて"
                "評価する。gauge_disconnectで終了したセッションの"
                "トレースデータと成功条件を照合し、"
                "合否判定と詳細評価を返す。"
            ),
        )
        self.mcp.add_tool(
            self.gauge_compare,
            name="gauge_compare",
            description=(
                "ベースラインのトレースと新規実行のトレースを"
                "比較し、メトリクスの改善/悪化を判定する。"
                "返却値にはoverall_verdictとメトリクスごとの"
                "比較結果を含む。"
            ),
        )
        self.mcp.add_tool(
            self.gauge_report,
            name="gauge_report",
            description=(
                "複数のトレースセッションから統合レポートを"
                "生成する。平均メトリクスと改善推奨事項を返す。"
            ),
        )

    def _register_prompts(self) -> None:
        """FastMCPにプロンプトを登録する。"""
        for prompt in FASTMCP_PROMPTS:
            self.mcp.add_prompt(prompt)

    # ------------------------------------------------------------------
    # ツールメソッド（FastMCPが型ヒントからスキーマを自動生成）
    # ------------------------------------------------------------------

    async def gauge_lint(
        self,
        server_command: Annotated[
            str | None,
            Field(
                description="対象MCPサーバーの起動コマンド（stdioトランスポート時に必須）"
            ),
        ] = None,
        server_args: Annotated[
            list[str] | None,
            Field(description="対象MCPサーバーの起動引数。デフォルト: []"),
        ] = None,
        server_url: Annotated[
            str | None,
            Field(
                description=(
                    "リモートMCPサーバーのURL"
                    "（sse/streamable_httpトランスポート時に必須）"
                )
            ),
        ] = None,
        transport_type: Annotated[
            str | None,
            Field(
                description=(
                    "トランスポートの種類。"
                    "デフォルト: server_url指定時はstreamable_http、それ以外はstdio"
                )
            ),
        ] = None,
        headers: Annotated[
            dict[str, Any] | None,
            Field(description="リモート接続時のHTTPヘッダー。デフォルト: {}"),
        ] = None,
    ) -> CallToolResult:
        """対象MCPサーバーのツール説明文をリンティングする。"""
        await self.storage.init_db()
        try:
            result = await self._handle_lint(
                {
                    "server_command": server_command,
                    "server_args": server_args or [],
                    "server_url": server_url,
                    "transport_type": transport_type,
                    "headers": headers or {},
                }
            )
            return self._success_response(result)
        except ServerConnectionError as e:
            return self._error_response(
                "connection_failed",
                str(e),
                "server_command/server_urlと接続パラメータを確認してください",
            )
        except InvalidScenarioError as e:
            return self._error_response(
                "invalid_scenario",
                str(e),
                "パラメータの形式を確認してください",
            )
        except GaugeError as e:
            return self._error_response(
                "gauge_error", str(e), "エラーの詳細を確認してください"
            )

    async def gauge_connect(
        self,
        server_command: Annotated[
            str | None,
            Field(
                description="対象MCPサーバーの起動コマンド（stdioトランスポート時に必須）"
            ),
        ] = None,
        server_args: Annotated[
            list[str] | None,
            Field(description="対象MCPサーバーの起動引数。デフォルト: []"),
        ] = None,
        server_url: Annotated[
            str | None,
            Field(
                description=(
                    "リモートMCPサーバーのURL"
                    "（sse/streamable_httpトランスポート時に必須）"
                )
            ),
        ] = None,
        transport_type: Annotated[
            str | None,
            Field(
                description=(
                    "トランスポートの種類。"
                    "デフォルト: server_url指定時はstreamable_http、それ以外はstdio"
                )
            ),
        ] = None,
        headers: Annotated[
            dict[str, Any] | None,
            Field(description="リモート接続時のHTTPヘッダー。デフォルト: {}"),
        ] = None,
        scenario_id: Annotated[
            str | None,
            Field(description="紐づけるシナリオID（任意）"),
        ] = None,
    ) -> CallToolResult:
        """対象MCPサーバーに接続しトレースセッションを開始する。"""
        await self.storage.init_db()
        try:
            result = await self._handle_connect(
                {
                    "server_command": server_command,
                    "server_args": server_args or [],
                    "server_url": server_url,
                    "transport_type": transport_type,
                    "headers": headers or {},
                    "scenario_id": scenario_id,
                }
            )
            return self._success_response(result)
        except ServerConnectionError as e:
            return self._error_response(
                "connection_failed",
                str(e),
                "server_command/server_urlと接続パラメータを確認してください",
            )
        except InvalidScenarioError as e:
            return self._error_response(
                "invalid_scenario",
                str(e),
                "パラメータの形式を確認してください",
            )
        except GaugeError as e:
            return self._error_response(
                "gauge_error", str(e), "エラーの詳細を確認してください"
            )

    async def gauge_proxy_call(
        self,
        session_id: Annotated[
            str,
            Field(description="gauge_connectで取得したセッションID"),
        ],
        tool_name: Annotated[
            str,
            Field(description="呼び出す対象ツールの名前"),
        ],
        arguments: Annotated[
            dict[str, Any],
            Field(description="対象ツールに渡す引数"),
        ],
    ) -> CallToolResult:
        """対象MCPサーバーのツールをプロキシ呼び出しする。"""
        await self.storage.init_db()
        try:
            result = await self._handle_proxy_call(
                {
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                }
            )
            return self._success_response(result)
        except ToolCallTimeoutError as e:
            return self._error_response(
                "tool_call_timeout",
                str(e),
                "対象サーバーが応答しません。サーバーの状態を確認してください",
            )
        except ConnectionLostError as e:
            return self._error_response(
                "connection_lost",
                str(e),
                "gauge_connectで再接続してください",
            )
        except SessionNotFoundError as e:
            return self._error_response(
                "session_not_found",
                str(e),
                "gauge_connectで取得した有効なsession_idを指定してください",
            )
        except GaugeError as e:
            return self._error_response(
                "gauge_error", str(e), "エラーの詳細を確認してください"
            )

    async def gauge_disconnect(
        self,
        session_id: Annotated[
            str,
            Field(description="gauge_connectで取得したセッションID"),
        ],
        task_success: Annotated[
            bool | None,
            Field(
                description=(
                    "タスクが成功したかどうか。"
                    "呼び出し元エージェントが判断して設定する"
                )
            ),
        ] = None,
    ) -> CallToolResult:
        """対象MCPサーバーとの接続を切断しセッションを終了する。"""
        await self.storage.init_db()
        try:
            result = await self._handle_disconnect(
                {
                    "session_id": session_id,
                    "task_success": task_success,
                }
            )
            return self._success_response(result)
        except SessionNotFoundError as e:
            return self._error_response(
                "session_not_found",
                str(e),
                "gauge_connectで取得した有効なsession_idを指定してください",
            )
        except GaugeError as e:
            return self._error_response(
                "gauge_error", str(e), "エラーの詳細を確認してください"
            )

    async def gauge_evaluate(
        self,
        session_id: Annotated[
            str,
            Field(description="評価対象のセッションID"),
        ],
        success_criteria: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "成功条件（max_steps, required_tools, "
                    "forbidden_tools, must_succeed を含む）"
                )
            ),
        ],
        task_success: Annotated[
            bool | None,
            Field(
                description=(
                    "タスクが成功したかの判断。"
                    "呼び出し元エージェントが判断して設定する"
                )
            ),
        ] = None,
    ) -> CallToolResult:
        """トレースセッションの結果を成功条件に基づいて評価する。"""
        await self.storage.init_db()
        try:
            result = await self._handle_evaluate(
                {
                    "session_id": session_id,
                    "success_criteria": success_criteria,
                    "task_success": task_success,
                }
            )
            return self._success_response(result)
        except SessionNotFoundError as e:
            return self._error_response(
                "session_not_found",
                str(e),
                "gauge_connectで取得した有効なsession_idを指定してください",
            )
        except TraceNotFoundError as e:
            return self._error_response(
                "trace_not_found",
                str(e),
                "有効なtrace_idを指定してください",
            )
        except InvalidScenarioError as e:
            return self._error_response(
                "invalid_scenario",
                str(e),
                "success_criteriaの形式を確認してください",
            )
        except GaugeError as e:
            return self._error_response(
                "gauge_error", str(e), "エラーの詳細を確認してください"
            )

    async def gauge_compare(
        self,
        baseline_trace_id: Annotated[
            str,
            Field(description="ベースライン（変更前）のトレースID"),
        ],
        current_trace_id: Annotated[
            str,
            Field(description="現在（変更後）のトレースID"),
        ],
    ) -> CallToolResult:
        """ベースラインと現在のトレースを比較し改善/悪化を判定する。"""
        await self.storage.init_db()
        try:
            result = await self._handle_compare(
                {
                    "baseline_trace_id": baseline_trace_id,
                    "current_trace_id": current_trace_id,
                }
            )
            return self._success_response(result)
        except TraceNotFoundError as e:
            return self._error_response(
                "trace_not_found",
                str(e),
                "有効なtrace_idを指定してください",
            )
        except GaugeError as e:
            return self._error_response(
                "gauge_error", str(e), "エラーの詳細を確認してください"
            )

    async def gauge_report(
        self,
        trace_ids: Annotated[
            list[str],
            Field(description="レポート対象のトレースIDリスト"),
        ],
    ) -> CallToolResult:
        """複数のトレースセッションから統合レポートを生成する。"""
        await self.storage.init_db()
        try:
            result = await self._handle_report({"trace_ids": trace_ids})
            return self._success_response(result)
        except TraceNotFoundError as e:
            return self._error_response(
                "trace_not_found",
                str(e),
                "有効なtrace_idを指定してください",
            )
        except GaugeError as e:
            return self._error_response(
                "gauge_error", str(e), "エラーの詳細を確認してください"
            )

    # ------------------------------------------------------------------
    # レスポンスヘルパー
    # ------------------------------------------------------------------

    @staticmethod
    def _success_response(result: dict[str, Any]) -> CallToolResult:
        """成功レスポンスをCallToolResultとして生成する。"""
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False),
                )
            ],
            isError=False,
        )

    @staticmethod
    def _error_response(
        error_code: str, message: str, suggestion: str
    ) -> CallToolResult:
        """エラーレスポンスをCallToolResultとして生成する。"""
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": error_code,
                            "message": message,
                            "suggestion": suggestion,
                        },
                        ensure_ascii=False,
                    ),
                )
            ],
            isError=True,
        )

    # ------------------------------------------------------------------
    # テスト互換用ディスパッチャー
    # ------------------------------------------------------------------

    async def _dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """ツール名に基づいてエンジンに委譲する。テスト互換のため維持。"""
        await self.storage.init_db()

        handlers: dict[
            str,
            Any,
        ] = {
            "gauge_lint": self._handle_lint,
            "gauge_connect": self._handle_connect,
            "gauge_proxy_call": self._handle_proxy_call,
            "gauge_disconnect": self._handle_disconnect,
            "gauge_evaluate": self._handle_evaluate,
            "gauge_compare": self._handle_compare,
            "gauge_report": self._handle_report,
        }

        handler = handlers.get(name)
        if handler is None:
            return {
                "error": "unknown_tool",
                "message": f"不明なツール: {name}",
                "suggestion": "利用可能なツール名を確認してください",
            }
        result: dict[str, Any] = await handler(arguments)
        return result

    # ------------------------------------------------------------------
    # 内部ハンドラ（_dispatch / ツールメソッド共通ロジック）
    # ------------------------------------------------------------------

    @staticmethod
    def _build_connection_params(arguments: dict[str, Any]) -> ConnectionParams:
        """ツール引数からConnectionParamsを構築する。"""
        server_command = arguments.get("server_command")
        server_url = arguments.get("server_url")
        transport_type_str = arguments.get("transport_type")
        headers = arguments.get("headers", {})
        server_args = arguments.get("server_args", [])
        env = arguments.get("env")

        if transport_type_str:
            transport_type = TransportType(transport_type_str)
        elif server_url:
            transport_type = TransportType.STREAMABLE_HTTP
        else:
            transport_type = TransportType.STDIO

        if transport_type == TransportType.STDIO and not server_command:
            raise InvalidScenarioError(
                "server_command",
                "stdioトランスポートではserver_commandが必須です",
            )
        if (
            transport_type
            in (
                TransportType.SSE,
                TransportType.STREAMABLE_HTTP,
            )
            and not server_url
        ):
            raise InvalidScenarioError(
                "server_url",
                f"{transport_type}トランスポートではserver_urlが必須です",
            )

        return ConnectionParams(
            transport_type=transport_type,
            server_command=server_command,
            server_args=server_args,
            server_url=server_url,
            headers=headers,
            env=env,
        )

    async def _handle_lint(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params = self._build_connection_params(arguments)
        results, total_tools = await self.lint_engine.lint(
            params,
            timeout_sec=self.config.mcp_timeout_sec,
        )
        return {
            "total_tools": total_tools,
            "total_issues": len(results),
            "issues": [r.model_dump() for r in results],
        }

    async def _handle_connect(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params = self._build_connection_params(arguments)
        scenario_id = arguments.get("scenario_id")
        session_id, tools = await self.session_manager.connect(params, scenario_id)
        return {"session_id": session_id, "tools": tools}

    async def _handle_proxy_call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = arguments["session_id"]
        tool_name = arguments["tool_name"]
        tool_arguments = arguments.get("arguments", {})
        return await self.session_manager.proxy_call(
            session_id, tool_name, tool_arguments
        )

    async def _handle_disconnect(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = arguments["session_id"]
        task_success = arguments.get("task_success")
        summary = await self.session_manager.disconnect(session_id, task_success)
        return summary.model_dump()

    async def _handle_evaluate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = arguments["session_id"]
        criteria_data = arguments["success_criteria"]
        task_success = arguments.get("task_success")
        criteria = SuccessCriteria(**criteria_data)
        return await self.evaluate_engine.evaluate(session_id, criteria, task_success)

    async def _handle_compare(self, arguments: dict[str, Any]) -> dict[str, Any]:
        baseline_trace_id = arguments["baseline_trace_id"]
        current_trace_id = arguments["current_trace_id"]
        result = await self.compare_engine.compare(baseline_trace_id, current_trace_id)
        return result.model_dump()

    async def _handle_report(self, arguments: dict[str, Any]) -> dict[str, Any]:
        trace_ids = arguments["trace_ids"]
        result = await self.report_generator.generate(trace_ids)
        return result.model_dump()
