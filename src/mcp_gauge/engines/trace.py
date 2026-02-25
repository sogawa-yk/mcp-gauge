"""LLM行動トレーシングエンジン。"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mcp_gauge.exceptions import TraceNotFoundError
from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.trace import (
    ConnectionParams,
    SessionStatus,
    TraceRecord,
    TraceSession,
    TraceSummary,
)


def _args_similar(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """引数の類似度を判定する。

    キーセットが同一で、各キーの値が完全一致またはNone/空値の
    等価ペアの場合にTrueを返す。
    """
    if set(a.keys()) != set(b.keys()):
        return False
    _empty: tuple[None, str, list[Any], dict[str, Any]] = (None, "", [], {})
    for key in a:
        val_a = a[key]
        val_b = b[key]
        if val_a == val_b:
            continue
        # None/空文字/空リスト/空辞書を等価とみなす
        if val_a in _empty and val_b in _empty:
            continue
        return False
    return True


def detect_redundant_calls(
    records: list[TraceRecord],
) -> int:
    """冗長な再呼び出しを検出する。"""
    redundant = 0
    for i in range(1, len(records)):
        prev = records[i - 1]
        curr = records[i]
        if curr.tool_name != prev.tool_name:
            continue
        if prev.is_error:
            continue  # リトライは冗長ではない
        if _args_similar(prev.arguments, curr.arguments):
            redundant += 1
    return redundant


def count_recovery_steps(
    records: list[TraceRecord],
) -> int:
    """エラーリカバリに要した追加ステップを計算する。"""
    recovery_steps = 0
    in_recovery = False
    error_tool: str | None = None
    for record in records:
        if record.is_error:
            in_recovery = True
            error_tool = record.tool_name
            continue
        if in_recovery:
            recovery_steps += 1
            # 異なるツールが成功した時点でリカバリ完了
            if record.tool_name != error_tool:
                in_recovery = False
                error_tool = None
    return recovery_steps


class TraceEngine:
    """LLM行動トレーシングエンジン。"""

    def __init__(self, storage: TraceStorage) -> None:
        self.storage = storage
        self.active_sessions: dict[str, TraceSession] = {}
        self._sequence_counters: dict[str, int] = {}

    async def start_session(
        self,
        params: ConnectionParams,
        scenario_id: str | None = None,
    ) -> str:
        """トレースセッションを開始しtrace_idを返す。"""
        session_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        session = TraceSession(
            id=session_id,
            server_command=params.server_command,
            server_args=params.server_args,
            transport_type=params.transport_type,
            server_url=params.server_url,
            scenario_id=scenario_id,
            status=SessionStatus.RUNNING,
            started_at=now,
        )
        await self.storage.save_session(session)
        self.active_sessions[session_id] = session
        self._sequence_counters[session_id] = 0
        return session_id

    async def record_call(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        is_error: bool,
        duration_ms: float,
    ) -> TraceRecord:
        """ツール呼び出しを記録する。"""
        if session_id not in self.active_sessions:
            raise TraceNotFoundError(session_id)

        self._sequence_counters[session_id] += 1
        now = datetime.now(UTC).isoformat()

        record = TraceRecord(
            id=str(uuid4()),
            session_id=session_id,
            sequence=self._sequence_counters[session_id],
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            is_error=is_error,
            duration_ms=duration_ms,
            timestamp=now,
        )
        await self.storage.save_record(record)
        return record

    async def stop_session(
        self,
        session_id: str,
        task_success: bool | None = None,
    ) -> TraceSummary:
        """セッションを終了しサマリーを返す。"""
        if session_id not in self.active_sessions:
            raise TraceNotFoundError(session_id)

        records = await self.storage.get_records(session_id)
        summary = self._calculate_summary(records)

        now = datetime.now(UTC).isoformat()
        await self.storage.update_session_status(
            session_id,
            SessionStatus.COMPLETED,
            finished_at=now,
            task_success=task_success,
        )
        await self.storage.save_summary(session_id, summary)

        del self.active_sessions[session_id]
        del self._sequence_counters[session_id]

        return summary

    def _calculate_summary(self, records: list[TraceRecord]) -> TraceSummary:
        """トレースレコードからサマリーを計算する。"""
        if not records:
            return TraceSummary(
                total_calls=0,
                unique_tools=0,
                error_count=0,
                redundant_calls=0,
                total_duration_ms=0.0,
                recovery_steps=0,
                tool_call_sequence=[],
            )

        tool_names = [r.tool_name for r in records]
        return TraceSummary(
            total_calls=len(records),
            unique_tools=len(set(tool_names)),
            error_count=sum(1 for r in records if r.is_error),
            redundant_calls=detect_redundant_calls(records),
            total_duration_ms=sum(r.duration_ms for r in records),
            recovery_steps=count_recovery_steps(records),
            tool_call_sequence=tool_names,
        )
