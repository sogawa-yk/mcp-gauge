"""MCP Gaugeの設定管理。"""

import os
from pathlib import Path

from pydantic import BaseModel


class GaugeConfig(BaseModel):
    """MCP Gaugeの設定。"""

    db_path: str
    mcp_timeout_sec: int

    @classmethod
    def from_env(cls) -> "GaugeConfig":
        """環境変数から設定を読み込む。"""
        default_db_path = str(Path.home() / ".mcp-gauge" / "gauge.db")
        return cls(
            db_path=os.environ.get("MCP_GAUGE_DB_PATH", default_db_path),
            mcp_timeout_sec=int(os.environ.get("MCP_GAUGE_TIMEOUT", "30")),
        )
