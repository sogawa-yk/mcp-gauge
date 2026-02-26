"""E2Eテスト用フィクスチャ。"""

import asyncio
import re
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from mcp_gauge.config import GaugeConfig
from mcp_gauge.server import GaugeServer

# --- stdio mock server fixtures ---


@pytest.fixture
def mock_server_command() -> str:
    """モックMCPサーバーの起動コマンドを返す。"""
    return sys.executable


@pytest.fixture
def mock_server_args() -> list[str]:
    """モックMCPサーバーの起動引数を返す。"""
    mock_server_path = (
        Path(__file__).parent.parent / "fixtures" / "mock_server" / "server.py"
    )
    return [str(mock_server_path)]


# --- HTTP mock server fixture ---


async def _read_port_from_stderr(
    proc: asyncio.subprocess.Process,
) -> int:
    """uvicornのstderr出力からポート番号を読み取る。"""
    assert proc.stderr is not None
    while True:
        line_bytes = await proc.stderr.readline()
        if not line_bytes:
            raise RuntimeError("HTTPモックサーバーが予期せず終了しました")
        line = line_bytes.decode()
        # "Uvicorn running on http://127.0.0.1:XXXXX" から抽出
        match = re.search(r"Uvicorn running on http://[\d.]+:(\d+)", line)
        if match:
            return int(match.group(1))


@pytest.fixture
async def http_mock_server_url() -> AsyncGenerator[str, None]:
    """Streamable HTTP MCPモックサーバーを起動し、URLを返す。

    port=0で起動し、uvicornのstderr出力から実際のポートを取得する。
    テスト終了時にサブプロセスを停止する。
    """
    http_server_path = (
        Path(__file__).parent.parent / "fixtures" / "mock_server" / "http_server.py"
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(http_server_path),
        "0",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        port = await asyncio.wait_for(_read_port_from_stderr(proc), timeout=10.0)
        url = f"http://127.0.0.1:{port}/mcp"
        yield url
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()


# --- GaugeServer fixture ---


@pytest.fixture
async def gauge_server(tmp_path: Path) -> AsyncGenerator[GaugeServer, None]:
    """初期化済みのGaugeServerインスタンスを返す。"""
    db_path = str(tmp_path / "test_gauge.db")
    config = GaugeConfig(db_path=db_path, mcp_timeout_sec=30, mcp_tool_timeout_sec=300)
    server = GaugeServer(config)
    await server.initialize()
    try:
        yield server
    finally:
        await server.session_manager.close_all()
