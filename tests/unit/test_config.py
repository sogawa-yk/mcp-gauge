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
            mcp_timeout_sec=30,
            mcp_tool_timeout_sec=300,
        )
        assert config.db_path == "/tmp/test.db"
        assert config.mcp_timeout_sec == 30
        assert config.mcp_tool_timeout_sec == 300

    def test_from_env_defaults(self):
        """環境変数未設定時のデフォルト値。"""
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in (
                "MCP_GAUGE_DB_PATH",
                "MCP_GAUGE_TIMEOUT",
                "MCP_GAUGE_TOOL_TIMEOUT",
            )
        }
        with patch.dict(os.environ, env, clear=True):
            config = GaugeConfig.from_env()
        assert config.db_path.endswith(".mcp-gauge/gauge.db")
        assert config.mcp_timeout_sec == 30
        assert config.mcp_tool_timeout_sec == 300

    def test_from_env_custom(self):
        """環境変数からカスタム値を読み込む。"""
        env = {
            "MCP_GAUGE_DB_PATH": "/custom/path.db",
            "MCP_GAUGE_TIMEOUT": "60",
            "MCP_GAUGE_TOOL_TIMEOUT": "600",
        }
        with patch.dict(os.environ, env, clear=True):
            config = GaugeConfig.from_env()
        assert config.db_path == "/custom/path.db"
        assert config.mcp_timeout_sec == 60
        assert config.mcp_tool_timeout_sec == 600
