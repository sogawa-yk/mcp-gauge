"""MCP Gaugeのカスタム例外クラス。"""


class GaugeError(Exception):
    """MCP Gaugeの基底例外クラス。"""


class ServerConnectionError(GaugeError):
    """対象MCPサーバーへの接続失敗。"""

    def __init__(self, target: str, cause: Exception | None = None) -> None:
        self.target = target
        self.cause = cause
        super().__init__(f"対象サーバーへの接続に失敗しました: {target}")


class InvalidScenarioError(GaugeError):
    """シナリオ定義が不正。"""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"シナリオ定義エラー [{field}]: {message}")


class TraceNotFoundError(GaugeError):
    """指定されたトレースIDが存在しない。"""

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        super().__init__(f"トレースが見つかりません: {trace_id}")


class SessionNotFoundError(GaugeError):
    """指定されたセッションIDがアクティブでない。"""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"アクティブなセッションが見つかりません: {session_id}")


class ToolCallTimeoutError(GaugeError):
    """ツール呼び出しがタイムアウト。"""

    def __init__(self, tool_name: str, timeout_sec: int) -> None:
        self.tool_name = tool_name
        self.timeout_sec = timeout_sec
        super().__init__(
            f"ツール '{tool_name}' の呼び出しが{timeout_sec}秒でタイムアウトしました"
        )


class ConnectionLostError(GaugeError):
    """バックグラウンド接続が予期せず切断された。"""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(
            f"ツール '{tool_name}' 呼び出し前に接続が切断されました"
        )
