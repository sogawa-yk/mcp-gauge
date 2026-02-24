"""TraceEngineのユニットテスト。"""

from unittest.mock import AsyncMock

import pytest

from mcp_gauge.engines.trace import (
    TraceEngine,
    _args_similar,
    count_recovery_steps,
    detect_redundant_calls,
)
from mcp_gauge.exceptions import TraceNotFoundError
from mcp_gauge.models.trace import TraceRecord


def _make_record(
    sequence: int,
    tool_name: str,
    arguments: dict | None = None,
    is_error: bool = False,
) -> TraceRecord:
    """テスト用のTraceRecordを作成する。"""
    return TraceRecord(
        id=f"rec-{sequence:03d}",
        session_id="sess-001",
        sequence=sequence,
        tool_name=tool_name,
        arguments=arguments or {},
        result={"ok": True} if not is_error else {"error": "fail"},
        is_error=is_error,
        duration_ms=100.0,
        timestamp=f"2026-01-01T00:00:{sequence:02d}Z",
    )


class TestArgsSimilar:
    """_args_similar関数のテスト。"""

    def test_identical_args(self):
        """同一引数はTrue。"""
        assert _args_similar({"name": "test"}, {"name": "test"}) is True

    def test_different_values(self):
        """異なる値はFalse。"""
        assert _args_similar({"name": "test1"}, {"name": "test2"}) is False

    def test_different_keys(self):
        """異なるキーはFalse。"""
        assert _args_similar({"name": "test"}, {"id": "test"}) is False

    def test_none_and_empty_string(self):
        """Noneと空文字列は等価。"""
        assert _args_similar({"name": None}, {"name": ""}) is True

    def test_none_and_empty_list(self):
        """Noneと空リストは等価。"""
        assert _args_similar({"items": None}, {"items": []}) is True

    def test_none_and_empty_dict(self):
        """Noneと空辞書は等価。"""
        assert _args_similar({"config": None}, {"config": {}}) is True

    def test_empty_args(self):
        """空の引数同士はTrue。"""
        assert _args_similar({}, {}) is True

    def test_mixed_empty_values(self):
        """異なる空値同士は等価。"""
        assert _args_similar({"a": ""}, {"a": None}) is True


class TestDetectRedundantCalls:
    """冗長呼び出し検出のテスト。"""

    def test_no_records(self):
        """空レコードの場合は0。"""
        assert detect_redundant_calls([]) == 0

    def test_single_record(self):
        """単一レコードの場合は0。"""
        records = [_make_record(1, "create")]
        assert detect_redundant_calls(records) == 0

    def test_different_tools(self):
        """異なるツールの連続呼び出しは冗長ではない。"""
        records = [
            _make_record(1, "create"),
            _make_record(2, "list"),
        ]
        assert detect_redundant_calls(records) == 0

    def test_same_tool_same_args(self):
        """同一ツール・同一引数の連続は冗長。"""
        records = [
            _make_record(1, "list", {"page": 1}),
            _make_record(2, "list", {"page": 1}),
        ]
        assert detect_redundant_calls(records) == 1

    def test_retry_after_error_not_redundant(self):
        """エラー後の再呼び出しは冗長ではない。"""
        records = [
            _make_record(1, "create", {"name": "test"}, is_error=True),
            _make_record(2, "create", {"name": "test"}),
        ]
        assert detect_redundant_calls(records) == 0

    def test_same_tool_different_args(self):
        """同一ツールでも異なる引数は冗長ではない。"""
        records = [
            _make_record(1, "create", {"name": "a"}),
            _make_record(2, "create", {"name": "b"}),
        ]
        assert detect_redundant_calls(records) == 0

    def test_multiple_redundant(self):
        """複数の冗長呼び出しを検出する。"""
        records = [
            _make_record(1, "list"),
            _make_record(2, "list"),
            _make_record(3, "list"),
        ]
        assert detect_redundant_calls(records) == 2

    def test_non_consecutive_same_tool(self):
        """非連続の同一ツール呼び出しは冗長ではない。"""
        records = [
            _make_record(1, "list"),
            _make_record(2, "create"),
            _make_record(3, "list"),
        ]
        assert detect_redundant_calls(records) == 0


class TestCountRecoverySteps:
    """リカバリステップ計測のテスト。"""

    def test_no_errors(self):
        """エラーなしの場合は0。"""
        records = [
            _make_record(1, "create"),
            _make_record(2, "list"),
        ]
        assert count_recovery_steps(records) == 0

    def test_error_then_different_tool_success(self):
        """エラー後に異なるツールで成功する場合はリカバリ1ステップ。"""
        records = [
            _make_record(1, "create", is_error=True),
            _make_record(2, "list"),
        ]
        assert count_recovery_steps(records) == 1

    def test_error_then_retry_then_different_tool(self):
        """エラー後に同一ツールリトライ→異なるツール成功で2ステップ。"""
        records = [
            _make_record(1, "create", is_error=True),
            _make_record(2, "create"),
            _make_record(3, "list"),
        ]
        # create(err) → create(ok, same tool) → list(diff tool, done)
        assert count_recovery_steps(records) == 2

    def test_error_then_same_tool_success(self):
        """エラー後に同一ツール成功はまだリカバリ中。"""
        records = [
            _make_record(1, "create", is_error=True),
            _make_record(2, "create"),
        ]
        # create(error) → create(success, same tool, still in recovery)
        assert count_recovery_steps(records) == 1

    def test_multiple_errors(self):
        """複数エラーのリカバリを正しく計測する。"""
        records = [
            _make_record(1, "create", is_error=True),
            _make_record(2, "list"),  # recovery done: 1 step
            _make_record(3, "update", is_error=True),
            _make_record(4, "update"),  # same tool, still recovering
            _make_record(5, "list"),  # different tool, recovery done: 2 steps
        ]
        assert count_recovery_steps(records) == 3

    def test_error_at_end(self):
        """末尾のエラーはリカバリステップ0。"""
        records = [
            _make_record(1, "create"),
            _make_record(2, "list", is_error=True),
        ]
        assert count_recovery_steps(records) == 0


class TestTraceEngine:
    """TraceEngineのテスト。"""

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage.save_session = AsyncMock()
        storage.save_record = AsyncMock()
        storage.save_summary = AsyncMock()
        storage.update_session_status = AsyncMock()
        storage.get_records = AsyncMock(return_value=[])
        return storage

    @pytest.fixture
    def engine(self, mock_storage):
        return TraceEngine(mock_storage)

    async def test_start_session(self, engine, mock_storage):
        """セッション開始でIDが返される。"""
        session_id = await engine.start_session("python -m server")
        assert isinstance(session_id, str)
        assert len(session_id) > 0
        mock_storage.save_session.assert_called_once()

    async def test_record_call(self, engine, mock_storage):
        """ツール呼び出しが記録される。"""
        session_id = await engine.start_session("python -m server")
        record = await engine.record_call(
            session_id=session_id,
            tool_name="create",
            arguments={"name": "test"},
            result={"id": "1"},
            is_error=False,
            duration_ms=100.0,
        )
        assert record.tool_name == "create"
        assert record.sequence == 1
        mock_storage.save_record.assert_called_once()

    async def test_record_call_invalid_session(self, engine):
        """存在しないセッションIDでエラー。"""
        with pytest.raises(TraceNotFoundError):
            await engine.record_call(
                session_id="nonexistent",
                tool_name="create",
                arguments={},
                result={},
                is_error=False,
                duration_ms=100.0,
            )

    async def test_stop_session(self, engine, mock_storage):
        """セッション終了でサマリーが返される。"""
        session_id = await engine.start_session("python -m server")
        summary = await engine.stop_session(session_id)
        assert summary.total_calls == 0
        mock_storage.update_session_status.assert_called_once()
        mock_storage.save_summary.assert_called_once()

    async def test_stop_session_invalid(self, engine):
        """存在しないセッションの停止でエラー。"""
        with pytest.raises(TraceNotFoundError):
            await engine.stop_session("nonexistent")

    async def test_calculate_summary_with_records(self, engine, mock_storage):
        """レコード付きのサマリー計算。"""
        session_id = await engine.start_session("python -m server")
        records = [
            _make_record(1, "create", {"name": "test"}),
            _make_record(2, "list"),
            _make_record(3, "list"),  # redundant
        ]
        mock_storage.get_records.return_value = records

        summary = await engine.stop_session(session_id)
        assert summary.total_calls == 3
        assert summary.unique_tools == 2
        assert summary.redundant_calls == 1
        assert summary.error_count == 0

    async def test_sequence_counter_increments(self, engine, mock_storage):
        """シーケンス番号がインクリメントされる。"""
        session_id = await engine.start_session("python -m server")
        r1 = await engine.record_call(session_id, "create", {}, {}, False, 10.0)
        r2 = await engine.record_call(session_id, "list", {}, {}, False, 20.0)
        assert r1.sequence == 1
        assert r2.sequence == 2
