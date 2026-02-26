"""MCPClientWrapperのユニットテスト。"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, ErrorData, TextContent

from mcp_gauge.exceptions import ConnectionLostError, ToolCallTimeoutError
from mcp_gauge.infra.mcp_client import MCPClientWrapper


def _make_connected_client(
    timeout_sec: int = 30,
    tool_call_timeout_sec: int = 300,
) -> MCPClientWrapper:
    """接続済み状態のMCPClientWrapperを作成する。"""
    client = MCPClientWrapper(
        timeout_sec=timeout_sec,
        tool_call_timeout_sec=tool_call_timeout_sec,
    )
    client._session = AsyncMock()
    client._bg_task = MagicMock(spec=asyncio.Task)
    client._bg_task.done.return_value = False
    return client


class TestCallToolTimeout:
    """call_toolのタイムアウト関連テスト。"""

    @pytest.mark.asyncio
    async def test_timeout_raises_tool_call_timeout_error(self) -> None:
        """MCP SDKが408エラーを返した場合、ToolCallTimeoutErrorを送出する。"""
        client = _make_connected_client(tool_call_timeout_sec=60)
        mcp_error = McpError(ErrorData(code=408, message="Request timed out"))
        client._session.call_tool = AsyncMock(side_effect=mcp_error)

        with pytest.raises(ToolCallTimeoutError) as exc_info:
            await client.call_tool("slow_tool", {"key": "value"})

        assert exc_info.value.tool_name == "slow_tool"
        assert exc_info.value.timeout_sec == 60
        assert "slow_tool" in str(exc_info.value)
        assert "60" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_408_mcp_error_propagates(self) -> None:
        """408以外のMcpErrorはそのまま伝播する。"""
        client = _make_connected_client()
        mcp_error = McpError(ErrorData(code=500, message="Internal error"))
        client._session.call_tool = AsyncMock(side_effect=mcp_error)

        with pytest.raises(McpError) as exc_info:
            await client.call_tool("some_tool", {})

        assert exc_info.value.error.code == 500

    @pytest.mark.asyncio
    async def test_read_timeout_uses_tool_call_timeout(self) -> None:
        """read_timeout_secondsにtool_call_timeout_secが渡されること。"""
        client = _make_connected_client(
            timeout_sec=30, tool_call_timeout_sec=600
        )
        client._session.call_tool = AsyncMock(
            return_value=CallToolResult(
                content=[TextContent(type="text", text="ok")],
                isError=False,
            )
        )

        await client.call_tool("my_tool", {"arg": 1})

        client._session.call_tool.assert_called_once_with(
            "my_tool",
            {"arg": 1},
            read_timeout_seconds=timedelta(seconds=600),
        )

    @pytest.mark.asyncio
    async def test_default_tool_call_timeout_is_300(self) -> None:
        """tool_call_timeout_secのデフォルト値が300であること。"""
        client = MCPClientWrapper()
        assert client.tool_call_timeout_sec == 300


class TestCallToolConnectionLost:
    """call_toolの接続断検出テスト。"""

    @pytest.mark.asyncio
    async def test_bg_task_done_raises_connection_lost_error(self) -> None:
        """bg_taskが終了済みの場合、ConnectionLostErrorを送出する。"""
        client = _make_connected_client()
        client._bg_task.done.return_value = True  # type: ignore[union-attr]

        with pytest.raises(ConnectionLostError) as exc_info:
            await client.call_tool("any_tool", {})

        assert exc_info.value.tool_name == "any_tool"
        assert "any_tool" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bg_task_alive_proceeds_normally(self) -> None:
        """bg_taskが生きている場合、正常にツール呼び出しが行われること。"""
        client = _make_connected_client()
        client._session.call_tool = AsyncMock(
            return_value=CallToolResult(
                content=[TextContent(type="text", text="result")],
                isError=False,
            )
        )

        result_dict, is_error, duration_ms = await client.call_tool(
            "working_tool", {"x": 1}
        )

        assert result_dict["content"] == ["result"]
        assert is_error is False
        assert duration_ms >= 0

    @pytest.mark.asyncio
    async def test_no_session_raises_runtime_error(self) -> None:
        """セッションが未接続の場合、RuntimeErrorを送出する。"""
        client = MCPClientWrapper()

        with pytest.raises(RuntimeError, match="Not connected"):
            await client.call_tool("any_tool", {})

    @pytest.mark.asyncio
    async def test_bg_task_none_skips_check(self) -> None:
        """bg_taskがNoneの場合、接続チェックをスキップして通常処理する。"""
        client = MCPClientWrapper()
        client._session = AsyncMock()
        client._bg_task = None
        client._session.call_tool = AsyncMock(
            return_value=CallToolResult(
                content=[TextContent(type="text", text="ok")],
                isError=False,
            )
        )

        result_dict, is_error, duration_ms = await client.call_tool(
            "tool", {}
        )

        assert result_dict["content"] == ["ok"]
