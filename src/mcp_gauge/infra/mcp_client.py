"""テスト対象MCPサーバーへの接続。"""

import asyncio
import time
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

from mcp_gauge.exceptions import ServerConnectionError


class MCPClientWrapper:
    """テスト対象MCPサーバーへの接続ラッパー。"""

    def __init__(self, timeout_sec: int = 30) -> None:
        self.timeout_sec = timeout_sec
        self._session: ClientSession | None = None
        self._read_stream: Any = None
        self._write_stream: Any = None
        self._cm: Any = None

    async def connect(
        self,
        server_command: str,
        server_args: list[str] | None = None,
    ) -> list[Tool]:
        """対象サーバーに接続し、ツール一覧を返す。"""
        try:
            server_params = StdioServerParameters(
                command=server_command,
                args=server_args or [],
            )
            self._cm = stdio_client(server_params)
            self._read_stream, self._write_stream = await self._cm.__aenter__()
            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()
            await asyncio.wait_for(
                self._session.initialize(),
                timeout=self.timeout_sec,
            )
            result = await self._session.list_tools()
            return result.tools
        except TimeoutError as e:
            raise ServerConnectionError(server_command, cause=e) from e
        except Exception as e:
            raise ServerConnectionError(server_command, cause=e) from e

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], bool, float]:
        """ツールを呼び出し、(結果, is_error, duration_ms)を返す。"""
        if self._session is None:
            raise RuntimeError("Not connected")

        start = time.perf_counter()
        result = await self._session.call_tool(tool_name, arguments)
        duration_ms = (time.perf_counter() - start) * 1000

        is_error = result.isError or False
        content_parts = []
        for item in result.content:
            if hasattr(item, "text"):
                content_parts.append(item.text)
            else:
                content_parts.append(str(item))

        result_dict = {
            "content": content_parts,
            "is_error": is_error,
        }
        return result_dict, is_error, duration_ms

    async def close(self) -> None:
        """接続を閉じる。"""
        import contextlib

        if self._session is not None:
            with contextlib.suppress(Exception):
                await self._session.__aexit__(None, None, None)
            self._session = None
        if self._cm is not None:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(None, None, None)
            self._cm = None
