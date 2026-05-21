# 手作業画像生成ワークフロー

このプロジェクトでは、ChatGPTなどのWeb UIに手作業でプロンプトを貼り付けて画像生成する場合でも、画像の整合性が崩れにくいように参照画像ワークフローを用意しています。

## 基本の流れ

1. Web UIでアイデアを入力して制作設計を生成します。
2. キャラクター参照シートを開き、front / side / back / detail の参照画像をChatGPTで生成します。
3. 生成した参照画像をWeb UIへアップロードします。
4. ショット生成キューを開き、各ショットの「必ず添付する参照画像」とプロンプトを確認します。
5. ChatGPTに参照画像を添付し、表示されたプロンプトを貼り付けて画像を生成します。
6. 生成画像をWeb UIへアップロードします。
7. 次ショットでは、キャラクター参照画像に加えて直前ショット画像も参照候補として表示されます。

## 生成されるファイル

- `references/character_reference_sheet.md`
- `references/character_reference_sheet.json`
- `reference_plan.md`
- `reference_plan.json`
- `manual_generation_guide.md`
- `images/manual/<shot_id>.png`

## 学習ポイント

- 画像生成では、プロンプトだけではキャラクターや背景の一貫性が崩れやすい。
- 参照画像、直前ショット、世界観メモを明示的に管理すると整合性を保ちやすい。
- 本家ViMaxのReference Image Selectorに近い考え方を、まずは人間参加型ワークフローとして実装している。
