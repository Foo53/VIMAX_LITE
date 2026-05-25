# ViMax Lite

ViMax Lite は、HKUDS/ViMax の「動画生成前の設計工程」を再現する、ポートフォリオ向けの Python CLI ツールです。

アイデアや脚本の分析、マルチエージェントによる制作設計、RAG による一貫性維持、構造化出力、Gemini API を使った任意の参考画像生成、学習メモの出力を扱います。

このツールはAI動画生成APIによる動画そのものは生成しません。代わりに、動画生成ツールへ渡す前段階の成果物として、制作設計書、構造化 JSON、絵コンテ、画像生成プロンプト、動画生成プロンプト、継続性レポート、RAG の参照履歴、学習メモ、任意の参考画像を生成します。

Remotion を使い、生成済み画像をつなげて字幕を付けた「画像ベースの組み立て動画」を生成できます。MVモードではアップロードしたBGMも動画へ組み込めます。SEと読み上げ音声は今後追加する計画で、将来の動画生成APIとも両立できる設計です。詳細は [docs/remotion_video_assembly_plan.md](docs/remotion_video_assembly_plan.md) にまとめています。

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

Remotionで画像連結動画を作る前提の制作設計にする場合:

```bash
vimax-lite idea2design --project portfolio-demo --idea "..." --provider mock --output-mode remotion
vimax-lite timeline --project portfolio-demo
vimax-lite render-video --project portfolio-demo
```

`render-video` は `remotion/` のNode.js依存関係を使います。初回は `cd remotion && npm install` を実行してください。通常のRemotion動画は字幕付きで、MVモードではアップロードしたBGMを再生できます。SE、読み上げ音声は今後追加予定です。

Web UIでアイデア入力から始める場合:

```bash
vimax-lite web --host 127.0.0.1 --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開くと、アイデア入力、生成進捗、制作設計確認、参照画像シート、ショット画像生成キュー、画像アップロード、残り生成枚数の確認ができます。

参照画像ページとショット画像ページでは、画像生成モデルを選択できます。現在利用できる方式は次の2つです。

- `ChatGPT 手動生成`: 参照画像の添付方法を含む貼り付け用プロンプトを表示します。
- `SDXL + IP-Adapter（ローカル）`: SDXL専用のPositive / Negative Promptを表示し、参照画像をIP-Adapter条件として渡して候補を生成します。

`FLUX + IP-Adapter` と `Gemini Image` は、モデル専用プロンプトと生成バックエンドを追加するための後続対応枠として画面に表示します。

### ローカルSDXLによる候補画像生成

Web UIからローカルSDXLを使う場合は、追加依存関係を導入します。

```bash
pip install -e ".[sdxl]"
```

- 初回生成時にはSDXL本体とIP-Adapterのモデル取得が発生します。CUDA対応GPUを推奨します。
- SDXLの画像はすぐに正式画像へ上書きせず、`images/sdxl_candidates/` に候補として保存します。
- ChatGPT貼り付け用プロンプトをSDXLへ流用せず、SDXL専用のPositive / Negative Promptを使います。
- 内容を確認して「採用」を押した候補だけが、参照画像またはショット画像として次の生成に利用されます。
- キャラクター参照画像は `front` を先に採用し、その画像を参照して他の向きを生成します。
- 参照画像ページの「未保存分の候補を順次生成」では、未保存の `front` 候補を先に作成し、その候補を参照して `side` / `back` / `detail` の候補を続けて生成できます。候補の正式採用は自動では行いません。
- ショット画像は順番に生成・採用します。採用済みの前ショット画像とキャラクター参照画像を、IP-Adapterによる視覚条件付けへ渡します。

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
  sdxl_generation_guide.md
  timeline_manifest.json
  rag_store.json
  references/
    character_reference_sheet.md
    character_reference_sheet.json
  images/
    image_manifest.json
    shot_001.png
    manual/
      <shot_id>.png
    sdxl_candidates/
      reference/
        <reference_id>.png
        <reference_id>.json
      shot/
        <shot_id>.png
        <shot_id>.json
  videos/
    assembled_video.mp4
    render_report.md
```

## 本家 ViMax との差分

現在の ViMax Lite は、本家 ViMax の動画生成パイプライン全体ではなく、動画生成直前までの制作設計、参照画像管理、RAG、学習用ワークフローに絞った実装です。

詳しい差分は [docs/vimax_lite_vs_vimax.md](docs/vimax_lite_vs_vimax.md) にまとめています。

## Remotion による動画組み立て計画

動画生成APIを使わずに、生成済み画像、字幕、読み上げ音声を組み合わせて MP4 を作る拡張計画は [docs/remotion_video_assembly_plan.md](docs/remotion_video_assembly_plan.md) にまとめています。
