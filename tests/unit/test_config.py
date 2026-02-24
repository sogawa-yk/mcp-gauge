"""GaugeConfigのユニットテスト。"""

import os
from unittest.mock import patch

from mcp_gauge.config import GaugeConfig


class TestGaugeConfig:
    """GaugeConfigのテスト。"""

    def test_create_valid(self):
        """正常なConfigを作成できること。"""
        config = GaugeConfig(
            db_path="/tmp/test.db",
            anthropic_api_key="test-key",
            anthropic_model="claude-sonnet-4-20250514",
            mcp_timeout_sec=30,
        )
        assert config.db_path == "/tmp/test.db"
        assert config.anthropic_api_key == "test-key"
        assert config.anthropic_model == "claude-sonnet-4-20250514"
        assert config.mcp_timeout_sec == 30

    def test_from_env_defaults(self):
        """環境変数未設定時のデフォルト値。"""
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in (
                "MCP_GAUGE_DB_PATH",
                "ANTHROPIC_API_KEY",
                "MCP_GAUGE_MODEL",
                "MCP_GAUGE_TIMEOUT",
            )
        }
        with patch.dict(os.environ, env, clear=True):
            config = GaugeConfig.from_env()
        assert config.db_path.endswith(".mcp-gauge/gauge.db")
        assert config.anthropic_api_key == ""
        assert config.anthropic_model == "claude-sonnet-4-20250514"
        assert config.mcp_timeout_sec == 30

    def test_from_env_custom(self):
        """環境変数からカスタム値を読み込む。"""
        env = {
            "MCP_GAUGE_DB_PATH": "/custom/path.db",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "MCP_GAUGE_MODEL": "claude-haiku-4-5-20251001",
            "MCP_GAUGE_TIMEOUT": "60",
        }
        with patch.dict(os.environ, env, clear=True):
            config = GaugeConfig.from_env()
        assert config.db_path == "/custom/path.db"
        assert config.anthropic_api_key == "sk-ant-test"
        assert config.anthropic_model == "claude-haiku-4-5-20251001"
        assert config.mcp_timeout_sec == 60
