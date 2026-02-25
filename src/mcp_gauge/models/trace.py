"""トレース関連のデータモデル。"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class SessionStatus(StrEnum):
    """トレースセッションのステータス。"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TransportType(StrEnum):
    """MCPトランスポートの種類。"""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class ConnectionParams(BaseModel):
    """MCP接続パラメータ。"""

    transport_type: TransportType = TransportType.STDIO
    server_command: str | None = None
    server_args: list[str] = []
    server_url: str | None = None
    headers: dict[str, str] = {}
    env: dict[str, str] | None = None

    def display_target(self) -> str:
        """ログ/エラー用の接続先表示名を返す。"""
        if self.server_url:
            return self.server_url
        if self.server_command:
            parts = [self.server_command, *self.server_args]
            return " ".join(parts)
        return "(unknown)"


class TraceRecord(BaseModel):
    """個別のツール呼び出し記録。"""

    id: str
    session_id: str
    sequence: int
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    is_error: bool
    duration_ms: float
    timestamp: str


class TraceSummary(BaseModel):
    """セッションの集計データ。"""

    total_calls: int
    unique_tools: int
    error_count: int
    redundant_calls: int
    total_duration_ms: float
    recovery_steps: int
    tool_call_sequence: list[str]


class TraceSession(BaseModel):
    """テスト実行の単位。"""

    id: str
    server_command: str | None = None
    server_args: list[str] = []
    transport_type: TransportType = TransportType.STDIO
    server_url: str | None = None
    scenario_id: str | None = None
    status: SessionStatus = SessionStatus.RUNNING
    started_at: str
    finished_at: str | None = None
    task_success: bool | None = None
    summary: TraceSummary | None = None
