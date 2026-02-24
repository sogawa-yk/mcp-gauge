"""LintEngineのユニットテスト。"""

from mcp.types import Tool

from mcp_gauge.engines.lint import (
    AmbiguousDescriptionRule,
    DescriptionLengthRule,
    LintEngine,
    MissingDefaultValueRule,
    MissingParameterDescriptionRule,
    MissingReturnDescriptionRule,
)
from mcp_gauge.models.lint import Severity


def _make_tool(
    name: str = "test_tool",
    description: str = "",
    input_schema: dict | None = None,
) -> Tool:
    """テスト用のToolオブジェクトを作成する。"""
    return Tool(
        name=name,
        description=description,
        inputSchema=input_schema or {"type": "object", "properties": {}},
    )


class TestAmbiguousDescriptionRule:
    """曖昧表現検出ルールのテスト。"""

    def test_detect_japanese_ambiguous(self):
        """日本語の曖昧表現を検出する。"""
        rule = AmbiguousDescriptionRule()
        tool = _make_tool(description="適切な値を指定してリソースを作成する")
        results = rule.check(tool)
        assert len(results) >= 1
        assert results[0].rule == "ambiguous-description"
        assert results[0].severity == Severity.WARNING

    def test_detect_english_ambiguous(self):
        """英語の曖昧表現を検出する。"""
        rule = AmbiguousDescriptionRule()
        tool = _make_tool(description="Set any suitable value for the resource")
        results = rule.check(tool)
        assert len(results) >= 1
        assert results[0].rule == "ambiguous-description"

    def test_detect_etc(self):
        """「etc.」「など」の省略表現を検出する。"""
        rule = AmbiguousDescriptionRule()
        tool = _make_tool(description="リソース名、ID、タグなど")
        results = rule.check(tool)
        assert len(results) >= 1

    def test_no_issue_for_good_description(self):
        """良いdescriptionでは警告が出ない。"""
        rule = AmbiguousDescriptionRule()
        tool = _make_tool(
            description=(
                "指定された名前でリソースを作成する。"
                "名前は英数字とハイフン（a-z, 0-9, -）で1-64文字。"
                "作成されたリソースのIDを返す。"
            )
        )
        results = rule.check(tool)
        assert len(results) == 0

    def test_multiple_patterns(self):
        """複数の曖昧表現を含む場合に複数の結果を返す。"""
        rule = AmbiguousDescriptionRule()
        tool = _make_tool(description="適切な値を必要に応じて設定する")
        results = rule.check(tool)
        assert len(results) >= 2


class TestMissingParameterDescriptionRule:
    """パラメータ説明不足検出ルールのテスト。"""

    def test_detect_missing_description(self):
        """必須パラメータにdescriptionがない場合を検出する。"""
        rule = MissingParameterDescriptionRule()
        tool = _make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            }
        )
        results = rule.check(tool)
        assert len(results) == 1
        assert results[0].rule == "missing-param-description"
        assert results[0].severity == Severity.ERROR

    def test_no_issue_with_description(self):
        """descriptionがある場合は警告なし。"""
        rule = MissingParameterDescriptionRule()
        tool = _make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "リソースの名前",
                    },
                },
                "required": ["name"],
            }
        )
        results = rule.check(tool)
        assert len(results) == 0

    def test_optional_param_not_checked(self):
        """任意パラメータはチェックしない。"""
        rule = MissingParameterDescriptionRule()
        tool = _make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "tag": {"type": "string"},
                },
                "required": [],
            }
        )
        results = rule.check(tool)
        assert len(results) == 0


class TestMissingDefaultValueRule:
    """デフォルト値未記載検出ルールのテスト。"""

    def test_detect_missing_default(self):
        """任意パラメータにデフォルト値がない場合を検出する。"""
        rule = MissingDefaultValueRule()
        tool = _make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                },
                "required": [],
            }
        )
        results = rule.check(tool)
        assert len(results) == 1
        assert results[0].rule == "missing-default-value"
        assert results[0].severity == Severity.WARNING

    def test_no_issue_with_default_in_schema(self):
        """schemaにdefaultがある場合は警告なし。"""
        rule = MissingDefaultValueRule()
        tool = _make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 10,
                    },
                },
                "required": [],
            }
        )
        results = rule.check(tool)
        assert len(results) == 0

    def test_no_issue_with_default_in_description(self):
        """descriptionにデフォルト値が記載されている場合は警告なし。"""
        rule = MissingDefaultValueRule()
        tool = _make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "件数上限。デフォルト: 10",
                    },
                },
                "required": [],
            }
        )
        results = rule.check(tool)
        assert len(results) == 0

    def test_required_param_not_checked(self):
        """必須パラメータはチェックしない。"""
        rule = MissingDefaultValueRule()
        tool = _make_tool(
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            }
        )
        results = rule.check(tool)
        assert len(results) == 0


class TestMissingReturnDescriptionRule:
    """戻り値説明未記載検出ルールのテスト。"""

    def test_detect_missing_return(self):
        """戻り値の説明がない場合を検出する。"""
        rule = MissingReturnDescriptionRule()
        tool = _make_tool(description="リソースを作成する")
        results = rule.check(tool)
        assert len(results) == 1
        assert results[0].rule == "missing-return-description"

    def test_no_issue_with_return_description(self):
        """戻り値の説明がある場合は警告なし。"""
        rule = MissingReturnDescriptionRule()
        tool = _make_tool(
            description=("リソースを作成し、作成されたリソースのIDを返す")
        )
        results = rule.check(tool)
        assert len(results) == 0

    def test_no_issue_with_english_returns(self):
        """英語のreturn説明がある場合は警告なし。"""
        rule = MissingReturnDescriptionRule()
        tool = _make_tool(description="Create a resource. Returns the resource ID.")
        results = rule.check(tool)
        assert len(results) == 0

    def test_no_issue_for_empty_description(self):
        """空のdescriptionでは出さない（他のルールで検出）。"""
        rule = MissingReturnDescriptionRule()
        tool = _make_tool(description="")
        results = rule.check(tool)
        assert len(results) == 0


class TestDescriptionLengthRule:
    """description長さチェックルールのテスト。"""

    def test_too_short(self):
        """短すぎるdescriptionを検出する。"""
        rule = DescriptionLengthRule()
        tool = _make_tool(description="作成する")
        results = rule.check(tool)
        assert len(results) == 1
        assert results[0].rule == "description-too-short"
        assert results[0].severity == Severity.INFO

    def test_too_long(self):
        """長すぎるdescriptionを検出する。"""
        rule = DescriptionLengthRule()
        tool = _make_tool(description="a" * 501)
        results = rule.check(tool)
        assert len(results) == 1
        assert results[0].rule == "description-too-long"

    def test_good_length(self):
        """適切な長さのdescriptionは警告なし。"""
        rule = DescriptionLengthRule()
        tool = _make_tool(
            description=(
                "指定された名前でリソースを作成し、作成されたリソースのIDを返す"
            )
        )
        results = rule.check(tool)
        assert len(results) == 0

    def test_empty_description(self):
        """空のdescriptionはスキップ。"""
        rule = DescriptionLengthRule()
        tool = _make_tool(description="")
        results = rule.check(tool)
        assert len(results) == 0


class TestLintEngineApplyRules:
    """LintEngine._apply_rulesのテスト。"""

    def test_apply_all_rules(self):
        """全ルールが適用される。"""
        engine = LintEngine()
        tools = [
            _make_tool(
                name="bad_tool",
                description="適切な値を設定",
                input_schema={
                    "type": "object",
                    "properties": {
                        "config": {"type": "object"},
                    },
                    "required": ["config"],
                },
            )
        ]
        results = engine._apply_rules(tools)
        rules_found = {r.rule for r in results}
        assert "ambiguous-description" in rules_found
        assert "missing-param-description" in rules_found

    def test_no_issues_for_good_tools(self):
        """良いツールには警告なし。"""
        engine = LintEngine()
        tools = [
            _make_tool(
                name="good_tool",
                description=(
                    "指定された名前でリソースを作成し、"
                    "作成されたリソースのIDをJSON形式で返す。"
                    "名前は英数字で1-64文字。"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "リソース名（英数字1-64文字）",
                        },
                        "tag": {
                            "type": "string",
                            "description": "タグ。デフォルト: なし",
                        },
                    },
                    "required": ["name"],
                },
            )
        ]
        results = engine._apply_rules(tools)
        # warning/error レベルの問題がないこと
        serious = [
            r for r in results if r.severity in (Severity.ERROR, Severity.WARNING)
        ]
        assert len(serious) == 0

    def test_multiple_tools(self):
        """複数ツールに対してルールが適用される。"""
        engine = LintEngine()
        tools = [
            _make_tool(name="tool1", description="短い"),
            _make_tool(name="tool2", description="これも短い"),
        ]
        results = engine._apply_rules(tools)
        tool_names = {r.tool_name for r in results}
        assert "tool1" in tool_names
        assert "tool2" in tool_names
