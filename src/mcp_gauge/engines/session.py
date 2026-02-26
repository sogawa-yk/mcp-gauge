"""プロキシセッション管理エンジン。"""

from typing import Any

from mcp_gauge.engines.trace import TraceEngine
from mcp_gauge.exceptions import SessionNotFoundError
from mcp_gauge.infra.mcp_client import MCPClientWrapper
from mcp_gauge.models.trace import ConnectionParams, TraceSummary


class SessionManager:
    """対象MCPサーバーへのプロキシセッションを管理する。

    gauge_connect → gauge_proxy_call (繰り返し) → gauge_disconnect
    のライフサイクルを管理し、全ツール呼び出しをトレースする。
    """

    def __init__(
        self,
        trace_engine: TraceEngine,
        mcp_timeout_sec: int = 30,
        mcp_tool_timeout_sec: int = 300,
    ) -> None:
        self.trace_engine = trace_engine
        self.mcp_timeout_sec = mcp_timeout_sec
        self.mcp_tool_timeout_sec = mcp_tool_timeout_sec
        self._clients: dict[str, MCPClientWrapper] = {}

    async def connect(
        self,
        params: ConnectionParams,
        scenario_id: str | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """対象サーバーに接続し、(session_id, tools)を返す。"""
        client = MCPClientWrapper(
            timeout_sec=self.mcp_timeout_sec,
            tool_call_timeout_sec=self.mcp_tool_timeout_sec,
        )
        tools = await client.connect(params)

        session_id = await self.trace_engine.start_session(params, scenario_id)
        self._clients[session_id] = client

        tool_defs = [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema
                or {"type": "object", "properties": {}},
            }
            for tool in tools
        ]
        return session_id, tool_defs

    async def proxy_call(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """ツールをプロキシ呼び出しし、結果とメトリクスを返す。"""
        client = self._clients.get(session_id)
        if client is None:
            raise SessionNotFoundError(session_id)

        result_dict, is_error, duration_ms = await client.call_tool(
            tool_name, arguments
        )

        record = await self.trace_engine.record_call(
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result_dict,
            is_error=is_error,
            duration_ms=duration_ms,
        )

        return {
            "result": result_dict,
            "metrics": {
                "duration_ms": duration_ms,
                "sequence": record.sequence,
                "tool_name": tool_name,
                "is_error": is_error,
            },
        }

    async def disconnect(
        self,
        session_id: str,
        task_success: bool | None = None,
    ) -> TraceSummary:
        """接続を切断しサマリーを返す。"""
        client = self._clients.pop(session_id, None)
        if client is None:
            raise SessionNotFoundError(session_id)

        summary = await self.trace_engine.stop_session(
            session_id, task_success=task_success
        )
        await client.close()
        return summary

    async def close_all(self) -> None:
        """全アクティブセッションを強制終了する。"""
        import contextlib

        for session_id in list(self._clients.keys()):
            with contextlib.suppress(Exception):
                await self.disconnect(session_id)
