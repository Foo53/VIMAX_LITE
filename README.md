# ViMax Lite

ViMax Lite は、HKUDS/ViMax の「動画生成前の設計工程」を再現する、ポートフォリオ向けの Python CLI ツールです。

アイデアや脚本の分析、マルチエージェントによる制作設計、RAG による一貫性維持、構造化出力、Gemini API を使った任意の参考画像生成、学習メモの出力を扱います。

このツールはAI動画生成APIによる動画そのものは生成しません。代わりに、動画生成ツールへ渡す前段階の成果物として、制作設計書、構造化 JSON、絵コンテ、画像生成プロンプト、動画生成プロンプト、継続性レポート、RAG の参照履歴、学習メモ、任意の参考画像を生成します。

今後の派生として、Remotion を使い、生成済み画像をつなげて字幕と読み上げ音声を付けた「画像ベースの組み立て動画」を作る計画があります。これはAI動画生成ではなく編集・レンダリングレイヤーですが、将来の動画生成APIとも両立できる設計です。詳細は [docs/remotion_video_assembly_plan.md](docs/remotion_video_assembly_plan.md) にまとめています。

## セットアップ

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Gemini API を使う場合は、API キーを環境変数に設定します。

```bash
set GEMINI_API_KEY=your_api_key_here
```

Claude Code CLI がインストールされている場合は、`--provider claude` で `claude -p` を使ったテキスト生成ができます（画像生成は未対応）。

```bash
vimax-lite idea2design --project portfolio-demo --idea "..." --provider claude
```

API キーや外部ツールなしで試す場合は、`--provider mock` を指定するとローカルだけでパイプライン全体を実行できます。

## 使い方

```bash
vimax-lite init --project portfolio-demo
vimax-lite idea2design --project portfolio-demo --idea "雨の東京路地で、孤独な配達ロボットが音楽を見つける" --provider mock
vimax-lite inspect-rag --project portfolio-demo
```

Web UIでアイデア入力から始める場合:

```bash
vimax-lite web --host 127.0.0.1 --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開くと、アイデア入力、生成進捗、制作設計確認、参照画像シート、ショット画像生成キュー、画像アップロード、残り生成枚数の確認ができます。

Gemini API を使う場合:

```bash
vimax-lite idea2design --project portfolio-demo --idea "..." --provider gemini --model gemini-2.5-flash
```

想定尺を指定する場合は `--duration-seconds` を使います（デフォルト60秒）。

```bash
# 30秒の短編
vimax-lite idea2design --project portfolio-demo --idea "..." --provider claude --duration-seconds 30

# 3分の作品
vimax-lite idea2design --project portfolio-demo --idea "..." --provider claude --duration-seconds 180

# 5分の作品
vimax-lite idea2design --project portfolio-demo --idea "..." --provider gemini --duration-seconds 300
```

任意で参考画像を生成する場合:

```bash
vimax-lite idea2design --project portfolio-demo --idea "..." --provider gemini --generate-images
vimax-lite generate-images --project portfolio-demo --provider gemini
```

画像生成はAPIクォータを消費しやすいため、デフォルトでは1枚だけ生成します。複数枚を生成する場合は、枚数と待機秒数を指定してください。

```bash
vimax-lite generate-images --project portfolio-demo --provider gemini --max-images 3 --image-delay-seconds 20
```

Gemini画像生成が対応していない比率、たとえば `2.35:1` は、内部で近い対応比率の `21:9` へ丸めます。

## テスト

外部APIなしで、mock provider を使ったパイプライン検証を実行できます。

```bash
python -m unittest discover -s tests
```

`pytest` が入っている環境では、通常どおり `python -m pytest` でも確認できます。

## 出力構成

```text
outputs/<project>/
  design.md
  design.json
  storyboard.md
  image_prompts.md
  video_prompts.md
  continuity_report.md
  rag_trace.md
  learning_notes.md
  reference_plan.md
  reference_plan.json
  manual_generation_guide.md
  rag_store.json
  references/
    character_reference_sheet.md
    character_reference_sheet.json
  images/
    image_manifest.json
    shot_001.png
    manual/
      <shot_id>.png
```

## 本家 ViMax との差分

現在の ViMax Lite は、本家 ViMax の動画生成パイプライン全体ではなく、動画生成直前までの制作設計、参照画像管理、RAG、学習用ワークフローに絞った実装です。

詳しい差分は [docs/vimax_lite_vs_vimax.md](docs/vimax_lite_vs_vimax.md) にまとめています。

## Remotion による動画組み立て計画

動画生成APIを使わずに、生成済み画像、字幕、読み上げ音声を組み合わせて MP4 を作る拡張計画は [docs/remotion_video_assembly_plan.md](docs/remotion_video_assembly_plan.md) にまとめています。
