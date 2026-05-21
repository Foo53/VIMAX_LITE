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

## Phase 9: ポートフォリオ化

生成された成果物、README、アーキテクチャ説明、サンプルを使って、採用面談や GitHub 上でプロジェクトを説明できる状態にします。

## Phase 10: 本家 ViMax との差分理解

`docs/vimax_lite_vs_vimax.md` を読みます。現在の実装が本家 ViMax のどの部分を再現していて、どこが未実装なのかを説明できるようにします。特に、Reference Image Selector、Best Image Selector、camera tree、動画生成の違いを理解すると、今後の拡張方針をポートフォリオとして話しやすくなります。
