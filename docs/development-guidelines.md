# 開発ガイドライン (Development Guidelines)

## コーディング規約

### 命名規則

#### 変数・関数

```python
# 変数: snake_case、名詞または名詞句
user_profile_data = fetch_user_profile()
trace_session_id = "550e8400-..."
is_completed = True

# 関数: snake_case、動詞で始める
def calculate_total_calls(records: list[TraceRecord]) -> int: ...
def detect_redundant_calls(records: list[TraceRecord]) -> int: ...
def validate_scenario(scenario: dict) -> ScenarioDefinition: ...

# Boolean: is_, has_, should_, can_ で始める
is_valid = True
has_permission = False
should_retry = True
```

#### クラス

```python
# クラス: PascalCase、名詞
class LintEngine: ...
class TraceStorage: ...
class ScenarioRunner: ...

# プライベートメソッド: _プレフィックス
class TraceEngine:
    async def start_session(self, ...) -> str: ...        # public
    def _calculate_summary(self, ...) -> TraceSummary: ... # private
    def _detect_redundant_calls(self, ...) -> int: ...     # private
```

#### 定数

```python
# UPPER_SNAKE_CASE
MAX_TRACE_RECORDS = 100_000
DEFAULT_DB_PATH = "~/.mcp-gauge/gauge.db"
AMBIGUOUS_PATTERNS = [
    (r"適切な", "具体的な値や形式を明記してください"),
    ...
]
```

### 型ヒント

**全ての公開関数に型ヒントを付与する**:

```python
# 良い例: 明示的な型ヒント
async def lint(
    self,
    server_command: str,
    server_args: list[str] | None = None,
) -> list[LintResult]:
    ...

# 悪い例: 型ヒントなし
async def lint(self, server_command, server_args=None):
    ...
```

**Pydanticモデルでデータ構造を定義**:

```python
from pydantic import BaseModel

class LintResult(BaseModel):
    tool_name: str
    severity: Severity
    rule: str
    message: str
    suggestion: str
    field: str
```

### コードフォーマット

- **フォーマッター**: ruff format
- **行の長さ**: 最大88文字（ruffデフォルト、pyproject.tomlの`[tool.ruff] line-length`で管理）
- **インデント**: 4スペース
- **クォート**: ダブルクォート（ruffデフォルト）

### コメント規約

**docstring（Google style）**:
```python
async def run_scenario(
    self,
    server_command: str,
    scenario: ScenarioDefinition,
    server_args: list[str] | None = None,
) -> ScenarioResult:
    """シナリオを実行し、結果を返す。

    テスト用LLMにタスク指示を与え、対象MCPサーバーのツールを使って
    自動実行する。実行結果はトレースデータとして記録される。

    Args:
        server_command: 対象MCPサーバーの起動コマンド。
        scenario: 実行するシナリオ定義。
        server_args: 対象MCPサーバーの起動引数。

    Returns:
        シナリオの実行結果（合否・トレースサマリー・詳細評価）。

    Raises:
        ConnectionError: 対象サーバーへの接続に失敗した場合。
        LLMAPIError: LLM APIの呼び出しに失敗した場合。
    """
```

**インラインコメント**:
```python
# 良い例: なぜそうするかを説明
# リトライは冗長呼び出しに含めない（意図的な再試行のため）
if prev.is_error:
    continue

# 悪い例: 何をしているか（コードを見れば分かる）
# iを1増やす
i += 1
```

### エラーハンドリング

**カスタム例外クラス**:
```python
class GaugeError(Exception):
    """MCP Gaugeの基底例外クラス。"""

class ConnectionError(GaugeError):
    """対象MCPサーバーへの接続失敗。"""
    def __init__(self, server_command: str, cause: Exception | None = None):
        self.server_command = server_command
        self.cause = cause
        super().__init__(
            f"対象サーバーへの接続に失敗しました: {server_command}"
        )

class InvalidScenarioError(GaugeError):
    """シナリオ定義が不正。"""
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"シナリオ定義エラー [{field}]: {message}")

class TraceNotFoundError(GaugeError):
    """指定されたトレースIDが存在しない。"""
    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        super().__init__(f"トレースが見つかりません: {trace_id}")
```

**エラーハンドリングの原則**:
- 予期されるエラー: カスタム例外で適切に処理
- 予期しないエラー: 上位に伝播
- エラーを無視しない
- エージェントが次のアクションを判断できるよう、エラーメッセージに`suggestion`を含める

```python
# MCPツールハンドラでのエラーハンドリング
async def gauge_lint(self, server_command: str, ...) -> dict:
    try:
        results = await self.lint_engine.lint(server_command, server_args)
        return {"total_tools": ..., "issues": ...}
    except ConnectionError as e:
        return {
            "error": "connection_failed",
            "message": str(e),
            "suggestion": "server_commandとserver_argsを確認してください",
        }
```

### 非同期処理

**async/awaitの使用**:
```python
# 良い例: async/await
async def start_session(self, server_command: str) -> str:
    session = TraceSession(id=str(uuid4()), ...)
    await self.storage.save_session(session)
    return session.id

# 並列実行が可能な場合はgatherを使用
async def run_suite(self, scenarios: list[ScenarioDefinition]) -> list[ScenarioResult]:
    tasks = [self.run_scenario(s) for s in scenarios]
    return await asyncio.gather(*tasks)
```

## Git運用ルール

### ブランチ戦略

> 現時点ではmainブランチのみで運用。チーム拡大時にdevelopブランチの導入を検討する。

**ブランチ種別**:
- `main`: 本番リリース可能な安定版
- `feature/[機能名]`: 新機能開発
- `fix/[修正内容]`: バグ修正
- `refactor/[対象]`: リファクタリング

**フロー**:
```
main
  ├─ feature/lint-engine
  ├─ feature/trace-engine
  └─ fix/redundant-detection
```

**マージ方針**:
- feature/fix/refactor → main: squash merge

### コミットメッセージ規約

**Conventional Commits**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**:
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: コードフォーマット
- `refactor`: リファクタリング
- `test`: テスト追加・修正
- `chore`: ビルド、依存関係等

**Scope（対象モジュール）**:
- `lint`: LintEngine、リンティングルール
- `trace`: TraceEngine、トレーシング
- `scenario`: ScenarioRunner
- `compare`: CompareEngine
- `server`: MCPサーバーレイヤー
- `models`: データモデル
- `infra`: インフラレイヤー（storage, mcp_client, llm_client）
- `ci`: CI/CD設定
- `docs`: ドキュメント

**例**:
```
feat(lint): 曖昧表現検出ルールを追加

ツールdescriptionに含まれる曖昧な表現を検出するルールを実装しました。

実装内容:
- AmbiguousDescriptionRuleクラスを追加
- 日本語/英語の曖昧パターン定義
- 各パターンに対する改善提案の生成

Closes #15
```

### プルリクエストプロセス

**作成前のチェック**:
- [ ] 全てのテストがパス（`uv run pytest`）
- [ ] Lintエラーがない（`uv run ruff check`）
- [ ] フォーマット済み（`uv run ruff format`）
- [ ] 型チェックがパス（`uv run mypy src/`）

**PRサイズ目安**:
- 変更ファイル数: 10ファイル以内
- 変更行数: 300行以内
- 大きくなる場合は分割する

## テスト戦略

### テストピラミッド

```
       /\
      /E2E\       10% (dogfooding)
     /------\
    / 統合   \     20%
   /----------\
  / ユニット   \   70%
 /--------------\
```

### テストの書き方（Given-When-Then）

```python
class TestLintEngine:
    """LintEngineのユニットテスト。"""

    async def test_detect_ambiguous_description(self):
        """曖昧な表現を含むdescriptionを検出する。"""
        # Given: 曖昧な表現を含むツール定義
        tools = [
            Tool(name="create", description="適切な値を指定して作成する", inputSchema={})
        ]
        engine = LintEngine()

        # When: リンティング実行
        results = engine._apply_rules(tools)

        # Then: 曖昧表現の警告が出る
        assert len(results) >= 1
        assert results[0].rule == "ambiguous-description"
        assert results[0].severity == Severity.WARNING

    async def test_no_issues_for_good_description(self):
        """適切なdescriptionでは警告が出ない。"""
        # Given: 良いdescription
        tools = [
            Tool(
                name="create_resource",
                description="指定された名前でリソースを作成する。名前は英数字とハイフン（a-z, 0-9, -）で1-64文字。",
                inputSchema={...}
            )
        ]
        engine = LintEngine()

        # When
        results = engine._apply_rules(tools)

        # Then
        ambiguous = [r for r in results if r.rule == "ambiguous-description"]
        assert len(ambiguous) == 0
```

### テスト命名規則

- パターン: `test_[対象]_[条件]_[期待結果]` または説明的なdocstring
- ファイル: `test_[対象モジュール].py`

```python
# 関数名で表現
def test_detect_redundant_calls_with_retry_excludes_retry(): ...
def test_detect_redundant_calls_with_same_args_counts_as_redundant(): ...

# docstringで表現
def test_redundant_detection():
    """エラー後の同一ツール再呼び出しはリトライとして冗長に含めない。"""
```

### モック・フィクスチャの使用

```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_storage():
    """テスト用のモックストレージ。"""
    storage = AsyncMock(spec=TraceStorage)
    storage.get_records.return_value = [
        TraceRecord(id="1", session_id="s1", sequence=1, tool_name="create", ...),
        TraceRecord(id="2", session_id="s1", sequence=2, tool_name="list", ...),
    ]
    return storage

@pytest.fixture
def trace_engine(mock_storage):
    """モックストレージを注入したTraceEngine。"""
    engine = TraceEngine.__new__(TraceEngine)
    engine.storage = mock_storage
    return engine
```

### カバレッジ目標

| レイヤー | カバレッジ目標 | 理由 |
|---------|-------------|------|
| engines/ | 90%以上 | ビジネスロジックの正確性が最重要 |
| models/ | 80%以上 | バリデーションロジックの網羅 |
| infra/ | 60%以上 | 外部依存のため統合テストで補完 |
| server.py | 50%以上 | MCPプロトコル層はE2Eテストで補完 |

## コードレビュー基準

### レビューポイント

**機能性**:
- [ ] PRDの要件を満たしているか
- [ ] エッジケースが考慮されているか
- [ ] エラーハンドリングが適切か

**可読性**:
- [ ] 命名が明確か
- [ ] docstringが適切か
- [ ] 複雑なロジックが説明されているか

**保守性**:
- [ ] レイヤー間の依存関係ルールに違反していないか
- [ ] 責務が明確に分離されているか

**エージェント向け設計**:
- [ ] 戻り値が構造化JSONとしてエージェントが解釈可能か
- [ ] エラーレスポンスにsuggestionが含まれているか

### レビューコメントの優先度

- `[必須]`: 修正必須（バグ、セキュリティ）
- `[推奨]`: 修正推奨（パフォーマンス、可読性）
- `[提案]`: 検討してほしい
- `[質問]`: 理解のための質問

## 開発環境セットアップ

### セットアップ方法（推奨: devcontainer）

VS Code または GitHub Codespaces で `.devcontainer/devcontainer.json` を開くと、必要なツールが自動でセットアップされます。

### 必要なツール（手動セットアップの場合）

| ツール | バージョン | インストール方法 |
|--------|-----------|-----------------|
| Python | 3.12+ | OS標準 or pyenv |
| uv | 最新 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### セットアップ手順

```bash
# 1. リポジトリのクローン
git clone <repository-url>
cd mcp-gauge

# 2. 依存関係のインストール
uv sync

# 3. 環境変数の設定（E2Eテスト用）
export ANTHROPIC_API_KEY="sk-ant-..."

# 4. テストの実行
uv run pytest

# 5. リンター/フォーマッターの実行
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# 6. 型チェック
uv run mypy src/
```

### 品質チェックの自動化

**GitHub Actions CI**:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run ruff check src/ tests/
      - run: uv run ruff format --check src/ tests/
      - run: uv run mypy src/
      - run: uv run pytest --cov=src/mcp_gauge
```

### テスト種別ごとの実行

```bash
# ユニットテストのみ（APIキー不要、日常的に実行）
uv run pytest tests/unit/

# 統合テストまで実行
uv run pytest tests/unit/ tests/integration/

# E2Eテスト（ANTHROPIC_API_KEY が必要）
ANTHROPIC_API_KEY="sk-ant-..." uv run pytest tests/e2e/

# 全テスト実行
uv run pytest
```
