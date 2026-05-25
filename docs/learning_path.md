# 学習ロードマップ

## Phase 1: Gemini API の基礎

`src/vimax_lite/providers.py` を読みます。API キーの扱い、モデル選択、テキスト生成、画像生成、Provider 抽象化を学びます。

## Phase 2: 構造化出力

`src/vimax_lite/models.py` を読みます。Pydantic モデル、JSON Schema、Gemini の構造化出力、バリデーションを学びます。

## Phase 3: エージェント開発

`src/vimax_lite/agents.py` を読みます。役割別エージェント、入出力契約、ワークフロー制御、再試行しやすい設計を学びます。

## Phase 4: RAG 開発

`src/vimax_lite/rag.py` を読みます。メモリレコード、検索、コンテキスト注入、RAG 参照履歴の記録を学びます。

## Phase 5: 評価と改善

Critic Agent と Revision Agent を読みます。LLM の最初の出力をそのまま信じるのではなく、検査して改善する方法を学びます。

## Phase 6: マルチモーダル生成

Image Generation Agent を読みます。テキストのショット設計から参考画像を生成する流れを学びます。

## Phase 7: 参照画像ワークフロー

`src/vimax_lite/manual_workflow.py` と `docs/manual_image_workflow.md` を読みます。キャラクター参照シート、ショットごとの添付画像指定、ChatGPT貼り付け用手順書、生成画像アップロード、残り生成枚数の管理を学びます。

## Phase 8: Web UI

`src/vimax_lite/web_app.py` と `src/vimax_lite/templates/` を読みます。アイデア入力、バックグラウンド生成、進捗ポーリング、画像生成キュー、アップロード管理を学びます。

## Phase 8.5: 参照画像つきローカル生成と採用ゲート

`src/vimax_lite/sdxl_generator.py` と `src/vimax_lite/web_app.py` のSDXL処理を読みます。IP-Adapterで参照画像そのものを条件付けに使う方法、生成結果を候補として保存して人間の確認後に正式状態へ採用する方法、GPUや依存関係の実行可否をUIへ反映する方法を学びます。

到達目標は、生成AIの出力を即座にアプリ状態へ書き込むのではなく、「生成 -> 評価 -> 採用」という品質管理ループとして設計できることです。

続いて `src/vimax_lite/manual_workflow.py` の `build_manual_prompt()`、`build_sdxl_reference_prompt()`、`build_sdxl_shot_prompt()` を比較します。前者は人間がChatGPTへ操作を伝えるプロンプト、後二者はSDXLへ視覚内容を渡すプロンプトです。

到達目標は、モデル非依存の制作設計を保ったまま、モデルごとに最適化した入力へ変換する「プロンプトコンパイラ」の考え方を説明できることです。

Web UIの参照画像一括順次生成も確認します。最初の生成物を次の生成の入力に渡す処理は、エージェントワークフローでいう依存関係付きタスク実行です。一方で候補を正式状態へ書き込む採用処理は分離されており、効率化と品質ゲートを両立しています。

ショット画像の一括順次生成では、候補画像を次のショットの入力として連鎖させます。これは映像の照明、背景、キャラクター状態を保つための短期記憶に相当します。ただし候補はまだ正式な制作資産ではないため、一括生成後に人が確認して採用する設計になっています。生成の連鎖と状態確定を分ける考え方は、実務のエージェント設計でも重要です。

## Phase 9: ポートフォリオ化

生成された成果物、README、アーキテクチャ説明、サンプルを使って、採用面談や GitHub 上でプロジェクトを説明できる状態にします。

## Phase 10: 本家 ViMax との差分理解

`docs/vimax_lite_vs_vimax.md` を読みます。現在の実装が本家 ViMax のどの部分を再現していて、どこが未実装なのかを説明できるようにします。特に、Reference Image Selector、Best Image Selector、camera tree、動画生成の違いを理解すると、今後の拡張方針をポートフォリオとして話しやすくなります。

## Phase 11: Remotion による動画組み立て

`docs/remotion_video_assembly_plan.md` を読みます。生成済み画像、字幕、読み上げ音声、タイムライン manifest を組み合わせて、動画生成APIなしで MP4 を作る設計を学びます。ここでは、Remotion を動画生成AIではなく、最終編集・レンダリングレイヤーとして扱う考え方を身につけます。Web UI または CLI の `--output-mode remotion` を使うと、Remotion に適した脚本、ショット、編集指示が生成されます。

## Phase 12: 将来の動画生成API対応

Remotion で作った `timeline_manifest.json` を境界にして、Veo、Runway、Pika、Luma などの動画生成 provider を後から追加できる構成を学びます。重要なのは、画像連結動画と本物の動画生成を競合させるのではなく、Remotion を最終合成レイヤーとして残すことです。
