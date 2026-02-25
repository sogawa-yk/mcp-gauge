"""E2Eテスト: MCP Gaugeでモックサーバーをテストする（dogfooding）。

GaugeServerの_dispatchメソッドを通じて、MCPサーバーレイヤー →
エンジンレイヤー → インフラレイヤーの全フローを検証する。
テスト対象MCPサーバーとして、モックMCPサーバーをサブプロセスで起動する。
"""

from typing import Any

from mcp_gauge.server import GaugeServer


class TestGaugeLintE2E:
    """gauge_lintのE2Eテスト。"""

    async def test_lint_detects_issues_in_mock_server(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """モックサーバーのリンティング問題を検出する。"""
        result = await gauge_server._dispatch(
            "gauge_lint",
            {
                "server_command": mock_server_command,
                "server_args": mock_server_args,
            },
        )

        assert "error" not in result
        assert result["total_tools"] == 5
        assert result["total_issues"] > 0

        rules_found = {issue["rule"] for issue in result["issues"]}
        # create_resourceのdescriptionに「適切な」が含まれる
        assert "ambiguous-description" in rules_found
        # create_resourceのtypeパラメータにdescriptionがない
        assert "missing-param-description" in rules_found

    async def test_lint_returns_structured_json(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """リンティング結果が構造化JSONで返ること。"""
        result = await gauge_server._dispatch(
            "gauge_lint",
            {
                "server_command": mock_server_command,
                "server_args": mock_server_args,
            },
        )

        assert "total_tools" in result
        assert "total_issues" in result
        assert "issues" in result
        assert isinstance(result["issues"], list)

        for issue in result["issues"]:
            assert "tool_name" in issue
            assert "severity" in issue
            assert "rule" in issue
            assert "message" in issue
            assert "suggestion" in issue
            assert "field" in issue


class TestProxyFlowE2E:
    """gauge_connect → gauge_proxy_call → gauge_disconnectのE2Eテスト。"""

    async def test_full_proxy_flow(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """接続→プロキシ呼び出し→切断の全フローが動作する。"""
        # Connect
        connect_result = await gauge_server._dispatch(
            "gauge_connect",
            {
                "server_command": mock_server_command,
                "server_args": mock_server_args,
            },
        )

        assert "error" not in connect_result
        session_id = connect_result["session_id"]
        tools = connect_result["tools"]
        assert isinstance(session_id, str)
        assert len(tools) == 5

        tool_names = {t["name"] for t in tools}
        assert "echo" in tool_names
        assert "create_resource" in tool_names

        # Proxy call: echo
        echo_result = await gauge_server._dispatch(
            "gauge_proxy_call",
            {
                "session_id": session_id,
                "tool_name": "echo",
                "arguments": {"message": "hello e2e"},
            },
        )

        assert "error" not in echo_result
        assert echo_result["result"]["is_error"] is False
        assert "hello e2e" in echo_result["result"]["content"][0]
        assert echo_result["metrics"]["sequence"] == 1

        # Proxy call: create_resource
        create_result = await gauge_server._dispatch(
            "gauge_proxy_call",
            {
                "session_id": session_id,
                "tool_name": "create_resource",
                "arguments": {"name": "test-res", "type": "file"},
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

    async def test_proxy_call_with_error_tool(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """エラーを返すツールのプロキシ呼び出しがトレースに記録される。"""
        connect_result = await gauge_server._dispatch(
            "gauge_connect",
            {
                "server_command": mock_server_command,
                "server_args": mock_server_args,
            },
        )
        session_id = connect_result["session_id"]

        # fail_alwaysを呼ぶ
        fail_result = await gauge_server._dispatch(
            "gauge_proxy_call",
            {
                "session_id": session_id,
                "tool_name": "fail_always",
                "arguments": {},
            },
        )

        assert fail_result["result"]["is_error"] is True

        # 正常ツールも呼ぶ
        await gauge_server._dispatch(
            "gauge_proxy_call",
            {
                "session_id": session_id,
                "tool_name": "echo",
                "arguments": {"message": "recovery"},
            },
        )

        disconnect_result = await gauge_server._dispatch(
            "gauge_disconnect",
            {"session_id": session_id, "task_success": True},
        )

        assert disconnect_result["total_calls"] == 2
        assert disconnect_result["error_count"] == 1
        assert disconnect_result["recovery_steps"] == 1


class TestGaugeEvaluateE2E:
    """gauge_evaluateのE2Eテスト。"""

    async def _create_session(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> str:
        """テスト用セッションを作成し、いくつかのツールを呼び出して終了する。"""
        connect = await gauge_server._dispatch(
            "gauge_connect",
            {
                "server_command": mock_server_command,
                "server_args": mock_server_args,
            },
        )
        session_id = connect["session_id"]

        await gauge_server._dispatch(
            "gauge_proxy_call",
            {
                "session_id": session_id,
                "tool_name": "create_resource",
                "arguments": {"name": "eval-test", "type": "doc"},
            },
        )
        await gauge_server._dispatch(
            "gauge_proxy_call",
            {
                "session_id": session_id,
                "tool_name": "list_resources",
                "arguments": {},
            },
        )

        await gauge_server._dispatch(
            "gauge_disconnect",
            {"session_id": session_id, "task_success": True},
        )
        return session_id

    async def test_evaluate_passes_with_valid_criteria(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """成功条件を満たすセッションがpassedになる。"""
        session_id = await self._create_session(
            gauge_server, mock_server_command, mock_server_args
        )

        result = await gauge_server._dispatch(
            "gauge_evaluate",
            {
                "session_id": session_id,
                "success_criteria": {
                    "max_steps": 5,
                    "required_tools": ["create_resource", "list_resources"],
                    "forbidden_tools": ["delete_resource"],
                    "must_succeed": True,
                },
                "task_success": True,
            },
        )

        assert "error" not in result
        assert result["passed"] is True
        assert result["task_success"] is True
        assert result["criteria_evaluation"]["max_steps"]["passed"] is True
        assert result["criteria_evaluation"]["required_tools"]["passed"] is True
        assert result["criteria_evaluation"]["forbidden_tools"]["passed"] is True
        assert result["criteria_evaluation"]["must_succeed"]["passed"] is True

    async def test_evaluate_fails_with_exceeded_steps(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """max_stepsを超えるとfailedになる。"""
        session_id = await self._create_session(
            gauge_server, mock_server_command, mock_server_args
        )

        result = await gauge_server._dispatch(
            "gauge_evaluate",
            {
                "session_id": session_id,
                "success_criteria": {
                    "max_steps": 1,
                },
            },
        )

        assert result["passed"] is False
        assert result["criteria_evaluation"]["max_steps"]["passed"] is False
        assert result["criteria_evaluation"]["max_steps"]["actual"] == 2

    async def test_evaluate_fails_with_missing_required_tools(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """必須ツールが呼ばれていないとfailedになる。"""
        session_id = await self._create_session(
            gauge_server, mock_server_command, mock_server_args
        )

        result = await gauge_server._dispatch(
            "gauge_evaluate",
            {
                "session_id": session_id,
                "success_criteria": {
                    "required_tools": ["echo", "create_resource"],
                },
            },
        )

        assert result["passed"] is False
        assert "echo" in result["criteria_evaluation"]["required_tools"]["missing"]


class TestGaugeCompareE2E:
    """gauge_compareのE2Eテスト。"""

    async def _create_session_with_calls(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
        tool_calls: list[dict[str, Any]],
        task_success: bool = True,
    ) -> str:
        """指定されたツール呼び出しでセッションを作成する。"""
        connect = await gauge_server._dispatch(
            "gauge_connect",
            {
                "server_command": mock_server_command,
                "server_args": mock_server_args,
            },
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
            {"session_id": session_id, "task_success": task_success},
        )
        return session_id

    async def test_compare_two_sessions(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """2つのセッションのメトリクスを比較できる。"""
        # ベースライン: 3回のツール呼び出し（エラー1回含む）
        baseline_id = await self._create_session_with_calls(
            gauge_server,
            mock_server_command,
            mock_server_args,
            [
                {"tool_name": "echo", "arguments": {"message": "a"}},
                {"tool_name": "fail_always"},
                {"tool_name": "echo", "arguments": {"message": "b"}},
            ],
        )

        # 改善版: 2回のツール呼び出し（エラーなし）
        current_id = await self._create_session_with_calls(
            gauge_server,
            mock_server_command,
            mock_server_args,
            [
                {"tool_name": "echo", "arguments": {"message": "a"}},
                {
                    "tool_name": "create_resource",
                    "arguments": {"name": "x", "type": "t"},
                },
            ],
        )

        result = await gauge_server._dispatch(
            "gauge_compare",
            {
                "baseline_trace_id": baseline_id,
                "current_trace_id": current_id,
            },
        )

        assert "error" not in result
        assert result["baseline_trace_id"] == baseline_id
        assert result["current_trace_id"] == current_id
        assert result["overall_verdict"] in (
            "improved",
            "degraded",
            "unchanged",
            "mixed",
        )

        metrics = result["metrics"]
        assert "total_calls" in metrics
        assert "error_count" in metrics
        # 改善版はエラーが少ない
        assert metrics["error_count"]["verdict"] == "improved"


class TestGaugeReportE2E:
    """gauge_reportのE2Eテスト。"""

    async def test_report_from_multiple_sessions(
        self,
        gauge_server: GaugeServer,
        mock_server_command: str,
        mock_server_args: list[str],
    ) -> None:
        """複数セッションから統合レポートを生成できる。"""
        trace_ids = []
        for i in range(2):
            connect = await gauge_server._dispatch(
                "gauge_connect",
                {
                    "server_command": mock_server_command,
                    "server_args": mock_server_args,
                },
            )
            session_id = connect["session_id"]

            await gauge_server._dispatch(
                "gauge_proxy_call",
                {
                    "session_id": session_id,
                    "tool_name": "echo",
                    "arguments": {"message": f"report-test-{i}"},
                },
            )
            await gauge_server._dispatch(
                "gauge_disconnect",
                {"session_id": session_id, "task_success": True},
            )
            trace_ids.append(session_id)

        result = await gauge_server._dispatch(
            "gauge_report",
            {"trace_ids": trace_ids},
        )

        assert "error" not in result
        assert len(result["trace_ids"]) == 2
        assert result["generated_at"] is not None
        assert len(result["sessions"]) == 2
        assert isinstance(result["aggregated_calls"], float)
        assert isinstance(result["aggregated_errors"], float)
        assert isinstance(result["recommendations"], list)
