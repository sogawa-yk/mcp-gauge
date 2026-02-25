"""SessionManagerのユニットテスト。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gauge.engines.session import SessionManager
from mcp_gauge.exceptions import SessionNotFoundError
from mcp_gauge.models.trace import TraceSummary


def _make_mock_trace_engine() -> AsyncMock:
    """モックTraceEngineを作成する。"""
    engine = AsyncMock()
    engine.start_session = AsyncMock(return_value="sess-001")
    engine.record_call = AsyncMock()
    engine.record_call.return_value = MagicMock(sequence=1)
    engine.stop_session = AsyncMock(
        return_value=TraceSummary(
            total_calls=1,
            unique_tools=1,
            error_count=0,
            redundant_calls=0,
            total_duration_ms=100.0,
            recovery_steps=0,
            tool_call_sequence=["create"],
        )
    )
    return engine


def _make_mock_tool() -> MagicMock:
    """モックMCPツールを作成する。"""
    tool = MagicMock()
    tool.name = "create"
    tool.description = "リソースを作成する"
    tool.inputSchema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }
    return tool


class TestConnect:
    """SessionManager.connectのテスト。"""

    async def test_connect_returns_session_and_tools(self):
        """接続成功でsession_idとツール一覧が返ること。"""
        trace_engine = _make_mock_trace_engine()
        manager = SessionManager(trace_engine, mcp_timeout_sec=10)

        mock_tool = _make_mock_tool()

        with patch("mcp_gauge.engines.session.MCPClientWrapper") as MockClient:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock(return_value=[mock_tool])
            MockClient.return_value = mock_client

            session_id, tools = await manager.connect("python -m server")

        assert session_id == "sess-001"
        assert len(tools) == 1
        assert tools[0]["name"] == "create"
        assert tools[0]["description"] == "リソースを作成する"
        trace_engine.start_session.assert_called_once()

    async def test_connect_stores_client(self):
        """接続後にクライアントが保持されること。"""
        trace_engine = _make_mock_trace_engine()
        manager = SessionManager(trace_engine)

        with patch("mcp_gauge.engines.session.MCPClientWrapper") as MockClient:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock(return_value=[])
            MockClient.return_value = mock_client

            session_id, _ = await manager.connect("python -m server")

        assert session_id in manager._clients


class TestProxyCall:
    """SessionManager.proxy_callのテスト。"""

    async def test_proxy_call_returns_result(self):
        """プロキシ呼び出しで結果とメトリクスが返ること。"""
        trace_engine = _make_mock_trace_engine()
        manager = SessionManager(trace_engine)

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(
            return_value=(
                {"content": ["created"], "is_error": False},
                False,
                50.0,
            )
        )
        manager._clients["sess-001"] = mock_client

        result = await manager.proxy_call("sess-001", "create", {"name": "test"})

        assert result["result"]["content"] == ["created"]
        assert result["metrics"]["duration_ms"] == 50.0
        assert result["metrics"]["tool_name"] == "create"
        trace_engine.record_call.assert_called_once()

    async def test_proxy_call_invalid_session(self):
        """無効なセッションでSessionNotFoundError。"""
        trace_engine = _make_mock_trace_engine()
        manager = SessionManager(trace_engine)

        with pytest.raises(SessionNotFoundError):
            await manager.proxy_call("nonexistent", "create", {})


class TestDisconnect:
    """SessionManager.disconnectのテスト。"""

    async def test_disconnect_returns_summary(self):
        """切断時にサマリーが返ること。"""
        trace_engine = _make_mock_trace_engine()
        manager = SessionManager(trace_engine)

        mock_client = AsyncMock()
        manager._clients["sess-001"] = mock_client

        summary = await manager.disconnect("sess-001")

        assert summary.total_calls == 1
        trace_engine.stop_session.assert_called_once()
        mock_client.close.assert_called_once()
        assert "sess-001" not in manager._clients

    async def test_disconnect_invalid_session(self):
        """無効なセッションでSessionNotFoundError。"""
        trace_engine = _make_mock_trace_engine()
        manager = SessionManager(trace_engine)

        with pytest.raises(SessionNotFoundError):
            await manager.disconnect("nonexistent")

    async def test_disconnect_with_task_success(self):
        """task_successがstop_sessionに渡されること。"""
        trace_engine = _make_mock_trace_engine()
        manager = SessionManager(trace_engine)
        manager._clients["sess-001"] = AsyncMock()

        await manager.disconnect("sess-001", task_success=True)

        trace_engine.stop_session.assert_called_once_with("sess-001", task_success=True)
