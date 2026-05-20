# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

ViMax Lite は、AI動画生成の前段階である制作設計工程を自動化するPython CLIツールです。HKUDS/ViMaxを参考に、アイデアや脚本をマルチエージェントパイプラインに通し、制作設計書、構造化JSON、絵コンテ、画像・動画生成プロンプト、継続性レポート、任意の参考画像を出力します。動画自体は生成しません。

UIとLLMプロンプトはすべて日本語です。

## よく使うコマンド

```bash
# インストール（編集可能モード、dev依存込み）
pip install -e ".[dev]"

# テスト実行（どちらでも可）
python -m unittest discover -s tests
python -m pytest

# テストを1件だけ実行
python -m pytest tests/test_pipeline.py::PipelineTest::test_mock_provider_structured_brief

# mock providerでCLI実行（APIキー不要）
vimax-lite init --project demo
vimax-lite idea2design --project demo --idea "アイデア" --provider mock

# Geminiで実行
vimax-lite idea2design --project demo --idea "アイデア" --provider gemini --model gemini-2.5-flash
```

## アーキテクチャ

**パイプラインの流れ**（`pipeline.py`で定義）:
1. `IdeationAgent` → `ScreenwriterAgent` → `CharacterAgent` → `ScenePlannerAgent` → `ShotDirectorAgent` → `PromptEngineerAgent`
2. `ContinuityCriticAgent`が制作設計全体を評価し、問題があれば`RevisionAgent`が修正方針を提示
3. `ImageGenerationAgent`は任意で最後に実行

全エージェントは`agents.py`の`Agent`を継承し、`LLMProvider`を受け取り、Pydanticモデルを返します。エージェント間の一貫性を保つため、`RAGStore`インスタンスを受け取って参照・書き込みを行います。

**各モジュールの役割:**

- `cli.py` — argparseベースのCLI。サブコマンド: `init`, `idea2design`, `script2design`, `generate-images`, `revise`, `inspect-rag`
- `pipeline.py` — エージェントを順次実行し、プロジェクト初期化と出力書き込みを管理
- `agents.py` — 各エージェントクラスは単一のLLM呼び出しとプロンプトテンプレートをラップ。実行中にRAGへ書き込む
- `providers.py` — `LLMProvider`抽象クラスと、`GeminiProvider`（`response_schema`による構造化出力）および`MockProvider`（全スキーマ型の決定論的フィクスチャ）。`normalize_aspect_ratio()`は未対応比率（例: `2.35:1` → `21:9`）をGemini対応比率へ丸める
- `models.py` — 全Pydanticデータモデル（`ProductionBrief`, `ProductionDesign`, `ShotPlan`など）と`ProjectPaths`
- `schemas.py` — エージェントの構造化出力ターゲットとなるラッパーモデル（`ScriptList`, `ShotList`, `PromptBundle`など）
- `rag.py` — `RAGStore`によるキーワードベース検索。キャラクター、ショット、プロンプト、画像メタデータを`MemoryRecord`として保存。全検索は`trace`に記録されRAG参照履歴出力に使われる
- `renderers.py` — `ProductionDesign`をMarkdownファイルに変換し、JSON出力を書き込む

**出力構造**は`outputs/<project>/`以下に配置。`design.json`, `design.md`, `storyboard.md`, `image_prompts.md`, `video_prompts.md`, `continuity_report.md`, `rag_trace.md`, `learning_notes.md`, `images/`。

## 開発上の注意

- Python 3.10+、全ファイルで`from __future__ import annotations`を使用
- `--provider gemini`には`GEMINI_API_KEY`環境変数が必要。mock providerはオフラインで動作
- Mock providerはPydanticモデルのクラス名をキーに決定論的データを返す — 新しいエージェント戻り値型を追加する際は`providers.py`の`_mock_payload()`にケースを追加する必要がある
- テストは`tempfile.TemporaryDirectory`を使い、`cli.main()`にargvリストを直接渡して実行
- `pyproject.toml`で`pythonpath = ["src"]`を設定済み。テスト内の`sys.path.insert`は旧来のフォールバック

## 言語

すべての出力（会話、説明、コメント、コミットメッセージ）は**日本語**。コード内変数名・関数名は英語可。
