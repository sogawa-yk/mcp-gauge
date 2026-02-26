# 技術仕様書 (Architecture Design Document)

## テクノロジースタック

### 言語・ランタイム

| 技術 | バージョン |
|------|-----------|
| Python | 3.12+ |
| uv | 最新安定版 |

- **Python 3.12+**
  - MCP Python SDKが公式サポートする主要言語
  - asyncio対応が成熟しており、MCPサーバーの非同期通信に適する
  - 型ヒント（typing）の強化により、構造化データの定義が明確
  - MCPサーバー開発のエコシステム（mcp SDK）がPythonに集中している

- **uv**
  - 依存解決・インストールが高速
  - pyproject.tomlベースの標準的なプロジェクト管理
  - ロックファイル（uv.lock）による再現可能なビルド

### フレームワーク・ライブラリ

| 技術 | 用途 | 選定理由 |
|------|------|----------|
| mcp (Python SDK) | MCPサーバー/クライアント実装 | 公式SDK、stdio/SSEトランスポート対応、サーバー・クライアント両方を単一ライブラリで実装可能 |
| aiosqlite | 非同期SQLiteアクセス | asyncioベースのMCPサーバー内から非同期でDB操作可能 |
| pydantic | データモデル定義・バリデーション | 型安全なデータモデル、JSON変換の自動化、MCPのinputSchemaとの親和性 |
| pyyaml | シナリオ定義ファイル読み込み | YAMLパーサーのデファクトスタンダード |

### 開発ツール

| 技術 | 用途 | 選定理由 |
|------|------|----------|
| pytest | テスト実行 | Pythonのデファクトスタンダード |
| pytest-asyncio | 非同期テスト | asyncioコードのテスト対応 |
| ruff | リンター/フォーマッター | 高速、ruff formatとruff checkで統一 |
| mypy | 型チェック | 静的型解析で型安全性を担保 |

## アーキテクチャパターン

### レイヤードアーキテクチャ

```
┌──────────────────────────────────┐
│   MCPサーバーレイヤー              │ ← MCPプロトコルの処理、ツール公開
├──────────────────────────────────┤
│   エンジンレイヤー                 │ ← 各機能のビジネスロジック
│   (Lint / Trace / Session /      │
│    Evaluate / Compare / Report)  │
├──────────────────────────────────┤
│   インフラレイヤー                 │ ← 外部接続・データ永続化
│   (MCPClient / TraceStorage)     │
└──────────────────────────────────┘
```

#### MCPサーバーレイヤー
- **責務**: MCPプロトコルでツールを公開し、リクエストをエンジンレイヤーに委譲する。結果を構造化JSONで返す
- **許可される操作**: エンジンレイヤーの呼び出し
- **禁止される操作**: インフラレイヤーへの直接アクセス、ビジネスロジックの実装

#### エンジンレイヤー
- **責務**: リンティング、トレーシング、プロキシセッション管理、成功条件評価、比較、レポート生成の各ビジネスロジック
- **許可される操作**: インフラレイヤーの呼び出し
- **禁止される操作**: MCPプロトコル固有の処理

#### インフラレイヤー
- **責務**: テスト対象MCPサーバーへの接続、SQLiteへのデータ永続化
- **許可される操作**: 外部サービス・ファイルシステムへのアクセス
- **禁止される操作**: ビジネスロジックの実装

### パッケージ構成

```
src/mcp_gauge/
├── __init__.py
├── __main__.py            # エントリーポイント（python -m mcp_gauge）
├── server.py              # MCPサーバーレイヤー: GaugeServer
├── engines/               # エンジンレイヤー
│   ├── __init__.py
│   ├── lint.py            # LintEngine + LintRules
│   ├── trace.py           # TraceEngine
│   ├── session.py         # SessionManager（プロキシセッション管理）
│   ├── evaluate.py        # EvaluateEngine（成功条件評価）
│   ├── compare.py         # CompareEngine
│   └── report.py          # ReportGenerator
├── infra/                 # インフラレイヤー
│   ├── __init__.py
│   ├── mcp_client.py      # 対象MCPサーバーへの接続
│   └── storage.py         # TraceStorage（SQLite）
├── models/                # データモデル（Pydantic）
│   ├── __init__.py
│   ├── trace.py           # TraceSession, TraceRecord, TraceSummary
│   ├── lint.py            # LintResult
│   ├── scenario.py        # ScenarioDefinition, SuccessCriteria
│   └── results.py         # ScenarioResult, ComparisonResult, Report
└── config.py              # GaugeConfig
```

### 設定項目（GaugeConfig）

| 設定キー | 取得元 | デフォルト値 | 説明 |
|---------|--------|------------|------|
| MCP_GAUGE_DB_PATH | 環境変数 | ~/.mcp-gauge/gauge.db | SQLiteファイルパス |
| MCP_GAUGE_TIMEOUT | 環境変数 | 30 | 対象サーバー接続タイムアウト（秒） |
| MCP_GAUGE_TOOL_TIMEOUT | 環境変数 | 300 | ツール呼び出しタイムアウト（秒） |

## データ永続化戦略

### ストレージ方式

| データ種別 | ストレージ | フォーマット | 理由 |
|-----------|----------|-------------|------|
| トレースデータ（TraceSession, TraceRecord, TraceSummary） | SQLite | リレーショナル | 集計クエリ・結合が必要、10万レコード規模に対応 |
| テストシナリオ定義 | ファイルシステム | YAML | ユーザーが編集しやすい、Gitで管理可能 |
| 設定 | 環境変数 + TOML | - | APIキーは環境変数、その他はTOML |

### SQLiteスキーマ

```sql
CREATE TABLE trace_sessions (
    id TEXT PRIMARY KEY,
    server_command TEXT NOT NULL,
    server_args TEXT,  -- JSON array
    scenario_id TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    task_success INTEGER  -- 0/1/NULL
);

CREATE TABLE trace_records (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES trace_sessions(id),
    sequence INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,  -- JSON
    result TEXT NOT NULL,     -- JSON
    is_error INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE INDEX idx_records_session ON trace_records(session_id);

CREATE TABLE trace_summaries (
    session_id TEXT PRIMARY KEY REFERENCES trace_sessions(id),
    total_calls INTEGER NOT NULL,
    unique_tools INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    redundant_calls INTEGER NOT NULL,
    total_duration_ms REAL NOT NULL,
    recovery_steps INTEGER NOT NULL,
    tool_call_sequence TEXT NOT NULL  -- JSON array
);
```

### バックアップ戦略

- **頻度**: 自動バックアップなし（トレースデータは再生成可能なため）
- **データ保全**: SQLiteのWALモードを有効化し、クラッシュ時のデータ損失を防止
- **エクスポート**: `gauge_report`ツールでJSON形式にエクスポート可能

### クラッシュリカバリー設計

- **書き込み戦略**: TraceRecordは呼び出し都度コミット（部分データ保持を優先）。TraceSummaryはセッション終了時にコミット
- **未完了セッションの扱い**: MCP Gauge起動時にstatus='running'のセッションを検出し、'failed'に変更する。部分的なTraceRecordは保持する（再実行で補完可能なためパージしない）
- **WALモードの保護範囲**: コミット済みトランザクションは保護される。TraceRecordは逐次コミットのため、最後にコミットされたレコードまでが保持される

## パフォーマンス要件

### レスポンスタイム

| 操作 | 目標時間 | 測定条件 |
|------|---------|---------|
| ツール説明文リンティング | 5秒以内 | 100ツール以下のMCPサーバー |
| トレース記録オーバーヘッド | 50ms以下/呼び出し | SQLite WALモード |
| レポート生成 | 10秒以内 | 1000トレースレコード |
| MCPサーバー起動 | 2秒以内 | 初回起動時（DB初期化含む） |

### リソース使用量

| リソース | 上限 | 理由 |
|---------|------|------|
| メモリ | 256MB | トレースデータはDBに逐次書き込み、メモリには現在セッション分のみ保持 |
| ディスク | 1GB | SQLiteデータベース（10万レコード想定） |

## セキュリティアーキテクチャ

### データ保護

- **APIキー管理**: プロキシ型アーキテクチャにより、LLM APIキーの管理は不要。呼び出し元エージェント側で管理される
- **アクセス制御**: SQLiteデータベースファイルのパーミッションを`600`（所有者のみ読み書き）に設定
- **トレースデータの機密性**: トレースデータにはテスト対象サーバーの入出力が含まれる。ローカルファイルに保存し、外部送信しない

### 入力検証

- **server_command**: パス文字列として検証。シェルインジェクション防止のため、`subprocess`の配列形式で実行（shell=False）
- **シナリオ定義**: Pydanticモデルでバリデーション。不正なフィールドはエラーとして拒否
- **trace_id**: UUID v4形式の検証

### プロセス隔離

- テスト対象MCPサーバーはサブプロセスとして起動する
- MCP Gaugeプロセスとは標準入出力（stdio）で通信し、プロセス空間を分離する
- テスト対象サーバーのクラッシュがMCP Gaugeに影響しないよう、タイムアウトと例外ハンドリングを実装

## スケーラビリティ設計

### データ増加への対応

- **想定データ量**: 10万トレースレコード（約100セッション × 1000レコード/セッション）
- **パフォーマンス劣化対策**: session_idへのインデックスにより、セッション単位のクエリを高速化
- **アーカイブ戦略**: MVP段階では手動削除。将来的にセッション単位のパージ機能を検討

### 機能拡張性

- **リンティングルールの追加**: `LintRule`基底クラスを継承した新ルールを追加するだけで拡張可能
- **LLMプロバイダーの非依存**: プロキシ型アーキテクチャにより、MCP Gauge自体はLLMプロバイダーに依存しない。呼び出し元エージェント（Claude Code等）が任意のLLMを使用可能
- **MCPツールの追加**: `GaugeServer`に新しいツールハンドラを追加するだけで拡張可能

## テスト戦略

### ユニットテスト
- **フレームワーク**: pytest + pytest-asyncio
- **対象**: エンジンレイヤーの各コンポーネント（LintEngine, TraceEngine, CompareEngine等）
- **カバレッジ目標**: エンジンレイヤー 90%以上

### 統合テスト
- **方法**: テスト用のモックMCPサーバーを用意し、MCP Gauge全体のフローを検証
- **対象**: MCPサーバーレイヤー → エンジンレイヤー → インフラレイヤーの一連の処理

### E2Eテスト
- **方法**: MCP GaugeをClaude Codeから実際に利用し、サンプルMCPサーバーをテスト（dogfooding）
- **シナリオ**: リンティング → 修正 → 再リンティングの自律ループ完結を検証

## 技術的制約

### 環境要件
- **OS**: Linux, macOS（Windowsは未検証）
- **Python**: 3.12以上
- **必要な外部依存**: なし（プロキシ型アーキテクチャのため、LLM APIキー等の外部依存は不要）

### パフォーマンス制約
- テスト対象MCPサーバーの起動時間がテスト全体の所要時間に影響する

### セキュリティ制約
- MCP Gaugeはテスト対象サーバーのツールを実行するため、テスト環境での実行を推奨
- 本番環境のMCPサーバーに対する直接テストは、破壊的操作のリスクがある
- **破壊的操作の防止**: 成功条件のforbidden_toolsはEvaluateEngineで事後評価される。呼び出し元エージェントが破壊的ツールの呼び出しを自律的に回避することを前提とする。LintEngineおよびTraceEngineはツールの実行制御を行わない（リンティング・記録のみ）

## 依存関係管理

| ライブラリ | 用途 | バージョン管理方針 |
|-----------|------|-------------------|
| mcp | MCPサーバー/クライアント | 互換範囲指定（>=1.0,<2.0） |
| aiosqlite | 非同期SQLite | 互換範囲指定 |
| pydantic | データモデル | 互換範囲指定（>=2.0,<3.0） |
| pyyaml | YAML読み込み | 互換範囲指定 |

**方針**:
- メジャーバージョンは固定（破壊的変更を防止）
- マイナー・パッチバージョンは互換範囲で許可
- `uv.lock`で実際のインストールバージョンを固定し、再現可能なビルドを担保
