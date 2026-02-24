"""MCP Gaugeのカスタム例外クラス。"""


class GaugeError(Exception):
    """MCP Gaugeの基底例外クラス。"""


class ServerConnectionError(GaugeError):
    """対象MCPサーバーへの接続失敗。"""

    def __init__(self, server_command: str, cause: Exception | None = None) -> None:
        self.server_command = server_command
        self.cause = cause
        super().__init__(f"対象サーバーへの接続に失敗しました: {server_command}")


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


class LLMAPIError(GaugeError):
    """LLM APIの呼び出しに失敗。"""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        self.cause = cause
        super().__init__(f"LLM APIエラー: {message}")
