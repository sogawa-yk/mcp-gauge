"""トレースデータのSQLite永続化。"""

import json
import os
from pathlib import Path

import aiosqlite

from mcp_gauge.exceptions import TraceNotFoundError
from mcp_gauge.models.trace import (
    SessionStatus,
    TraceRecord,
    TraceSession,
    TraceSummary,
    TransportType,
)

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS trace_sessions (
    id TEXT PRIMARY KEY,
    server_command TEXT,
    server_args TEXT,
    transport_type TEXT NOT NULL DEFAULT 'stdio',
    server_url TEXT,
    scenario_id TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    task_success INTEGER
);

CREATE TABLE IF NOT EXISTS trace_records (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES trace_sessions(id),
    sequence INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    result TEXT NOT NULL,
    is_error INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_session
    ON trace_records(session_id);

CREATE TABLE IF NOT EXISTS trace_summaries (
    session_id TEXT PRIMARY KEY REFERENCES trace_sessions(id),
    total_calls INTEGER NOT NULL,
    unique_tools INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    redundant_calls INTEGER NOT NULL,
    total_duration_ms REAL NOT NULL,
    recovery_steps INTEGER NOT NULL,
    tool_call_sequence TEXT NOT NULL
);
"""


class TraceStorage:
    """SQLiteへのトレースデータ永続化。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init_db(self) -> None:
        """テーブルを初期化し、WALモードを有効化する。"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(_CREATE_TABLES_SQL)
            await self._migrate(db)
            await db.commit()

        # パーミッション600
        import contextlib

        with contextlib.suppress(OSError):
            os.chmod(self.db_path, 0o600)

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        """既存DBに新カラムを追加するマイグレーション。"""
        cursor = await db.execute("PRAGMA table_info(trace_sessions)")
        columns = {row[1] for row in await cursor.fetchall()}

        if "transport_type" not in columns:
            await db.execute(
                "ALTER TABLE trace_sessions "
                "ADD COLUMN transport_type TEXT NOT NULL DEFAULT 'stdio'"
            )
        if "server_url" not in columns:
            await db.execute(
                "ALTER TABLE trace_sessions ADD COLUMN server_url TEXT"
            )

    async def recover_sessions(self) -> int:
        """status='running'のセッションを'failed'に更新する。"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE trace_sessions SET status = ? WHERE status = ?",
                (SessionStatus.FAILED.value, SessionStatus.RUNNING.value),
            )
            await db.commit()
            return cursor.rowcount

    async def save_session(self, session: TraceSession) -> None:
        """セッションを保存する。"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO trace_sessions "
                "(id, server_command, server_args, transport_type, "
                "server_url, scenario_id, "
                "status, started_at, finished_at, task_success) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.server_command,
                    json.dumps(session.server_args),
                    session.transport_type.value,
                    session.server_url,
                    session.scenario_id,
                    session.status.value,
                    session.started_at,
                    session.finished_at,
                    (
                        int(session.task_success)
                        if session.task_success is not None
                        else None
                    ),
                ),
            )
            await db.commit()

    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        finished_at: str | None = None,
        task_success: bool | None = None,
    ) -> None:
        """セッションのステータスを更新する。"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE trace_sessions "
                "SET status = ?, finished_at = ?, task_success = ? "
                "WHERE id = ?",
                (
                    status.value,
                    finished_at,
                    (int(task_success) if task_success is not None else None),
                    session_id,
                ),
            )
            await db.commit()

    async def save_record(self, record: TraceRecord) -> None:
        """トレースレコードを保存する（都度コミット）。"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO trace_records "
                "(id, session_id, sequence, tool_name, arguments, "
                "result, is_error, duration_ms, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.session_id,
                    record.sequence,
                    record.tool_name,
                    json.dumps(record.arguments),
                    json.dumps(record.result),
                    int(record.is_error),
                    record.duration_ms,
                    record.timestamp,
                ),
            )
            await db.commit()

    async def save_summary(self, session_id: str, summary: TraceSummary) -> None:
        """サマリーを保存する。"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO trace_summaries "
                "(session_id, total_calls, unique_tools, "
                "error_count, redundant_calls, total_duration_ms, "
                "recovery_steps, tool_call_sequence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    summary.total_calls,
                    summary.unique_tools,
                    summary.error_count,
                    summary.redundant_calls,
                    summary.total_duration_ms,
                    summary.recovery_steps,
                    json.dumps(summary.tool_call_sequence),
                ),
            )
            await db.commit()

    async def get_session(self, session_id: str) -> TraceSession:
        """セッションを取得する。"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM trace_sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise TraceNotFoundError(session_id)

            summary = await self._get_summary_or_none(db, session_id)

            return TraceSession(
                id=row["id"],
                server_command=row["server_command"],
                server_args=json.loads(row["server_args"] or "[]"),
                transport_type=TransportType(row["transport_type"]),
                server_url=row["server_url"],
                scenario_id=row["scenario_id"],
                status=SessionStatus(row["status"]),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                task_success=(
                    bool(row["task_success"])
                    if row["task_success"] is not None
                    else None
                ),
                summary=summary,
            )

    async def get_records(self, session_id: str) -> list[TraceRecord]:
        """セッションのトレースレコードを取得する。"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM trace_records WHERE session_id = ? ORDER BY sequence",
                (session_id,),
            )
            rows = await cursor.fetchall()
            return [
                TraceRecord(
                    id=row["id"],
                    session_id=row["session_id"],
                    sequence=row["sequence"],
                    tool_name=row["tool_name"],
                    arguments=json.loads(row["arguments"]),
                    result=json.loads(row["result"]),
                    is_error=bool(row["is_error"]),
                    duration_ms=row["duration_ms"],
                    timestamp=row["timestamp"],
                )
                for row in rows
            ]

    async def get_summary(self, session_id: str) -> TraceSummary:
        """サマリーを取得する。"""
        async with aiosqlite.connect(self.db_path) as db:
            summary = await self._get_summary_or_none(db, session_id)
            if summary is None:
                raise TraceNotFoundError(session_id)
            return summary

    async def _get_summary_or_none(
        self, db: aiosqlite.Connection, session_id: str
    ) -> TraceSummary | None:
        """サマリーを取得する（存在しない場合はNone）。"""
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM trace_summaries WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return TraceSummary(
            total_calls=row["total_calls"],
            unique_tools=row["unique_tools"],
            error_count=row["error_count"],
            redundant_calls=row["redundant_calls"],
            total_duration_ms=row["total_duration_ms"],
            recovery_steps=row["recovery_steps"],
            tool_call_sequence=json.loads(row["tool_call_sequence"]),
        )
