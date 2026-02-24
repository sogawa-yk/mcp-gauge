"""トレース関連のデータモデル。"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class SessionStatus(StrEnum):
    """トレースセッションのステータス。"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


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
    server_command: str
    server_args: list[str]
    scenario_id: str | None = None
    status: SessionStatus = SessionStatus.RUNNING
    started_at: str
    finished_at: str | None = None
    task_success: bool | None = None
    summary: TraceSummary | None = None
