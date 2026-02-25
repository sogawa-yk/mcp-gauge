"""MCP Gaugeが公開するPrompt定義。

コーディングエージェントがMCPサーバー開発を自律的に実行するための
ワークフローガイドをMCPのPromptプリミティブとして提供する。
"""

import json as _json

from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
)

# ---------------------------------------------------------------------------
# Prompt メタデータ定義
# ---------------------------------------------------------------------------

PROMPTS: list[Prompt] = [
    Prompt(
        name="mcp-server-dev-workflow",
        description=(
            "MCPサーバーのテスト・品質改善を自律的に実行するための"
            "包括的ワークフロー。接続情報とタスク概要を渡すと、"
            "lint→動的テスト→評価→改善の反復サイクルを案内する。"
        ),
        arguments=[
            PromptArgument(
                name="server_command",
                description=(
                    "stdioトランスポートのサーバー起動コマンド。server_urlと排他。"
                ),
                required=False,
            ),
            PromptArgument(
                name="server_args",
                description="サーバー起動引数（カンマ区切り）",
                required=False,
            ),
            PromptArgument(
                name="server_url",
                description=(
                    "SSE/Streamable HTTPサーバーのURL。server_commandと排他。"
                ),
                required=False,
            ),
            PromptArgument(
                name="task_description",
                description="テスト対象サーバーの概要とテスト目的",
                required=True,
            ),
        ],
    ),
    Prompt(
        name="fix-quality-issues",
        description=(
            "gauge_lintで検出される全ルールと修正パターンのリファレンス。"
            "lint結果を受け取り、各issueの具体的な修正方法を案内する。"
        ),
        arguments=[
            PromptArgument(
                name="lint_json",
                description=(
                    "gauge_lintの実行結果JSON（省略時は全ルールのリファレンスを返す）"
                ),
                required=False,
            ),
        ],
    ),
    Prompt(
        name="regression-test",
        description=(
            "MCPサーバーの変更前後を比較するリグレッションテストの"
            "ワークフロー。ベースラインのtrace_idと接続情報を渡す。"
        ),
        arguments=[
            PromptArgument(
                name="baseline_trace_id",
                description="比較基準となる過去のtrace ID",
                required=True,
            ),
            PromptArgument(
                name="server_command",
                description="stdioトランスポートのサーバー起動コマンド",
                required=False,
            ),
            PromptArgument(
                name="server_args",
                description="サーバー起動引数（カンマ区切り）",
                required=False,
            ),
            PromptArgument(
                name="server_url",
                description="SSE/Streamable HTTPサーバーのURL",
                required=False,
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Prompt コンテンツ生成
# ---------------------------------------------------------------------------


def _build_connection_block(arguments: dict[str, str] | None) -> str:
    """接続パラメータの説明ブロックを生成する。"""
    args = arguments or {}
    server_command = args.get("server_command", "")
    server_args = args.get("server_args", "")
    server_url = args.get("server_url", "")

    if server_url:
        return (
            "## 接続情報\n\n"
            f"- **トランスポート**: Streamable HTTP\n"
            f"- **URL**: `{server_url}`\n\n"
            "接続パラメータ:\n"
            "```json\n"
            f'{{"server_url": "{server_url}"}}\n'
            "```"
        )
    elif server_command:
        lines = [
            "## 接続情報\n",
            "- **トランスポート**: stdio",
            f"- **コマンド**: `{server_command}`",
        ]
        params: dict[str, str | list[str]] = {
            "server_command": server_command,
        }
        if server_args:
            parsed_args = [a.strip() for a in server_args.split(",") if a.strip()]
            lines.append(f"- **引数**: `{server_args}`")
            params["server_args"] = parsed_args
        params_json = _json.dumps(params, ensure_ascii=False)
        lines.append(f"\n接続パラメータ:\n```json\n{params_json}\n```")
        return "\n".join(lines)
    else:
        return (
            "## 接続情報\n\n"
            "**注意**: 接続情報が未指定です。以下のいずれかを指定してください:\n"
            "- `server_command`: stdioトランスポートのサーバー起動コマンド\n"
            "- `server_url`: SSE/Streamable HTTPサーバーのURL"
        )


def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    """指定されたプロンプトのコンテンツを生成する。"""
    generators = {
        "mcp-server-dev-workflow": _generate_dev_workflow,
        "fix-quality-issues": _generate_fix_quality,
        "regression-test": _generate_regression_test,
    }
    generator = generators.get(name)
    if generator is None:
        raise ValueError(f"不明なプロンプト: {name}")
    return generator(arguments)


# ---------------------------------------------------------------------------
# mcp-server-dev-workflow
# ---------------------------------------------------------------------------


def _generate_dev_workflow(
    arguments: dict[str, str] | None,
) -> GetPromptResult:
    args = arguments or {}
    task_description = args.get("task_description", "（未指定）")
    connection_block = _build_connection_block(arguments)

    content = f"""\
あなたはMCPサーバーの品質を自律的にテスト・改善するコーディングエージェントです。
以下のワークフローに従って、対象MCPサーバーのテストと改善を実行してください。

## タスク

{task_description}

{connection_block}

---

## ワークフロー

以下の5つのPhaseを順に実行してください。各Phaseの完了後、次のPhaseに自動で進んでください。

### Phase 1: 静的品質チェック（Lint）

`gauge_lint` を実行して、ツール定義の品質問題を検出します。

検出されたissueをseverity順（ERROR → WARNING → INFO）に確認し、
対象MCPサーバーのソースコードを修正してください。

主なルールと修正方針:

| ルール | severity | 修正方針 |
|--------|----------|----------|
| `missing-param-description` | ERROR | 必須パラメータに用途・形式・有効値を記述 |
| `ambiguous-description` | WARNING | 「適切な」「必要に応じて」等を具体的な記述に置換 |
| `missing-default-value` | WARNING | オプショナルパラメータにデフォルト値を明記 |
| `missing-return-description` | WARNING | 「〜を返す」「〜を返却する」を説明に追記 |
| `description-too-short` | INFO | 20文字以上になるよう目的・使い方・制約を追記 |
| `description-too-long` | INFO | 500文字以下に要点を絞って簡潔化 |

**修正後、再度 `gauge_lint` を実行して issue が 0 件になったことを確認してください。**

### Phase 2: 動的テスト（Connect → Proxy Call → Disconnect）

#### Step 2.1: 接続

`gauge_connect` で対象サーバーに接続します。
返却される `session_id` と `tools` を記録してください。

#### Step 2.2: テストシナリオの実行

`gauge_proxy_call` で各ツールを呼び出します。以下のパターンを網羅してください:

1. **正常系**: 各ツールの基本的な動作確認（代表的な引数で呼び出し）
2. **連携テスト**: 複数ツールの組み合わせ（例: 作成→一覧→更新→削除）
3. **エッジケース**: 空文字、境界値、大きな入力
4. **エラー系**: 存在しないリソースの操作、型の不一致

各呼び出しの `result` と `metrics` を確認し、予期しないエラーがあれば原因を調査してください。

#### Step 2.3: 切断

`gauge_disconnect` でセッションを終了します。

- テストシナリオが全て成功した場合: `"task_success": true`
- エラーがあった場合: `"task_success": false`

返却されるサマリーで以下を確認:
- `error_count`: エラー回数（目標: 0）
- `redundant_calls`: 冗長な呼び出し回数（目標: 0）
- `recovery_steps`: エラー回復ステップ数

### Phase 3: 評価（Evaluate）

`gauge_evaluate` でトレースを評価します。

```json
{{
  "session_id": "<Phase 2のsession_id>",
  "success_criteria": {{
    "max_steps": <想定される最大ステップ数>,
    "required_tools": [<必ず呼ばれるべきツール名>],
    "forbidden_tools": [<呼ばれてはいけないツール名>],
    "must_succeed": true
  }},
  "task_success": true
}}
```

`passed: false` の場合、`criteria_evaluation` の各項目を確認し:
- `max_steps` 超過 → テストシナリオの効率化、またはサーバー側ツールの統合を検討
- `required_tools` 未使用 → テストシナリオにツール呼び出しを追加
- `forbidden_tools` 使用 → サーバーの実装を確認し、不要なツールを削除/非公開化
- `must_succeed` 失敗 → エラーの根本原因を修正

### Phase 4: レポート生成

`gauge_report` で全トレースの統合レポートを生成します。

```json
{{
  "trace_ids": ["<session_id_1>", "<session_id_2>", ...]
}}
```

`recommendations` に改善提案が含まれます。提案に従ってサーバーを改善してください。

### Phase 5: 反復改善

Phase 1〜4 の結果に基づいてサーバーのソースコードを改善し、
再度 Phase 1 から実行します。以下の目標を全て達成するまで繰り返してください:

- [ ] `gauge_lint` の issue が 0 件
- [ ] `gauge_evaluate` が `passed: true`
- [ ] `gauge_disconnect` の `error_count` が 0
- [ ] `gauge_disconnect` の `redundant_calls` が 0

改善前後の比較には `gauge_compare` を使用してください:

```json
{{
  "baseline_trace_id": "<改善前のsession_id>",
  "current_trace_id": "<改善後のsession_id>"
}}
```

`overall_verdict` が `improved` になるまで改善を続けてください。

---

## 重要な注意事項

- 各ツール呼び出しの結果は **必ず確認** してください。`"error"` キーが含まれる場合はエラーです。
- `gauge_connect` で取得した `session_id` は `gauge_disconnect` まで有効です。
- 1つのセッションで複数回 `gauge_proxy_call` を呼べます。
- テスト対象サーバーのソースコードを直接修正できる場合は、lint指摘やエラーに基づいて修正してください。
"""

    return GetPromptResult(
        description=(
            "MCPサーバーの品質テスト・改善を自律的に実行するための包括的ワークフロー"
        ),
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=content),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# fix-quality-issues
# ---------------------------------------------------------------------------


def _generate_fix_quality(
    arguments: dict[str, str] | None,
) -> GetPromptResult:
    args = arguments or {}
    lint_json = args.get("lint_json", "")

    context_block = ""
    if lint_json:
        context_block = f"""
## 検出されたissue

以下は `gauge_lint` の実行結果です。各issueに対して修正を実施してください。

```json
{lint_json}
```

---
"""

    content = f"""\
あなたはMCPサーバーのツール定義の品質を改善するコーディングエージェントです。
`gauge_lint` で検出されたissueを修正してください。
{context_block}
## Lintルール修正リファレンス

### 1. `missing-param-description` (ERROR)

**問題**: 必須パラメータに `description` フィールドがない。

**修正方法**: inputSchemaのpropertiesに `description` を追加する。

```python
# Before
"user_id": {{"type": "string"}}

# After
"user_id": {{
    "type": "string",
    "description": "操作対象のユーザーID（UUID v4形式）"
}}
```

**記述すべき内容**:
- パラメータの用途（何のために使うか）
- 期待される形式（UUID、ISO 8601日付、正規表現パターン等）
- 有効な値の範囲（最小値、最大値、許可される値のリスト）

---

### 2. `ambiguous-description` (WARNING)

**問題**: ツール説明に曖昧な表現が含まれている。

**検出される表現と修正例**:

| 検出表現 | 修正例 |
|----------|--------|
| 「適切な名前で〜」 | 「英数字とハイフンで構成される名前（1-64文字）で〜」 |
| 「必要に応じて〜」 | 「pageパラメータが指定された場合に〜」 |
| 「など」「etc.」「等」 | 具体的な選択肢を全て列挙: 「JSON, CSV, XMLの3形式」 |
| 「正しい形式で〜」 | 「ISO 8601形式（例: 2024-01-15T09:30:00Z）で〜」 |
| 「適当なサイズ」 | 「1KB〜10MBの範囲のサイズ」 |

---

### 3. `missing-default-value` (WARNING)

**問題**: オプショナルパラメータにデフォルト値の記載がない。

**修正方法（2つの選択肢）**:

```python
# 方法A: schemaのdefaultフィールドに設定
"page_size": {{
    "type": "integer",
    "description": "1ページあたりの件数",
    "default": 20
}}

# 方法B: descriptionにデフォルト値を明記
"page_size": {{
    "type": "integer",
    "description": "1ページあたりの件数。デフォルト: 20"
}}
```

---

### 4. `missing-return-description` (WARNING)

**問題**: ツール説明に戻り値の記述がない。

**修正方法**: descriptionに戻り値の説明を追加する。

```python
# Before
description="ユーザー情報を取得する"

# After
description="指定されたIDのユーザー情報を取得し、name, email, roleを含むJSONを返す"
```

**戻り値として記述すべき内容**:
- 返却されるデータのフォーマット（JSON、プレーンテキスト等）
- 主要なフィールド名とその型
- エラー時の返却形式

---

### 5. `description-too-short` / `description-too-long` (INFO)

**短すぎる場合（20文字未満）**: 以下を追記
- ツールの目的
- 主な入出力
- 使用場面や制約事項

**長すぎる場合（500文字超）**: 以下を実施
- 要点を箇条書きに整理
- 詳細な仕様は別のリソース（README等）に移動
- 冗長な表現を削除

---

## 修正手順

1. severity が **ERROR** のissueを最優先で修正
2. severity が **WARNING** のissueを修正
3. severity が **INFO** のissueを修正
4. `gauge_lint` を再実行して全issueが解消されたことを確認
"""

    return GetPromptResult(
        description="gauge_lint検出issue の修正ガイド",
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=content),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# regression-test
# ---------------------------------------------------------------------------


def _generate_regression_test(
    arguments: dict[str, str] | None,
) -> GetPromptResult:
    args = arguments or {}
    baseline_trace_id = args.get("baseline_trace_id", "")
    connection_block = _build_connection_block(arguments)

    if not baseline_trace_id:
        baseline_block = (
            "**注意**: `baseline_trace_id` が未指定です。"
            "過去のテスト実行で取得した session_id を指定してください。"
        )
    else:
        baseline_block = f"- **ベースライン trace ID**: `{baseline_trace_id}`"

    content = f"""\
あなたはMCPサーバーの変更前後の品質を比較検証するコーディングエージェントです。
以下のワークフローに従って、リグレッションテストを実行してください。

{connection_block}

{baseline_block}

---

## ワークフロー

### Step 1: ベースラインの確認

まず、ベースラインのトレースデータを確認します:

```json
gauge_report({{
  "trace_ids": ["{baseline_trace_id}"]
}})
```

レポートから以下を確認してください:
- 呼び出されたツールとその順序
- エラーの有無
- 合計呼び出し回数

### Step 2: 同一シナリオの再実行

ベースラインと**同じツール呼び出し順序・引数**で新しいセッションを実行します。

1. `gauge_connect` で接続
2. ベースラインと同じ順序で `gauge_proxy_call` を実行
3. `gauge_disconnect` で切断（`task_success` もベースラインに合わせる）

### Step 3: 比較

```json
gauge_compare({{
  "baseline_trace_id": "{baseline_trace_id}",
  "current_trace_id": "<Step 2のsession_id>"
}})
```

### Step 4: 結果の分析

`overall_verdict` を確認:

| verdict | 意味 | アクション |
|---------|------|-----------|
| `improved` | 改善された | 変更を採用 |
| `unchanged` | 変化なし | 変更の影響なし（安全） |
| `degraded` | 劣化した | 変更を見直し、原因を調査 |
| `mixed` | 一部改善・一部劣化 | 各メトリクスを個別に確認 |

各メトリクスの `verdict` を確認:
- `total_calls`: 呼び出し回数（少ないほど良い）
- `error_count`: エラー数（少ないほど良い）
- `redundant_calls`: 冗長呼び出し数（少ないほど良い）
- `total_duration_ms`: 合計処理時間（短いほど良い）
- `recovery_steps`: エラー回復ステップ数（少ないほど良い）
- `task_success`: タスク成功（true が良い）

### Step 5: 劣化時の対応

`degraded` のメトリクスがある場合:

1. 劣化したメトリクスの `baseline` と `current` の値を比較
2. 変更内容とメトリクス劣化の因果関係を分析
3. 必要に応じてサーバーのソースコードを修正
4. Step 2〜4 を再実行

**`overall_verdict` が `improved` または `unchanged` になるまで繰り返してください。**
"""

    return GetPromptResult(
        description="MCPサーバーのリグレッションテストワークフロー",
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=content),
            ),
        ],
    )
