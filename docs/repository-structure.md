# リポジトリ構造定義書 (Repository Structure Document)

> **注意**: 以下は目標とするリポジトリ構造（To-Be）です。実装の進捗に応じて随時更新してください。

## プロジェクト構造

```
mcp-gauge/
├── src/
│   └── mcp_gauge/             # メインパッケージ
│       ├── __init__.py
│       ├── __main__.py        # エントリーポイント（python -m mcp_gauge）
│       ├── server.py          # MCPサーバーレイヤー
│       ├── config.py          # 設定管理
│       ├── exceptions.py      # カスタム例外クラス
│       ├── engines/           # エンジンレイヤー（ビジネスロジック）
│       │   ├── __init__.py
│       │   ├── lint.py
│       │   ├── trace.py
│       │   ├── session.py
│       │   ├── evaluate.py
│       │   ├── compare.py
│       │   └── report.py
│       ├── infra/             # インフラレイヤー（外部接続・永続化）
│       │   ├── __init__.py
│       │   ├── mcp_client.py
│       │   └── storage.py
│       └── models/            # データモデル（Pydantic）
│           ├── __init__.py
│           ├── trace.py
│           ├── lint.py
│           ├── scenario.py
│           └── results.py
├── tests/                     # テストコード
│   ├── unit/                  # ユニットテスト
│   │   ├── engines/
│   │   │   ├── test_lint.py
│   │   │   ├── test_trace.py
│   │   │   ├── test_session.py
│   │   │   ├── test_evaluate.py
│   │   │   ├── test_compare.py
│   │   │   └── test_report.py
│   │   ├── infra/
│   │   │   └── test_storage.py
│   │   ├── models/
│   │   │   └── test_models.py
│   │   ├── test_config.py
│   │   └── test_exceptions.py
│   ├── integration/           # 統合テスト
│   │   ├── test_server.py
│   │   └── test_storage.py
│   ├── e2e/                   # E2Eテスト
│   │   └── test_dogfooding.py
│   ├── fixtures/              # テスト用フィクスチャ
│   │   ├── mock_server/       # テスト用モックMCPサーバー
│   │   │   └── server.py
│   │   └── scenarios/         # テスト用シナリオ
│   │       └── sample.yaml
│   └── conftest.py            # pytest共通設定
├── docs/                      # プロジェクトドキュメント
│   ├── ideas/                 # アイデア・調査メモ
│   │   └── initial-requirements.md
│   ├── product-requirements.md
│   ├── functional-design.md
│   ├── architecture.md
│   ├── repository-structure.md
│   ├── development-guidelines.md
│   └── glossary.md
├── .steering/                 # 作業単位のドキュメント
├── .claude/                   # Claude Code設定
│   ├── commands/
│   ├── skills/
│   └── agents/
├── pyproject.toml             # プロジェクト定義・依存関係
├── uv.lock                    # 依存関係ロックファイル
├── CLAUDE.md                  # Claude Code指示書
├── README.md                  # プロジェクト概要
├── LICENSE                    # ライセンス
└── .gitignore                 # Git除外設定
```

## ディレクトリ詳細

### src/mcp_gauge/ (メインパッケージ)

#### server.py

**役割**: MCPサーバーレイヤー。MCPプロトコルでツールを公開し、リクエストをエンジンレイヤーに委譲する

**配置内容**:
- `GaugeServer`クラス: MCPサーバーの起動・ツール登録
- 各ツールのハンドラ関数: `gauge_lint`, `gauge_connect`, `gauge_proxy_call`, `gauge_disconnect`, `gauge_evaluate`等

**依存関係**:
- 依存可能: `engines/`, `models/`, `config.py`
- 依存禁止: `infra/`（エンジンレイヤー経由でアクセス）

#### __main__.py

**役割**: コマンドラインエントリーポイント。`python -m mcp_gauge`で起動

**配置内容**:
- 起動処理、設定の読み込み、GaugeServerの初期化と実行

#### config.py

**役割**: 設定の管理。環境変数からの読み取り

**配置内容**:
- `GaugeConfig`クラス: DBパス、タイムアウト等の設定値

### src/mcp_gauge/engines/ (エンジンレイヤー)

**役割**: 各機能のビジネスロジックを実装する

**配置ファイル**:
- `lint.py`: LintEngine + 各LintRuleクラス
- `trace.py`: TraceEngine（トレースの記録・集計）
- `session.py`: SessionManager（プロキシセッション管理）
- `evaluate.py`: EvaluateEngine（成功条件評価）
- `compare.py`: CompareEngine（ベースライン比較）
- `report.py`: ReportGenerator（統合レポート生成）

**命名規則**:
- ファイル名: snake_case（`lint.py`, `trace.py`）
- クラス名: PascalCase（`LintEngine`, `TraceEngine`）
- 1ファイルに1つのメインクラス + 関連クラス（例: `lint.py`に`LintEngine` + `LintRule`サブクラス群）

**依存関係**:
- 依存可能: `infra/`, `models/`
- 依存禁止: `server.py`

### src/mcp_gauge/infra/ (インフラレイヤー)

**役割**: 外部サービスへの接続・データ永続化

**配置ファイル**:
- `mcp_client.py`: テスト対象MCPサーバーへの接続（MCPクライアント実装）
- `storage.py`: TraceStorage（SQLiteへの読み書き）

**命名規則**:
- ファイル名: snake_case
- クラス名: PascalCase（`MCPClientWrapper`, `TraceStorage`）

**依存関係**:
- 依存可能: `models/`
- 依存禁止: `server.py`, `engines/`

### src/mcp_gauge/models/ (データモデル)

**役割**: Pydanticモデルによるデータ構造定義。全レイヤーから参照される共通の型定義

**配置ファイル**:
- `trace.py`: TraceSession, TraceRecord, TraceSummary
- `lint.py`: LintResult, Severity
- `scenario.py`: ScenarioDefinition, SuccessCriteria
- `results.py`: ScenarioResult, CriteriaEvaluation, SuiteResult, ComparisonResult, MetricComparison, Report

**命名規則**:
- ファイル名: snake_case（ドメイン概念ごとに分割）
- クラス名: PascalCase

**依存関係**:
- 依存可能: なし（他モジュールに依存しない純粋なデータ定義）
- 依存禁止: `server.py`, `engines/`, `infra/`

### tests/ (テストディレクトリ)

#### unit/

**役割**: エンジンレイヤーとモデルのユニットテスト

**スコープ**: `engines/` と `models/` のみ対象。インフラレイヤー（`infra/`）は統合テスト（`integration/`）でカバーする。

**構造**: `src/mcp_gauge/`のディレクトリ構造をミラーする

```
tests/unit/
├── engines/
│   ├── test_lint.py           # LintEngine + 各ルールのテスト
│   ├── test_trace.py          # TraceEngine（冗長検出等のアルゴリズム）のテスト
│   ├── test_session.py        # SessionManager（プロキシセッション管理）のテスト
│   ├── test_evaluate.py       # EvaluateEngine（成功条件評価）のテスト
│   └── test_compare.py        # メトリクス比較のテスト
└── models/
    └── test_models.py         # Pydanticモデルのバリデーションテスト
```

**命名規則**: `test_[テスト対象ファイル名].py`

#### integration/

**役割**: コンポーネント間の結合テスト

```
tests/integration/
├── test_server.py             # MCPサーバーレイヤー → エンジンレイヤーの結合
└── test_storage.py            # TraceStorage ↔ SQLiteの結合
```

#### e2e/

**役割**: エンドツーエンドテスト（MCP Gauge全体を通しで検証）

```
tests/e2e/
└── test_dogfooding.py         # MCP Gaugeでテスト用MCPサーバーをテスト
```

#### fixtures/

**役割**: テスト用の共有データ・モックサーバー

```
tests/fixtures/
├── mock_server/
│   └── server.py              # テスト用モックMCPサーバー
└── scenarios/
    └── sample.yaml            # テスト用シナリオ定義
```

## ファイル配置規則

### ソースファイル

| ファイル種別 | 配置先 | 命名規則 | 例 |
|------------|--------|---------|-----|
| MCPサーバー | `src/mcp_gauge/` | snake_case | `server.py` |
| エンジン | `src/mcp_gauge/engines/` | snake_case（機能名） | `lint.py`, `trace.py` |
| インフラ | `src/mcp_gauge/infra/` | snake_case（接続先名） | `mcp_client.py`, `storage.py` |
| データモデル | `src/mcp_gauge/models/` | snake_case（ドメイン概念） | `trace.py`, `scenario.py` |

### テストファイル

| テスト種別 | 配置先 | 命名規則 | 例 |
|-----------|--------|---------|-----|
| ユニットテスト | `tests/unit/[layer]/` | `test_[対象].py` | `test_lint.py` |
| 統合テスト | `tests/integration/` | `test_[対象].py` | `test_server.py` |
| E2Eテスト | `tests/e2e/` | `test_[シナリオ].py` | `test_dogfooding.py` |

### 設定ファイル

| ファイル種別 | 配置先 | 説明 |
|------------|--------|------|
| プロジェクト定義 | `pyproject.toml` | 依存関係、ビルド設定、ツール設定 |
| 依存ロック | `uv.lock` | 再現可能なビルド用 |
| Claude Code | `CLAUDE.md` | Claude Code指示書 |
| ツール設定 | `pyproject.toml`内 | ruff, pytest, mypy等の設定 |

## 命名規則

### ディレクトリ名
- **レイヤーディレクトリ**: 複数形、snake_case
  - 例: `engines/`, `models/`
- **機能ディレクトリ**: 単数形、snake_case
  - 例: `mock_server/`

### ファイル名
- **全Pythonファイル**: snake_case
  - 例: `lint.py`, `mcp_client.py`, `trace.py`
- **テストファイル**: `test_`プレフィックス + snake_case
  - 例: `test_lint.py`, `test_storage.py`

### Python命名規則
- **クラス名**: PascalCase（`LintEngine`, `TraceStorage`）
- **関数名**: snake_case（`detect_redundant_calls`）
- **定数名**: UPPER_SNAKE_CASE（`AMBIGUOUS_PATTERNS`）
- **プライベート**: `_`プレフィックス（`_calculate_summary`）

## 依存関係のルール

### レイヤー間の依存

```
MCPサーバーレイヤー (server.py)
    ↓ (OK)
エンジンレイヤー (engines/)
    ↓ (OK)
インフラレイヤー (infra/)
```

**modelsは全レイヤーから参照可能**:
```
server.py ──→ models/  (OK)
engines/  ──→ models/  (OK)
infra/    ──→ models/  (OK)
models/   ──→ (なし)   (外部依存なし)
```

**禁止される依存**:
- infra/ → engines/ (逆方向)
- infra/ → server.py (逆方向)
- engines/ → server.py (逆方向)

## スケーリング戦略

### 機能の追加

新しいエンジン（例: セキュリティ検証）を追加する場合:

1. `src/mcp_gauge/engines/security.py` にエンジンクラスを作成
2. `src/mcp_gauge/models/` に必要なデータモデルを追加
3. `src/mcp_gauge/server.py` に新しいツールハンドラを追加
4. `tests/unit/engines/test_security.py` にユニットテストを追加

### リンティングルールの追加

`engines/lint.py` 内の `LintRule` 基底クラスを継承した新ルールクラスを追加し、`LintEngine.rules`リストに登録する。

### ファイルサイズの管理

**分割の目安**:
- 1ファイル: 300行以下を推奨
- 300-500行: リファクタリングを検討
- 500行以上: 分割を推奨

**分割の例**: `engines/lint.py` が大きくなった場合
```
engines/
├── lint/
│   ├── __init__.py        # LintEngine（メインクラス）
│   ├── rules.py           # 全ルールクラス
│   └── patterns.py        # 検出パターン定義
```

## 除外設定

### .gitignore

実際の `.gitignore` ファイルを正として管理する。主な除外対象:

- Python関連: `__pycache__/`, `*.py[cod]`, `*$py.class`, `*.so`, `dist/`, `build/`, `*.egg-info/`, `.eggs/`, `*.egg`
- 仮想環境: `.venv/`, `venv/`
- 環境変数: `.env`, `.env.local`
- テスト: `htmlcov/`, `.coverage`, `.coverage.*`, `coverage.xml`, `*.cover`, `.pytest_cache/`
- ツール: `.ruff_cache/`
- IDE: `.idea/`, `.vscode/`, `*.swp`
- データ: `*.db`, `*.sqlite3`
- OS: `.DS_Store`
- ステアリング: `.steering/`
