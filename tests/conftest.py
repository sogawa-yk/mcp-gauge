"""pytest共通設定とフィクスチャ。"""

import pytest

from mcp_gauge.models.trace import (
    SessionStatus,
    TraceRecord,
    TraceSession,
    TraceSummary,
)


@pytest.fixture
def sample_trace_session() -> TraceSession:
    """テスト用のTraceSession。"""
    return TraceSession(
        id="test-session-001",
        server_command="python -m test_server",
        server_args=["--port", "8080"],
        scenario_id=None,
        status=SessionStatus.RUNNING,
        started_at="2026-01-01T00:00:00Z",
        finished_at=None,
        task_success=None,
    )


@pytest.fixture
def sample_trace_records() -> list[TraceRecord]:
    """テスト用のTraceRecordリスト。"""
    return [
        TraceRecord(
            id="rec-001",
            session_id="test-session-001",
            sequence=1,
            tool_name="create_resource",
            arguments={"name": "test"},
            result={"id": "res-1"},
            is_error=False,
            duration_ms=100.0,
            timestamp="2026-01-01T00:00:01Z",
        ),
        TraceRecord(
            id="rec-002",
            session_id="test-session-001",
            sequence=2,
            tool_name="list_resources",
            arguments={},
            result={"resources": [{"id": "res-1"}]},
            is_error=False,
            duration_ms=50.0,
            timestamp="2026-01-01T00:00:02Z",
        ),
    ]


@pytest.fixture
def sample_trace_summary() -> TraceSummary:
    """テスト用のTraceSummary。"""
    return TraceSummary(
        total_calls=2,
        unique_tools=2,
        error_count=0,
        redundant_calls=0,
        total_duration_ms=150.0,
        recovery_steps=0,
        tool_call_sequence=["create_resource", "list_resources"],
    )
