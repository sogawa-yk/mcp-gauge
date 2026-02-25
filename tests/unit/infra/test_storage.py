"""TraceStorageのユニットテスト。"""

from pathlib import Path

import aiosqlite
import pytest

from mcp_gauge.exceptions import TraceNotFoundError
from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.trace import (
    SessionStatus,
    TraceRecord,
    TraceSession,
    TraceSummary,
    TransportType,
)


@pytest.fixture
async def storage(tmp_path: Path) -> TraceStorage:
    """テスト用のTraceStorageを作成する。"""
    db_path = str(tmp_path / "test.db")
    s = TraceStorage(db_path)
    await s.init_db()
    return s


def _make_session(
    session_id: str = "sess-001",
    status: SessionStatus = SessionStatus.RUNNING,
) -> TraceSession:
    """テスト用のTraceSessionを作成する。"""
    return TraceSession(
        id=session_id,
        server_command="python -m server",
        server_args=["--port", "8080"],
        scenario_id="scenario-001",
        status=status,
        started_at="2026-01-01T00:00:00Z",
    )


def _make_record(
    record_id: str = "rec-001",
    session_id: str = "sess-001",
    sequence: int = 1,
    tool_name: str = "create",
    is_error: bool = False,
) -> TraceRecord:
    """テスト用のTraceRecordを作成する。"""
    return TraceRecord(
        id=record_id,
        session_id=session_id,
        sequence=sequence,
        tool_name=tool_name,
        arguments={"name": "test"},
        result={"ok": True} if not is_error else {"error": "fail"},
        is_error=is_error,
        duration_ms=100.0,
        timestamp="2026-01-01T00:00:01Z",
    )


def _make_summary() -> TraceSummary:
    """テスト用のTraceSummaryを作成する。"""
    return TraceSummary(
        total_calls=3,
        unique_tools=2,
        error_count=0,
        redundant_calls=1,
        total_duration_ms=300.0,
        recovery_steps=0,
        tool_call_sequence=["create", "list", "list"],
    )


class TestInitDb:
    """init_dbのテスト。"""

    async def test_creates_tables(self, tmp_path: Path):
        """テーブルが作成されること。"""
        db_path = str(tmp_path / "new.db")
        storage = TraceStorage(db_path)
        await storage.init_db()
        assert Path(db_path).exists()

    async def test_creates_parent_dirs(self, tmp_path: Path):
        """親ディレクトリが作成されること。"""
        db_path = str(tmp_path / "subdir" / "deep" / "test.db")
        storage = TraceStorage(db_path)
        await storage.init_db()
        assert Path(db_path).exists()

    async def test_idempotent(self, tmp_path: Path):
        """複数回呼び出してもエラーにならないこと。"""
        db_path = str(tmp_path / "test.db")
        storage = TraceStorage(db_path)
        await storage.init_db()
        await storage.init_db()  # 2回目


class TestSaveAndGetSession:
    """セッションの保存・取得テスト。"""

    async def test_save_and_get(self, storage: TraceStorage):
        """セッションを保存して取得できること。"""
        session = _make_session()
        await storage.save_session(session)
        result = await storage.get_session("sess-001")
        assert result.id == "sess-001"
        assert result.server_command == "python -m server"
        assert result.server_args == ["--port", "8080"]
        assert result.transport_type == TransportType.STDIO
        assert result.server_url is None
        assert result.status == SessionStatus.RUNNING

    async def test_save_and_get_remote_session(self, storage: TraceStorage):
        """リモートセッションを保存して取得できること。"""
        session = TraceSession(
            id="sess-remote",
            transport_type=TransportType.STREAMABLE_HTTP,
            server_url="http://localhost:8080/mcp",
            status=SessionStatus.RUNNING,
            started_at="2026-01-01T00:00:00Z",
        )
        await storage.save_session(session)
        result = await storage.get_session("sess-remote")
        assert result.transport_type == TransportType.STREAMABLE_HTTP
        assert result.server_url == "http://localhost:8080/mcp"
        assert result.server_command is None

    async def test_get_nonexistent_raises(self, storage: TraceStorage):
        """存在しないセッションでTraceNotFoundErrorが発生すること。"""
        with pytest.raises(TraceNotFoundError):
            await storage.get_session("nonexistent")

    async def test_save_with_task_success(self, storage: TraceStorage):
        """task_success付きで保存できること。"""
        session = _make_session()
        session.task_success = True
        await storage.save_session(session)
        result = await storage.get_session("sess-001")
        assert result.task_success is True


class TestUpdateSessionStatus:
    """セッションステータス更新のテスト。"""

    async def test_update_to_completed(self, storage: TraceStorage):
        """ステータスをcompletedに更新できること。"""
        await storage.save_session(_make_session())
        await storage.update_session_status(
            "sess-001",
            SessionStatus.COMPLETED,
            finished_at="2026-01-01T00:01:00Z",
            task_success=True,
        )
        result = await storage.get_session("sess-001")
        assert result.status == SessionStatus.COMPLETED
        assert result.finished_at == "2026-01-01T00:01:00Z"
        assert result.task_success is True


class TestSaveAndGetRecords:
    """レコードの保存・取得テスト。"""

    async def test_save_and_get(self, storage: TraceStorage):
        """レコードを保存して取得できること。"""
        await storage.save_session(_make_session())
        await storage.save_record(_make_record())
        records = await storage.get_records("sess-001")
        assert len(records) == 1
        assert records[0].tool_name == "create"

    async def test_multiple_records_ordered(self, storage: TraceStorage):
        """複数レコードがsequence順で返されること。"""
        await storage.save_session(_make_session())
        await storage.save_record(_make_record("rec-002", sequence=2, tool_name="list"))
        await storage.save_record(
            _make_record("rec-001", sequence=1, tool_name="create")
        )
        records = await storage.get_records("sess-001")
        assert len(records) == 2
        assert records[0].sequence == 1
        assert records[1].sequence == 2

    async def test_empty_session(self, storage: TraceStorage):
        """レコードなしのセッションで空リストが返ること。"""
        await storage.save_session(_make_session())
        records = await storage.get_records("sess-001")
        assert records == []


class TestSaveAndGetSummary:
    """サマリーの保存・取得テスト。"""

    async def test_save_and_get(self, storage: TraceStorage):
        """サマリーを保存して取得できること。"""
        await storage.save_session(_make_session())
        summary = _make_summary()
        await storage.save_summary("sess-001", summary)
        result = await storage.get_summary("sess-001")
        assert result.total_calls == 3
        assert result.unique_tools == 2
        assert result.tool_call_sequence == ["create", "list", "list"]

    async def test_get_nonexistent_raises(self, storage: TraceStorage):
        """存在しないサマリーでTraceNotFoundErrorが発生すること。"""
        with pytest.raises(TraceNotFoundError):
            await storage.get_summary("nonexistent")

    async def test_session_includes_summary(self, storage: TraceStorage):
        """セッション取得時にサマリーが含まれること。"""
        await storage.save_session(_make_session())
        await storage.save_summary("sess-001", _make_summary())
        session = await storage.get_session("sess-001")
        assert session.summary is not None
        assert session.summary.total_calls == 3


class TestRecoverSessions:
    """セッションリカバリのテスト。"""

    async def test_recover_running_sessions(self, storage: TraceStorage):
        """running状態のセッションがfailedに更新されること。"""
        await storage.save_session(_make_session("sess-001", SessionStatus.RUNNING))
        await storage.save_session(_make_session("sess-002", SessionStatus.COMPLETED))
        count = await storage.recover_sessions()
        assert count == 1
        result = await storage.get_session("sess-001")
        assert result.status == SessionStatus.FAILED

    async def test_recover_no_running(self, storage: TraceStorage):
        """running状態のセッションがない場合は0。"""
        await storage.save_session(_make_session("sess-001", SessionStatus.COMPLETED))
        count = await storage.recover_sessions()
        assert count == 0


class TestMigration:
    """スキーママイグレーションのテスト。"""

    async def test_migrate_adds_new_columns(self, tmp_path: Path):
        """旧スキーマDBにtransport_typeとserver_urlカラムが追加されること。"""
        db_path = str(tmp_path / "old.db")
        # 旧スキーマでDBを作成
        old_sql = """
        CREATE TABLE IF NOT EXISTS trace_sessions (
            id TEXT PRIMARY KEY,
            server_command TEXT NOT NULL,
            server_args TEXT,
            scenario_id TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            started_at TEXT NOT NULL,
            finished_at TEXT,
            task_success INTEGER
        );
        """
        async with aiosqlite.connect(db_path) as db:
            await db.executescript(old_sql)
            await db.execute(
                "INSERT INTO trace_sessions "
                "(id, server_command, server_args, status, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "sess-old", "python -m server", "[]",
                    "running", "2026-01-01T00:00:00Z",
                ),
            )
            await db.commit()

        # init_dbでマイグレーションが実行される
        storage = TraceStorage(db_path)
        await storage.init_db()

        # 新カラムが追加されていること
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("PRAGMA table_info(trace_sessions)")
            columns = {row[1] for row in await cursor.fetchall()}
            assert "transport_type" in columns
            assert "server_url" in columns

    async def test_migrate_preserves_existing_data(self, tmp_path: Path):
        """マイグレーション後も既存データが読み取れること。"""
        db_path = str(tmp_path / "old2.db")
        old_sql = """
        CREATE TABLE IF NOT EXISTS trace_sessions (
            id TEXT PRIMARY KEY,
            server_command TEXT NOT NULL,
            server_args TEXT,
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
        async with aiosqlite.connect(db_path) as db:
            await db.executescript(old_sql)
            await db.execute(
                "INSERT INTO trace_sessions "
                "(id, server_command, server_args, status, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "sess-old",
                    "python -m server",
                    '["--port", "8080"]',
                    "completed",
                    "2026-01-01T00:00:00Z",
                ),
            )
            await db.commit()

        storage = TraceStorage(db_path)
        await storage.init_db()

        result = await storage.get_session("sess-old")
        assert result.server_command == "python -m server"
        assert result.transport_type == TransportType.STDIO
        assert result.server_url is None
