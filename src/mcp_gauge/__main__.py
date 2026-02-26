"""MCP Gaugeエントリーポイント。python -m mcp_gauge で起動。"""

import anyio

from mcp_gauge.config import GaugeConfig
from mcp_gauge.server import GaugeServer


async def main() -> None:
    """MCP Gaugeサーバーを起動する。"""
    config = GaugeConfig.from_env()
    server = GaugeServer(config)

    # DB初期化とクラッシュリカバリー
    await server.initialize()

    await server.mcp.run_stdio_async()


if __name__ == "__main__":
    anyio.run(main)
