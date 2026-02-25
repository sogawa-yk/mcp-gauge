"""E2Eテスト: Streamable HTTPトランスポートでのMCP Gauge動作検証。

実際のHTTPサーバーを起動し、gauge_connect → gauge_proxy_call → gauge_disconnect
のフロー全体をStreamable HTTPトランスポート経由で検証する。
"""

from typing import Any

from mcp_gauge.server import GaugeServer


class TestHttpConnectE2E:
    """Streamable HTTPトランスポートでの接続テスト。"""

    async def test_connect_via_streamable_http(
        self,
        gauge_server: GaugeServer,
        http_mock_server_url: str,
    ) -> None:
        """Streamable HTTPサーバーに接続し、ツール一覧を取得できる。"""
        result = await gauge_server._dispatch(
            "gauge_connect",
            {"server_url": http_mock_server_url},
        )

        assert "error" not in result
        session_id = result["session_id"]
        tools = result["tools"]
        assert isinstance(session_id, str)
        assert len(tools) == 3

        tool_names = {t["name"] for t in tools}
        assert "echo" in tool_names
        assert "create_resource" in tool_names
        assert "list_resources" in tool_names

        # クリーンアップ
        await gauge_server._dispatch(
            "gauge_disconnect",
            {"session_id": session_id, "task_success": True},
        )


class TestHttpProxyFlowE2E:
    """Streamable HTTPトランスポートでのプロキシフローテスト。"""

    async def test_full_proxy_flow_over_http(
        self,
        gauge_server: GaugeServer,
        http_mock_server_url: str,
    ) -> None:
        """HTTP経由で接続→プロキシ呼び出し→切断の全フローが動作する。"""
        # Connect
        connect_result = await gauge_server._dispatch(
            "gauge_connect",
            {"server_url": http_mock_server_url},
        )
        assert "error" not in connect_result
        session_id = connect_result["session_id"]

        # Proxy call: echo
        echo_result = await gauge_server._dispatch(
            "gauge_proxy_call",
            {
                "session_id": session_id,
                "tool_name": "echo",
                "arguments": {"message": "hello http"},
            },
        )
        assert "error" not in echo_result
        assert echo_result["result"]["is_error"] is False
        assert "hello http" in echo_result["result"]["content"][0]
        assert echo_result["metrics"]["sequence"] == 1

        # Proxy call: create_resource
        create_result = await gauge_server._dispatch(
            "gauge_proxy_call",
            {
                "session_id": session_id,
                "tool_name": "create_resource",
                "arguments": {"name": "http-res", "resource_type": "file"},
            },
        )
        assert create_result["metrics"]["sequence"] == 2
        assert create_result["result"]["is_error"] is False

        # Disconnect
        disconnect_result = await gauge_server._dispatch(
            "gauge_disconnect",
            {"session_id": session_id, "task_success": True},
        )
        assert "error" not in disconnect_result
        assert disconnect_result["total_calls"] == 2
        assert disconnect_result["unique_tools"] == 2
        assert disconnect_result["error_count"] == 0

    async def test_multiple_sequential_calls_over_http(
        self,
        gauge_server: GaugeServer,
        http_mock_server_url: str,
    ) -> None:
        """HTTP経由で複数のツール呼び出しが順次実行できる。"""
        connect_result = await gauge_server._dispatch(
            "gauge_connect",
            {"server_url": http_mock_server_url},
        )
        session_id = connect_result["session_id"]

        # 3回連続でechoを呼ぶ
        for i in range(3):
            result = await gauge_server._dispatch(
                "gauge_proxy_call",
                {
                    "session_id": session_id,
                    "tool_name": "echo",
                    "arguments": {"message": f"msg-{i}"},
                },
            )
            assert result["result"]["is_error"] is False
            assert f"msg-{i}" in result["result"]["content"][0]
            assert result["metrics"]["sequence"] == i + 1

        disconnect_result = await gauge_server._dispatch(
            "gauge_disconnect",
            {"session_id": session_id, "task_success": True},
        )
        assert disconnect_result["total_calls"] == 3


class TestHttpLintE2E:
    """Streamable HTTPトランスポートでのlintテスト。"""

    async def test_lint_via_http(
        self,
        gauge_server: GaugeServer,
        http_mock_server_url: str,
    ) -> None:
        """HTTPサーバーに対してlintを実行できる。"""
        result = await gauge_server._dispatch(
            "gauge_lint",
            {"server_url": http_mock_server_url},
        )

        assert "error" not in result
        assert result["total_tools"] == 3
        assert isinstance(result["issues"], list)


class TestHttpEvaluateE2E:
    """Streamable HTTPトランスポートでのevaluateテスト。"""

    async def _create_http_session(
        self,
        gauge_server: GaugeServer,
        http_mock_server_url: str,
        tool_calls: list[dict[str, Any]],
    ) -> str:
        """HTTPサーバーに接続してツール呼び出しを行い、セッションを作成する。"""
        connect = await gauge_server._dispatch(
            "gauge_connect",
            {"server_url": http_mock_server_url},
        )
        session_id = connect["session_id"]

        for call in tool_calls:
            await gauge_server._dispatch(
                "gauge_proxy_call",
                {
                    "session_id": session_id,
                    "tool_name": call["tool_name"],
                    "arguments": call.get("arguments", {}),
                },
            )

        await gauge_server._dispatch(
            "gauge_disconnect",
            {"session_id": session_id, "task_success": True},
        )
        return session_id

    async def test_evaluate_http_session(
        self,
        gauge_server: GaugeServer,
        http_mock_server_url: str,
    ) -> None:
        """HTTPセッションを評価できる。"""
        session_id = await self._create_http_session(
            gauge_server,
            http_mock_server_url,
            [
                {"tool_name": "echo", "arguments": {"message": "test"}},
                {
                    "tool_name": "create_resource",
                    "arguments": {"name": "res1", "resource_type": "doc"},
                },
            ],
        )

        result = await gauge_server._dispatch(
            "gauge_evaluate",
            {
                "session_id": session_id,
                "success_criteria": {
                    "max_steps": 5,
                    "required_tools": ["echo", "create_resource"],
                    "must_succeed": True,
                },
                "task_success": True,
            },
        )

        assert "error" not in result
        assert result["passed"] is True
