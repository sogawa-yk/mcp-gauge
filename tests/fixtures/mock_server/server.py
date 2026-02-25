"""テスト用モックMCPサーバー。

E2Eテストで使用する。意図的にリンティング問題を含むツール定義を持つ。
`python -m tests.fixtures.mock_server.server` で起動可能。
"""

import json

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

_server = Server("mock-test-server")

# インメモリリソースストア
_resources: dict[str, dict[str, str]] = {}


@_server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[Tool]:
    """ツール一覧を返す。"""
    return [
        Tool(
            name="echo",
            description=(
                "入力メッセージをそのまま返す。"
                "テスト用のシンプルなエコーツール。"
                "messageパラメータの内容をそのまま返却する。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "エコーする文字列",
                    },
                },
                "required": ["message"],
            },
        ),
        Tool(
            name="create_resource",
            description=(
                "適切な名前でリソースを作成する。作成されたリソースのIDを返す。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "リソース名（英数字とハイフン）",
                    },
                    "type": {
                        "type": "string",
                    },
                },
                "required": ["name", "type"],
            },
        ),
        Tool(
            name="list_resources",
            description="リソース一覧",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                    },
                },
            },
        ),
        Tool(
            name="fail_always",
            description=(
                "常にエラーを返すツール。"
                "エラーハンドリングのテストに使用する。"
                "呼び出すと必ずエラーレスポンスを返却する。"
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="delete_resource",
            description=("指定されたIDのリソースを削除する。削除結果を返却する。"),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "削除対象のリソースID",
                    },
                },
                "required": ["id"],
            },
        ),
    ]


@_server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, object]) -> list[TextContent]:
    """ツールを呼び出す。"""
    if name == "echo":
        message = arguments.get("message", "")
        return [TextContent(type="text", text=str(message))]

    if name == "create_resource":
        res_name = str(arguments.get("name", ""))
        res_type = str(arguments.get("type", ""))
        res_id = f"res-{len(_resources) + 1}"
        _resources[res_id] = {"name": res_name, "type": res_type}
        return [
            TextContent(
                type="text",
                text=json.dumps({"id": res_id, "name": res_name}),
            )
        ]

    if name == "list_resources":
        return [
            TextContent(
                type="text",
                text=json.dumps({"resources": list(_resources.values())}),
            )
        ]

    if name == "fail_always":
        raise ValueError("意図的なエラー: このツールは常に失敗します")

    if name == "delete_resource":
        res_id = str(arguments.get("id", ""))
        deleted = _resources.pop(res_id, None)
        if deleted:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"deleted": True, "id": res_id}),
                )
            ]
        return [
            TextContent(
                type="text",
                text=json.dumps({"deleted": False, "id": res_id}),
            )
        ]

    raise ValueError(f"不明なツール: {name}")


async def main() -> None:
    """モックサーバーを起動する。"""
    async with stdio_server() as (read_stream, write_stream):
        await _server.run(
            read_stream,
            write_stream,
            _server.create_initialization_options(),
        )


if __name__ == "__main__":
    anyio.run(main)
