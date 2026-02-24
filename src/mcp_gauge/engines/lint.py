"""ツール説明文リンティングエンジン。"""

import re
from abc import ABC, abstractmethod

from mcp.types import Tool

from mcp_gauge.infra.mcp_client import MCPClientWrapper
from mcp_gauge.models.lint import LintResult, Severity

# 曖昧表現の検出パターン
AMBIGUOUS_PATTERNS: list[tuple[str, str]] = [
    (r"適切な", "具体的な値や形式を明記してください"),
    (
        r"必要に応じて",
        "どのような条件で必要になるかを明記してください",
    ),
    (
        r"etc\.?|など$|等$",
        "省略せず具体的な選択肢を列挙してください",
    ),
    (
        r"正しい|正しく",
        "何が「正しい」のか基準を明記してください",
    ),
    (r"適当な", "具体的な値や形式を明記してください"),
    (
        r"any suitable",
        "具体的な条件を明記してください",
    ),
    (
        r"as needed",
        "どのような場合に必要かを明記してください",
    ),
    (
        r"if necessary",
        "どのような条件で必要かを明記してください",
    ),
]


class LintRule(ABC):
    """リンティングルールの基底クラス。"""

    @abstractmethod
    def check(self, tool: Tool) -> list[LintResult]:
        """ツールに対してルールを適用し、問題を返す。"""


class AmbiguousDescriptionRule(LintRule):
    """曖昧な表現を含むdescriptionを検出する。"""

    def check(self, tool: Tool) -> list[LintResult]:
        results: list[LintResult] = []
        description = tool.description or ""
        for pattern, suggestion in AMBIGUOUS_PATTERNS:
            match = re.search(pattern, description)
            if match:
                matched_text = match.group()
                results.append(
                    LintResult(
                        tool_name=tool.name,
                        severity=Severity.WARNING,
                        rule="ambiguous-description",
                        message=(
                            f"descriptionに曖昧な表現 '{matched_text}' が含まれています"
                        ),
                        suggestion=(
                            f"'{matched_text}' を具体的な"
                            f"記述に置き換えてください。"
                            f"{suggestion}"
                        ),
                        field="description",
                    )
                )
        return results


class MissingParameterDescriptionRule(LintRule):
    """必須パラメータにdescriptionがないことを検出する。"""

    def check(self, tool: Tool) -> list[LintResult]:
        results: list[LintResult] = []
        schema = tool.inputSchema or {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for param_name in required:
            param_schema = properties.get(param_name, {})
            if not param_schema.get("description"):
                results.append(
                    LintResult(
                        tool_name=tool.name,
                        severity=Severity.ERROR,
                        rule="missing-param-description",
                        message=(
                            f"必須パラメータ '{param_name}' にdescriptionがありません"
                        ),
                        suggestion=(
                            "パラメータの用途、期待される形式、"
                            "有効な値の範囲を記述してください"
                        ),
                        field=f"parameters.{param_name}",
                    )
                )
        return results


class MissingDefaultValueRule(LintRule):
    """任意パラメータのデフォルト値が説明に記載されていないことを検出する。"""

    def check(self, tool: Tool) -> list[LintResult]:
        results: list[LintResult] = []
        schema = tool.inputSchema or {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        for param_name, param_schema in properties.items():
            if param_name in required:
                continue
            description = param_schema.get("description", "")
            has_default_info = (
                "default" in param_schema
                or "デフォルト" in description.lower()
                or "default" in description.lower()
            )
            if not has_default_info:
                results.append(
                    LintResult(
                        tool_name=tool.name,
                        severity=Severity.WARNING,
                        rule="missing-default-value",
                        message=(
                            f"任意パラメータ '{param_name}' の"
                            f"デフォルト値が記載されていません"
                        ),
                        suggestion=(
                            "descriptionにデフォルト値を明記するか、"
                            "schemaのdefaultフィールドを設定してください"
                        ),
                        field=f"parameters.{param_name}",
                    )
                )
        return results


class MissingReturnDescriptionRule(LintRule):
    """戻り値の構造がdescriptionに記載されていないことを検出する。"""

    _RETURN_KEYWORDS = [
        "返す",
        "返却",
        "return",
        "returns",
        "戻り値",
        "レスポンス",
        "response",
        "出力",
        "output",
    ]

    def check(self, tool: Tool) -> list[LintResult]:
        description = (tool.description or "").lower()
        has_return_info = any(kw in description for kw in self._RETURN_KEYWORDS)
        if not has_return_info and description:
            return [
                LintResult(
                    tool_name=tool.name,
                    severity=Severity.WARNING,
                    rule="missing-return-description",
                    message=("descriptionに戻り値の構造が記載されていません"),
                    suggestion=(
                        "戻り値のフォーマットや含まれる"
                        "フィールドをdescriptionに記述してください"
                    ),
                    field="description",
                )
            ]
        return []


class DescriptionLengthRule(LintRule):
    """descriptionの長さをチェックする。"""

    MIN_LENGTH = 20
    MAX_LENGTH = 500

    def check(self, tool: Tool) -> list[LintResult]:
        results: list[LintResult] = []
        description = tool.description or ""

        if 0 < len(description) < self.MIN_LENGTH:
            results.append(
                LintResult(
                    tool_name=tool.name,
                    severity=Severity.INFO,
                    rule="description-too-short",
                    message=(
                        f"descriptionが{len(description)}文字です"
                        f"（推奨: {self.MIN_LENGTH}文字以上）"
                    ),
                    suggestion=("ツールの目的、使い方、制約事項を追記してください"),
                    field="description",
                )
            )
        elif len(description) > self.MAX_LENGTH:
            results.append(
                LintResult(
                    tool_name=tool.name,
                    severity=Severity.INFO,
                    rule="description-too-long",
                    message=(
                        f"descriptionが{len(description)}文字です"
                        f"（推奨: {self.MAX_LENGTH}文字以下）"
                    ),
                    suggestion=("要点を絞って簡潔にまとめてください"),
                    field="description",
                )
            )
        return results


class LintEngine:
    """ツール説明文リンティングエンジン。"""

    def __init__(self) -> None:
        self.rules: list[LintRule] = [
            AmbiguousDescriptionRule(),
            MissingParameterDescriptionRule(),
            MissingDefaultValueRule(),
            MissingReturnDescriptionRule(),
            DescriptionLengthRule(),
        ]

    async def lint(
        self,
        server_command: str,
        server_args: list[str] | None = None,
        timeout_sec: int = 30,
    ) -> tuple[list[LintResult], int]:
        """対象サーバーのツールをリンティングする。

        Returns:
            (リント結果リスト, 接続されたツール総数)のタプル。
        """
        client = MCPClientWrapper(timeout_sec=timeout_sec)
        try:
            tools = await client.connect(server_command, server_args)
            return self._apply_rules(tools), len(tools)
        finally:
            await client.close()

    def _apply_rules(self, tools: list[Tool]) -> list[LintResult]:
        """全ツールに対して全ルールを適用する。"""
        results: list[LintResult] = []
        for tool in tools:
            for rule in self.rules:
                results.extend(rule.check(tool))
        return results
