"""MCP Gaugeエントリーポイント。python -m mcp_gauge で起動。"""

import anyio
from mcp.server.stdio import stdio_server

from mcp_gauge.config import GaugeConfig
from mcp_gauge.server import GaugeServer


async def main() -> None:
    """MCP Gaugeサーバーを起動する。"""
    config = GaugeConfig.from_env()
    server = GaugeServer(config)

    # DB初期化とクラッシュリカバリー
    await server.initialize()

    async with stdio_server() as (read_stream, write_stream):
        await server.mcp.run(
            read_stream,
            write_stream,
            server.mcp.create_initialization_options(),
        )


if __name__ == "__main__":
    anyio.run(main)
