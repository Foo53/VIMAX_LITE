# 引き継ぎメモ

このプロジェクトは ViMax Lite。
HKUDS/ViMaxを参考に、動画生成直前までを自動化するPython CLI。

## 現在の状態

- WSLパス: `/home/fumafuma/work/vimax-lite`
- `mock` provider は動作確認済み
- Gemini provider はテキスト生成成功済み
- Gemini画像生成は無料枠/クォータ制限に注意
- 画像生成では非対応比率をGemini対応比率へ丸める
- `generate-images` はデフォルト1枚生成

## 主要ファイル

- `src/vimax_lite/cli.py`
- `src/vimax_lite/providers.py`
- `src/vimax_lite/agents.py`
- `src/vimax_lite/pipeline.py`
- `src/vimax_lite/rag.py`
- `src/vimax_lite/models.py`
- `src/vimax_lite/renderers.py`
- `docs/learning_path.md`
- `docs/architecture.md`
- `README.md`

## 動作確認済み

```bash
vimax-lite idea2design \
  --project portfolio-demo \
  --idea "雨の東京路地で、孤独な配達ロボットが音楽を見つける" \
  --provider mock
'''
