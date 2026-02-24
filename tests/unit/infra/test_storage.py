"""TraceStorageのユニットテスト。"""

from pathlib import Path

import pytest

from mcp_gauge.exceptions import TraceNotFoundError
from mcp_gauge.infra.storage import TraceStorage
from mcp_gauge.models.trace import (
    SessionStatus,
    TraceRecord,
    TraceSession,
    TraceSummary,
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
        assert result.status == SessionStatus.RUNNING

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
