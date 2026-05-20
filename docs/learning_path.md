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

## Phase 7: ポートフォリオ化

生成された成果物、README、アーキテクチャ説明、サンプルを使って、採用面談や GitHub 上でプロジェクトを説明できる状態にします。
