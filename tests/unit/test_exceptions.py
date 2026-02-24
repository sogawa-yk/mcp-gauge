"""カスタム例外クラスのユニットテスト。"""

from mcp_gauge.exceptions import (
    GaugeError,
    InvalidScenarioError,
    LLMAPIError,
    ServerConnectionError,
    TraceNotFoundError,
)


class TestGaugeError:
    """基底例外のテスト。"""

    def test_is_exception(self):
        """Exceptionのサブクラスであること。"""
        assert issubclass(GaugeError, Exception)

    def test_create(self):
        """インスタンス化できること。"""
        err = GaugeError("test error")
        assert str(err) == "test error"


class TestServerConnectionError:
    """ServerConnectionErrorのテスト。"""

    def test_create_with_cause(self):
        """cause付きで作成できること。"""
        cause = TimeoutError("timeout")
        err = ServerConnectionError("python -m server", cause=cause)
        assert err.server_command == "python -m server"
        assert err.cause is cause
        assert "python -m server" in str(err)

    def test_create_without_cause(self):
        """causeなしで作成できること。"""
        err = ServerConnectionError("python -m server")
        assert err.cause is None

    def test_is_gauge_error(self):
        """GaugeErrorのサブクラスであること。"""
        err = ServerConnectionError("cmd")
        assert isinstance(err, GaugeError)


class TestInvalidScenarioError:
    """InvalidScenarioErrorのテスト。"""

    def test_create(self):
        """正しいメッセージで作成されること。"""
        err = InvalidScenarioError("suite_path", "ファイルが見つかりません")
        assert err.field == "suite_path"
        assert "suite_path" in str(err)
        assert "ファイルが見つかりません" in str(err)

    def test_is_gauge_error(self):
        """GaugeErrorのサブクラスであること。"""
        err = InvalidScenarioError("field", "msg")
        assert isinstance(err, GaugeError)


class TestTraceNotFoundError:
    """TraceNotFoundErrorのテスト。"""

    def test_create(self):
        """正しいメッセージで作成されること。"""
        err = TraceNotFoundError("trace-123")
        assert err.trace_id == "trace-123"
        assert "trace-123" in str(err)

    def test_is_gauge_error(self):
        """GaugeErrorのサブクラスであること。"""
        err = TraceNotFoundError("id")
        assert isinstance(err, GaugeError)


class TestLLMAPIError:
    """LLMAPIErrorのテスト。"""

    def test_create_with_cause(self):
        """cause付きで作成できること。"""
        cause = RuntimeError("api error")
        err = LLMAPIError("rate limit exceeded", cause=cause)
        assert err.cause is cause
        assert "rate limit exceeded" in str(err)

    def test_create_without_cause(self):
        """causeなしで作成できること。"""
        err = LLMAPIError("error message")
        assert err.cause is None

    def test_is_gauge_error(self):
        """GaugeErrorのサブクラスであること。"""
        err = LLMAPIError("msg")
        assert isinstance(err, GaugeError)
