"""テスト用Streamable HTTP MCPサーバー。

E2Eテストで使用するHTTPベースのモックサーバー。
`python tests/fixtures/mock_server/http_server.py` で起動。
"""

import json
import sys

from mcp.server.fastmcp import FastMCP

_resources: dict[str, dict[str, str]] = {}

_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
_mcp = FastMCP("mock-http-server", host="127.0.0.1", port=_port)


@_mcp.tool()
def echo(message: str) -> str:
    """入力メッセージをそのまま返す。テスト用エコーツール。messageパラメータの内容をそのまま返却する。"""
    return message


@_mcp.tool()
def create_resource(name: str, resource_type: str) -> str:
    """指定された名前でリソースを作成し、作成結果をJSON形式で返却する。"""
    res_id = f"res-{len(_resources) + 1}"
    _resources[res_id] = {"name": name, "type": resource_type}
    return json.dumps({"id": res_id, "name": name})


@_mcp.tool()
def list_resources() -> str:
    """全リソースの一覧をJSON形式で返却する。"""
    return json.dumps({"resources": list(_resources.values())})


if __name__ == "__main__":
    _mcp.run(transport="streamable-http")
