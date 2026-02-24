"""Pydanticモデルのバリデーションテスト。"""

from mcp_gauge.models.lint import LintResult, Severity
from mcp_gauge.models.results import (
    ComparisonResult,
    CriteriaEvaluation,
    MetricComparison,
    Report,
    ScenarioResult,
    SuiteResult,
)
from mcp_gauge.models.scenario import (
    ScenarioDefinition,
    SuccessCriteria,
)
from mcp_gauge.models.trace import (
    SessionStatus,
    TraceRecord,
    TraceSession,
    TraceSummary,
)


class TestSessionStatus:
    """SessionStatusのテスト。"""

    def test_values(self):
        assert SessionStatus.RUNNING == "running"
        assert SessionStatus.COMPLETED == "completed"
        assert SessionStatus.FAILED == "failed"


class TestTraceRecord:
    """TraceRecordのテスト。"""

    def test_create_valid(self):
        record = TraceRecord(
            id="rec-001",
            session_id="sess-001",
            sequence=1,
            tool_name="create",
            arguments={"name": "test"},
            result={"id": "1"},
            is_error=False,
            duration_ms=100.0,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert record.tool_name == "create"
        assert record.is_error is False

    def test_error_record(self):
        record = TraceRecord(
            id="rec-002",
            session_id="sess-001",
            sequence=2,
            tool_name="create",
            arguments={"name": ""},
            result={"error": "invalid name"},
            is_error=True,
            duration_ms=50.0,
            timestamp="2026-01-01T00:00:01Z",
        )
        assert record.is_error is True


class TestTraceSummary:
    """TraceSummaryのテスト。"""

    def test_create_valid(self):
        summary = TraceSummary(
            total_calls=5,
            unique_tools=3,
            error_count=1,
            redundant_calls=1,
            total_duration_ms=500.0,
            recovery_steps=2,
            tool_call_sequence=[
                "create",
                "list",
                "create",
                "list",
                "delete",
            ],
        )
        assert summary.total_calls == 5
        assert summary.unique_tools == 3

    def test_empty_summary(self):
        summary = TraceSummary(
            total_calls=0,
            unique_tools=0,
            error_count=0,
            redundant_calls=0,
            total_duration_ms=0.0,
            recovery_steps=0,
            tool_call_sequence=[],
        )
        assert summary.total_calls == 0


class TestTraceSession:
    """TraceSessionのテスト。"""

    def test_create_running(self):
        session = TraceSession(
            id="sess-001",
            server_command="python -m server",
            server_args=["--port", "8080"],
            status=SessionStatus.RUNNING,
            started_at="2026-01-01T00:00:00Z",
        )
        assert session.status == SessionStatus.RUNNING
        assert session.finished_at is None
        assert session.task_success is None
        assert session.summary is None

    def test_defaults(self):
        session = TraceSession(
            id="sess-002",
            server_command="python -m server",
            server_args=[],
            started_at="2026-01-01T00:00:00Z",
        )
        assert session.scenario_id is None
        assert session.status == SessionStatus.RUNNING


class TestSeverity:
    """Severityのテスト。"""

    def test_values(self):
        assert Severity.ERROR == "error"
        assert Severity.WARNING == "warning"
        assert Severity.INFO == "info"


class TestLintResult:
    """LintResultのテスト。"""

    def test_create_valid(self):
        result = LintResult(
            tool_name="create",
            severity=Severity.WARNING,
            rule="ambiguous-description",
            message="曖昧な表現があります",
            suggestion="具体的に記述してください",
            field="description",
        )
        assert result.rule == "ambiguous-description"
        assert result.severity == Severity.WARNING


class TestSuccessCriteria:
    """SuccessCriteriaのテスト。"""

    def test_defaults(self):
        criteria = SuccessCriteria()
        assert criteria.max_steps is None
        assert criteria.required_tools is None
        assert criteria.forbidden_tools is None
        assert criteria.must_succeed is True

    def test_full_criteria(self):
        criteria = SuccessCriteria(
            max_steps=5,
            required_tools=["create", "list"],
            forbidden_tools=["delete"],
            must_succeed=True,
        )
        assert criteria.max_steps == 5
        assert len(criteria.required_tools) == 2


class TestScenarioDefinition:
    """ScenarioDefinitionのテスト。"""

    def test_create_valid(self):
        scenario = ScenarioDefinition(
            id="test-scenario",
            name="テストシナリオ",
            description="テスト用",
            task_instruction="リソースを作成して",
            success_criteria=SuccessCriteria(max_steps=5),
        )
        assert scenario.id == "test-scenario"
        assert scenario.setup is None

    def test_with_optional_fields(self):
        scenario = ScenarioDefinition(
            id="test-scenario",
            name="テストシナリオ",
            description="テスト用",
            task_instruction="リソースを作成して",
            success_criteria=SuccessCriteria(),
            setup=[{"command": "init"}],
            teardown=["cleanup"],
        )
        assert scenario.setup is not None
        assert scenario.teardown is not None


class TestCriteriaEvaluation:
    """CriteriaEvaluationのテスト。"""

    def test_all_none(self):
        eval_result = CriteriaEvaluation()
        assert eval_result.max_steps is None
        assert eval_result.required_tools is None

    def test_with_values(self):
        eval_result = CriteriaEvaluation(
            max_steps={"passed": True, "limit": 5, "actual": 3},
            required_tools={"passed": True, "missing": []},
            forbidden_tools={"passed": True, "violated": []},
            must_succeed={"passed": True},
        )
        assert eval_result.max_steps["passed"] is True


class TestScenarioResult:
    """ScenarioResultのテスト。"""

    def test_create_passed(self):
        result = ScenarioResult(
            scenario_id="test",
            trace_id="trace-001",
            passed=True,
            task_success=True,
            summary=TraceSummary(
                total_calls=2,
                unique_tools=2,
                error_count=0,
                redundant_calls=0,
                total_duration_ms=100.0,
                recovery_steps=0,
                tool_call_sequence=["create", "list"],
            ),
            criteria_evaluation=CriteriaEvaluation(),
        )
        assert result.passed is True


class TestSuiteResult:
    """SuiteResultのテスト。"""

    def test_create(self):
        result = SuiteResult(
            suite_path="suite.yaml",
            total=2,
            passed=1,
            failed=1,
            results=[],
        )
        assert result.total == 2
        assert result.failed == 1


class TestMetricComparison:
    """MetricComparisonのテスト。"""

    def test_numeric(self):
        m = MetricComparison(
            baseline=5.0,
            current=3.0,
            change=-2.0,
            verdict="improved",
        )
        assert m.change == -2.0

    def test_bool(self):
        m = MetricComparison(
            baseline=False,
            current=True,
            change=None,
            verdict="improved",
        )
        assert m.change is None


class TestComparisonResult:
    """ComparisonResultのテスト。"""

    def test_create(self):
        result = ComparisonResult(
            baseline_trace_id="base-001",
            current_trace_id="curr-001",
            overall_verdict="improved",
            metrics={},
        )
        assert result.overall_verdict == "improved"


class TestReport:
    """Reportのテスト。"""

    def test_create(self):
        report = Report(
            trace_ids=["t1", "t2"],
            generated_at="2026-01-01T00:00:00Z",
            sessions=[],
            aggregated_calls=3.5,
            aggregated_errors=0.5,
            aggregated_redundant=0.0,
            recommendations=["特に問題はありません"],
        )
        assert len(report.trace_ids) == 2
        assert report.aggregated_calls == 3.5
