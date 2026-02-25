"""テスト対象MCPサーバーへの接続。"""

import asyncio
import time
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool

from mcp_gauge.exceptions import ServerConnectionError
from mcp_gauge.models.trace import ConnectionParams, TransportType


class MCPClientWrapper:
    """テスト対象MCPサーバーへの接続ラッパー。"""

    def __init__(self, timeout_sec: int = 30) -> None:
        self.timeout_sec = timeout_sec
        self._session: ClientSession | None = None
        self._read_stream: Any = None
        self._write_stream: Any = None
        self._cm: Any = None
        self._http_client: httpx.AsyncClient | None = None

    async def connect(self, params: ConnectionParams) -> list[Tool]:
        """対象サーバーに接続し、ツール一覧を返す。"""
        target = params.display_target()
        try:
            if params.transport_type == TransportType.STDIO:
                await self._connect_stdio(params)
            elif params.transport_type == TransportType.SSE:
                await self._connect_sse(params)
            elif params.transport_type == TransportType.STREAMABLE_HTTP:
                await self._connect_streamable_http(params)

            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()
            await asyncio.wait_for(
                self._session.initialize(),
                timeout=self.timeout_sec,
            )
            result = await self._session.list_tools()
            return result.tools
        except ServerConnectionError:
            raise
        except TimeoutError as e:
            raise ServerConnectionError(target, cause=e) from e
        except Exception as e:
            raise ServerConnectionError(target, cause=e) from e

    async def _connect_stdio(self, params: ConnectionParams) -> None:
        """stdio トランスポートで接続する。"""
        assert params.server_command is not None
        server_params = StdioServerParameters(
            command=params.server_command,
            args=params.server_args,
        )
        self._cm = stdio_client(server_params)
        self._read_stream, self._write_stream = await self._cm.__aenter__()

    async def _connect_sse(self, params: ConnectionParams) -> None:
        """SSE トランスポートで接続する。"""
        assert params.server_url is not None
        self._cm = sse_client(
            url=params.server_url,
            headers=params.headers if params.headers else None,
        )
        self._read_stream, self._write_stream = await self._cm.__aenter__()

    async def _connect_streamable_http(
        self, params: ConnectionParams
    ) -> None:
        """Streamable HTTP トランスポートで接続する。"""
        assert params.server_url is not None
        http_client: httpx.AsyncClient | None = None
        if params.headers:
            http_client = httpx.AsyncClient(
                headers=params.headers,
            )
            self._http_client = http_client
        self._cm = streamable_http_client(
            url=params.server_url,
            http_client=http_client,
        )
        streams = await self._cm.__aenter__()
        # streamable_http_client returns 3-tuple:
        # (read, write, get_session_id)
        self._read_stream = streams[0]
        self._write_stream = streams[1]

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
        if self._http_client is not None:
            with contextlib.suppress(Exception):
                await self._http_client.aclose()
            self._http_client = None
