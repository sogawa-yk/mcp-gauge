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
