"""テスト対象MCPサーバーへの接続。"""

import asyncio
import contextlib
import os
import time
from datetime import timedelta
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from mcp.types import Tool

from mcp_gauge.exceptions import (
    ConnectionLostError,
    ServerConnectionError,
    ToolCallTimeoutError,
)
from mcp_gauge.models.trace import ConnectionParams, TransportType


class MCPClientWrapper:
    """テスト対象MCPサーバーへの接続ラッパー。

    全トランスポート(stdio/SSE/streamable_http)を統一的に扱う。
    内部でバックグラウンドタスクを使い、トランスポートの
    コンテキストマネージャを正しく async with で管理する。
    """

    def __init__(
        self, timeout_sec: int = 30, tool_call_timeout_sec: int = 300
    ) -> None:
        self.timeout_sec = timeout_sec
        self.tool_call_timeout_sec = tool_call_timeout_sec
        self._session: ClientSession | None = None
        self._tools: list[Tool] = []
        self._error: BaseException | None = None
        self._ready = asyncio.Event()
        self._close_requested = asyncio.Event()
        self._bg_task: asyncio.Task[None] | None = None

    async def connect(self, params: ConnectionParams) -> list[Tool]:
        """対象サーバーに接続し、ツール一覧を返す。"""
        target = params.display_target()
        try:
            self._bg_task = asyncio.create_task(self._connection_lifecycle(params))

            # ready信号またはバックグラウンドタスク終了を待つ
            ready_waiter = asyncio.create_task(self._ready.wait())
            done, pending = await asyncio.wait(
                {self._bg_task, ready_waiter},
                timeout=self.timeout_sec,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # ready_waiterのみキャンセル（bg_taskは接続維持のため残す）
            if ready_waiter in pending:
                ready_waiter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ready_waiter

            if not done:
                # タイムアウト
                await self._force_close()
                raise ServerConnectionError(
                    target,
                    cause=TimeoutError(
                        f"{self.timeout_sec}秒以内に接続できませんでした"
                    ),
                )

            if self._error is not None:
                await self._force_close()
                raise ServerConnectionError(
                    target,
                    cause=self._error,  # type: ignore[arg-type]
                )

            return list(self._tools)
        except ServerConnectionError:
            raise
        except Exception as e:
            await self._force_close()
            raise ServerConnectionError(target, cause=e) from e

    async def _connection_lifecycle(self, params: ConnectionParams) -> None:
        """バックグラウンドタスク: トランスポート/セッションのライフサイクル管理。

        async with でコンテキストマネージャを正しくネストし、
        close_requested シグナルまで接続を維持する。
        """
        try:
            async with (
                self._open_transport(params) as (
                    read_stream,
                    write_stream,
                ),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                result = await session.list_tools()

                self._session = session
                self._tools = list(result.tools)
                self._ready.set()

                # close()が呼ばれるまで接続を維持
                await self._close_requested.wait()
        except Exception as e:
            self._error = e
            self._ready.set()  # connect()のブロックを解除

    def _open_transport(self, params: ConnectionParams) -> Any:
        """トランスポート種別に応じたコンテキストマネージャを返す。"""
        if params.transport_type == TransportType.STDIO:
            return self._make_stdio_cm(params)
        elif params.transport_type == TransportType.SSE:
            return self._make_sse_cm(params)
        elif params.transport_type == TransportType.STREAMABLE_HTTP:
            return self._make_streamable_http_cm(params)
        raise ValueError(f"未対応のトランスポート: {params.transport_type}")

    @staticmethod
    def _make_stdio_cm(
        params: ConnectionParams,
    ) -> "_StdioCM":
        """stdio用コンテキストマネージャを作成する。"""
        assert params.server_command is not None
        server_params = StdioServerParameters(
            command=params.server_command,
            args=params.server_args,
            env={**os.environ, **(params.env or {})},
        )
        return _StdioCM(server_params)

    @staticmethod
    def _make_sse_cm(
        params: ConnectionParams,
    ) -> "_SseCM":
        """SSE用コンテキストマネージャを作成する。"""
        assert params.server_url is not None
        return _SseCM(
            url=params.server_url,
            headers=params.headers if params.headers else None,
        )

    @staticmethod
    def _make_streamable_http_cm(
        params: ConnectionParams,
    ) -> "_StreamableHttpCM":
        """Streamable HTTP用コンテキストマネージャを作成する。"""
        assert params.server_url is not None
        return _StreamableHttpCM(
            url=params.server_url,
            headers=params.headers if params.headers else None,
        )

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], bool, float]:
        """ツールを呼び出し、(結果, is_error, duration_ms)を返す。"""
        if self._session is None:
            raise RuntimeError("Not connected")

        if self._bg_task is not None and self._bg_task.done():
            raise ConnectionLostError(tool_name)

        start = time.perf_counter()
        try:
            result = await self._session.call_tool(
                tool_name,
                arguments,
                read_timeout_seconds=timedelta(
                    seconds=self.tool_call_timeout_sec
                ),
            )
        except McpError as e:
            if e.error.code == 408:
                raise ToolCallTimeoutError(
                    tool_name, self.tool_call_timeout_sec
                ) from e
            raise
        duration_ms = (time.perf_counter() - start) * 1000

        is_error = result.isError or False
        content_parts = []
        for item in result.content:
            if hasattr(item, "text"):
                content_parts.append(item.text)
            else:
                content_parts.append(str(item))

        result_dict: dict[str, Any] = {
            "content": content_parts,
            "is_error": is_error,
        }
        return result_dict, is_error, duration_ms

    async def close(self) -> None:
        """接続を閉じる。"""
        self._close_requested.set()
        self._session = None
        if self._bg_task is not None and not self._bg_task.done():
            try:
                await asyncio.wait_for(self._bg_task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError, Exception):
                self._bg_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._bg_task
            self._bg_task = None

    async def _force_close(self) -> None:
        """強制クローズ（エラー時）。"""
        self._close_requested.set()
        self._session = None
        if self._bg_task is not None and not self._bg_task.done():
            self._bg_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._bg_task
            self._bg_task = None


class _StdioCM:
    """stdio トランスポートのコンテキストマネージャラッパー。"""

    def __init__(self, server_params: StdioServerParameters) -> None:
        self._server_params = server_params
        self._cm: Any = None

    async def __aenter__(self) -> tuple[Any, Any]:
        self._cm = stdio_client(self._server_params)
        read_stream, write_stream = await self._cm.__aenter__()
        return read_stream, write_stream

    async def __aexit__(self, *args: Any) -> None:
        if self._cm is not None:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(*args)


class _SseCM:
    """SSE トランスポートのコンテキストマネージャラッパー。"""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._url = url
        self._headers = headers
        self._cm: Any = None

    async def __aenter__(self) -> tuple[Any, Any]:
        self._cm = sse_client(
            url=self._url,
            headers=self._headers,
        )
        read_stream, write_stream = await self._cm.__aenter__()
        return read_stream, write_stream

    async def __aexit__(self, *args: Any) -> None:
        if self._cm is not None:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(*args)


class _StreamableHttpCM:
    """Streamable HTTP トランスポートのコンテキストマネージャラッパー。"""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._url = url
        self._headers = headers
        self._cm: Any = None
        self._http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> tuple[Any, Any]:
        http_client: httpx.AsyncClient | None = None
        if self._headers:
            http_client = httpx.AsyncClient(headers=self._headers)
            self._http_client = http_client
        self._cm = streamable_http_client(
            url=self._url,
            http_client=http_client,
        )
        streams = await self._cm.__aenter__()
        # streamable_http_client returns 3-tuple:
        # (read, write, get_session_id)
        return streams[0], streams[1]

    async def __aexit__(self, *args: Any) -> None:
        if self._cm is not None:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(*args)
        if self._http_client is not None:
            with contextlib.suppress(Exception):
                await self._http_client.aclose()
            self._http_client = None
