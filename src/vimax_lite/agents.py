from __future__ import annotations

import time
from pathlib import Path

from vimax_lite.models import GeneratedImage, ProductionBrief, ProductionDesign, SunoMusicParams
from vimax_lite.providers import LLMProvider, normalize_aspect_ratio
from vimax_lite.rag import RAGStore
from vimax_lite.schemas import CharacterList, ContinuityReport, PromptBundle, RevisionResult, SceneList, ScriptList, ShotList, SunoMusicParamsSchema


class Agent:
    name = "agent"

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider


class IdeationAgent(Agent):
    name = "企画整理エージェント"

    def run(self, user_input: str, *, audience: str, style: str, duration_seconds: int, output_mode: str = "standard", genre: str = "", mood: str = "", color_tone: str = "", narration_style: str = "", target_platform: str = "") -> ProductionBrief:
        mode_instruction = output_mode_instruction(output_mode)
        creative_context = ""
        if genre:
            creative_context += f"\nジャンル: {genre}"
        if mood:
            creative_context += f"\n雰囲気: {mood}"
        if color_tone:
            creative_context += f"\n色調: {color_tone}"
        if narration_style:
            creative_context += f"\nナレーション文体: {narration_style}"
        if target_platform:
            creative_context += f"\n配信プラットフォーム: {target_platform}"
        prompt = f"""
あなたはViMax風の動画制作ワークフローにおける企画整理エージェントです。
ユーザーの入力を、短編映像の制作設計に使えるProductionBriefへ変換してください。
出力は必ず指定されたJSON Schemaに従ってください。
{mode_instruction}

USER_INPUT: {user_input}
想定視聴者: {audience}
映像スタイル: {style}
想定尺: {duration_seconds}秒
OUTPUT_MODE: {output_mode}
{creative_context}
"""
        brief = self.provider.generate_structured(prompt, ProductionBrief)
        brief.audience = brief.audience or audience
        brief.style = brief.style or style
        brief.duration_seconds = duration_seconds
        brief.output_mode = output_mode if output_mode in {"standard", "remotion", "mv"} else "standard"
        return brief


class ScreenwriterAgent(Agent):
    name = "脚本エージェント"

    def run(self, brief: ProductionBrief, source_script: str | None = None) -> ScriptList:
        mode_instruction = output_mode_instruction(brief.output_mode)
        prompt = f"""
あなたは脚本エージェントです。
短編映像向けに3から7個のビートを作ってください。
既存脚本がある場合は、主要な出来事を保ちながら映像向けに整理してください。
{mode_instruction}

制作ブリーフ:
{brief.model_dump_json(indent=2)}

既存脚本:
{source_script or "なし"}
"""
        return self.provider.generate_structured(prompt, ScriptList)


class CharacterAgent(Agent):
    name = "キャラクター設計エージェント"

    def run(self, brief: ProductionBrief, script: ScriptList, rag: RAGStore) -> CharacterList:
        context = rag.context_block(brief.logline, used_by=self.name)
        prompt = f"""
あなたはキャラクター設計エージェントです。
映像生成で一貫性を保つため、キャラクターID、外見、服装、声、継続性メモを明確にしてください。
参照画像生成でそのまま使えるように、appearance、wardrobe、continuity_notes は英語で書いてください。
入力が日本語の場合も、意味を保ったまま視覚的に明確な英語へ変換してください。

RAG参照情報:
{context}

制作ブリーフ:
{brief.model_dump_json(indent=2)}

脚本ビート:
{script.model_dump_json(indent=2)}
"""
        result = self.provider.generate_structured(prompt, CharacterList)
        for character in result.items:
            rag.add_character(character)
        return result


class ScenePlannerAgent(Agent):
    name = "シーン設計エージェント"

    def run(self, brief: ProductionBrief, script: ScriptList, characters: CharacterList, rag: RAGStore) -> SceneList:
        context = rag.context_block(brief.logline, used_by=self.name)
        prompt = f"""
あなたはシーン設計エージェントです。
脚本ビートを、場所、時間、登場人物、目的、継続性要件が明確なシーンへ分割してください。

RAG参照情報:
{context}

制作ブリーフ:
{brief.model_dump_json(indent=2)}

キャラクター:
{characters.model_dump_json(indent=2)}

脚本ビート:
{script.model_dump_json(indent=2)}
"""
        return self.provider.generate_structured(prompt, SceneList)


class ShotDirectorAgent(Agent):
    name = "ショット設計エージェント"

    def run(self, brief: ProductionBrief, scenes: SceneList, characters: CharacterList, rag: RAGStore) -> ShotList:
        context = rag.context_block(" ".join(scene.summary for scene in scenes.items), used_by=self.name, limit=8)
        mode_instruction = output_mode_instruction(brief.output_mode)
        caption_instruction = ""
        if brief.output_mode == "remotion":
            style_guide = _narration_style_guide(brief.narration_style)
            caption_instruction = f"""
各ショットの narration_caption フィールドに、字幕として表示する短い文章を30〜60文字の日本語で入れてください。
これはショットの映像説明ではなく、視聴者に伝えるストーリーの一文です。{style_guide}
例: 「雨の降る夜の路地。小さなロボットが立ち止まり、遠くの音に耳を澄ませる。」
"""
        elif brief.output_mode == "mv":
            caption_instruction = """
各ショットの narration_caption フィールドに、そのショットの映像に合わせた歌詞の一部（1〜2行）を入れてください。
これはミュージックビデオの歌詞字幕として使われます。歌詞は詩的で感情的な日本語にしてください。
例: 「雨の路地に光る水たまり / 小さなロボットが立ち止まる」
"""
        prompt = f"""
あなたはショット設計エージェントです。
各シーンをショット単位に分け、カメラ、レンズ、動き、first frame、last frame、照明、音を具体化してください。
RAG参照情報に含まれるキャラクターや世界観の一貫性を必ず守ってください。
{mode_instruction}
{caption_instruction}

RAG参照情報:
{context}

制作ブリーフ:
{brief.model_dump_json(indent=2)}

キャラクター:
{characters.model_dump_json(indent=2)}

シーン:
{scenes.model_dump_json(indent=2)}
"""
        result = self.provider.generate_structured(prompt, ShotList)
        for shot in result.items:
            rag.add_shot(shot)
        return result


class PromptEngineerAgent(Agent):
    name = "プロンプト設計エージェント"

    def run(self, brief: ProductionBrief, shots: ShotList, rag: RAGStore) -> PromptBundle:
        context = rag.context_block(" ".join(shot.description for shot in shots.items), used_by=self.name, limit=10)
        mode_instruction = output_mode_instruction(brief.output_mode)
        prompt = f"""
あなたはプロンプト設計エージェントです。
ショット設計から、画像生成プロンプトと動画生成プロンプトを作成してください。
画像プロンプトは視覚要素を具体的に、動画プロンプトは時間変化とカメラ移動を具体的に書いてください。
画像生成モデルでの安定性を高めるため、image_prompts.prompt と image_prompts.negative_prompt は英語で書いてください。
入力情報が日本語の場合も、意味を保ったまま英語の画像生成プロンプトに変換してください。
{mode_instruction}

RAG参照情報:
{context}

制作ブリーフ:
{brief.model_dump_json(indent=2)}

ショット:
{shots.model_dump_json(indent=2)}
"""
        result = self.provider.generate_structured(prompt, PromptBundle)
        for image_prompt in result.image_prompts:
            rag.add_prompt(image_prompt)
        return result


class ContinuityCriticAgent(Agent):
    name = "継続性評価エージェント"

    def run(self, design: ProductionDesign, rag: RAGStore) -> ContinuityReport:
        context = rag.context_block(design.brief.logline, used_by=self.name, limit=12)
        prompt = f"""
あなたは継続性評価エージェントです。
キャラクターの外見、衣装、時系列、場所、画面連続性、プロンプトの弱さを確認してください。
問題がある場合だけ、具体的で修正可能な指摘を返してください。

RAG参照情報:
{context}

制作設計:
{design.model_dump_json(indent=2)}
"""
        return self.provider.generate_structured(prompt, ContinuityReport)


class RevisionAgent(Agent):
    name = "修正エージェント"

    def run(self, design: ProductionDesign, rag: RAGStore) -> RevisionResult:
        prompt = f"""
あなたは修正エージェントです。
継続性評価の指摘を読み、制作設計を改善するための短い修正方針を返してください。
完全な設計書を書き直すのではなく、どこをどう直すべきかを簡潔に返してください。

制作設計:
{design.model_dump_json(indent=2)}
"""
        return self.provider.generate_structured(prompt, RevisionResult)


class MusicAgent(Agent):
    name = "音楽設計エージェント"

    def run(self, brief: ProductionBrief, *, message: str = "") -> SunoMusicParams:
        genre_context = ""
        if brief.genre:
            genre_context += f"\nジャンル: {brief.genre}"
        if brief.mood:
            genre_context += f"\n雰囲気: {brief.mood}"
        if brief.color_tone:
            genre_context += f"\n色調: {brief.color_tone}"
        regeneration = ""
        if message:
            regeneration = f"\n追加の要望: {message}\nこの要望を反映してパラメータを再生成してください。"
        prompt = f"""
あなたは音楽設計エージェントです。
映像作品のアイデアから、Suno AIで音楽を生成するためのパラメータを作成してください。

タイトル: {brief.title}
ログライン: {brief.logline}
映像スタイル: {brief.style}
想定尺: {brief.duration_seconds}秒
{genre_context}
{regeneration}

以下の形式で出力してください:
- lyrics: Suno向けのメタタグ付き歌詞。[Intro], [Verse 1], [Chorus], [Bridge], [Outro] 等のセクションタグを使って構造化してください。歌詞は日本語で、映像の世界観に合う詩的な内容にしてください。想定尺{brief.duration_seconds}秒に収まる長さにしてください（概ね1行あたり3秒で計算）。
- style: Sunoが理解できる英語のジャンル・雰囲気記述（例: "cinematic electronic, ambient, melancholic, Japanese pop"）
- weirdness: 創造性の度合い 0-100（保守的〜実験的）
- style_influence: Style指定への忠実度 0-100
- audio_influence: 音響的特性の探求度 0-100
"""
        result = self.provider.generate_structured(prompt, SunoMusicParamsSchema)
        return SunoMusicParams(
            lyrics=result.lyrics,
            style=result.style,
            weirdness=result.weirdness,
            style_influence=result.style_influence,
            audio_influence=result.audio_influence,
        )


class ImageGenerationAgent(Agent):
    name = "画像生成エージェント"

    def run(
        self,
        design: ProductionDesign,
        image_dir: Path,
        rag: RAGStore,
        *,
        image_model: str,
        max_images: int | None = None,
        delay_seconds: float = 0.0,
    ) -> list[GeneratedImage]:
        generated: list[GeneratedImage] = []
        for index, image_prompt in enumerate(design.image_prompts, start=1):
            if max_images is not None and len(generated) >= max_images:
                break
            if delay_seconds > 0 and generated:
                time.sleep(delay_seconds)
            path = image_dir / f"shot_{index:03d}.png"
            normalized_aspect_ratio = normalize_aspect_ratio(image_prompt.aspect_ratio)
            try:
                self.provider.generate_image(
                    image_prompt.prompt,
                    path,
                    model=image_model,
                    aspect_ratio=normalized_aspect_ratio,
                )
                image = GeneratedImage(
                    shot_id=image_prompt.shot_id,
                    path=str(path),
                    model=image_model,
                    prompt=f"{image_prompt.prompt}\n\naspect_ratio: {normalized_aspect_ratio}",
                    status="success",
                )
            except Exception as exc:
                image = GeneratedImage(
                    shot_id=image_prompt.shot_id,
                    path=None,
                    model=image_model,
                    prompt=f"{image_prompt.prompt}\n\naspect_ratio: {normalized_aspect_ratio}",
                    status="failed",
                    error=str(exc),
                )
            rag.add_image(image)
            generated.append(image)
        return generated


def _narration_style_guide(narration_style: str) -> str:
    guides = {
        "third_person": "三人称の語り口で、情景と出来事を物語のように書いてください。",
        "first_person": "主人公の一人称で、その場の気持ちや気づきを語るように書いてください。",
        "dialogue": "キャラクターのセリフや掛け合いの形式で書いてください。",
        "none": "",
    }
    return guides.get(narration_style, "絵本のように、やさしい語り口で情景と感情を伝える短い文にしてください。")


def output_mode_instruction(output_mode: str) -> str:
    if output_mode == "remotion":
        return """
出力モード: Remotion assembly.
このモードではAI動画生成APIではなく、生成済み静止画をRemotionで順番につなげ、字幕と読み上げ音声を重ねる前提で設計してください。
- 脚本ビートは、字幕やナレーションに変換しやすい短い出来事単位にしてください。
- ショットは1枚絵として成立し、ゆるいズーム、パン、フェードだけでも意味が伝わる構図にしてください。
- motion は激しいアクションではなく、Remotionで再現しやすい slow zoom, slow pan, crossfade, hold, parallax などを中心にしてください。
- audio には読み上げナレーション、環境音、短い効果音の方針を含めてください。
- video_prompts は動画生成API向けではなく、Remotionでの編集指示、字幕候補、ナレーション候補、ショット秒数の意図が分かる内容にしてください。
"""
    if output_mode == "mv":
        return """
出力モード: Music Video (MV) mode.
このモードではSunoで生成した音楽に合わせて、静止画をRemotionでつなぎ、歌詞字幕を重ねるミュージックビデオを制作します。
- ショットは楽曲の各セクション（Intro, Verse, Chorus, Bridge, Outro）に対応するように設計してください。
- 各ショットは1枚絵として成立し、ゆるいズームやパンで楽曲のテンポ感に合わせてください。
- motion は楽曲の雰囲気に合うよう slow zoom, slow pan, hold を中心にしてください。
- audio には楽曲のセクション名と雰囲気を含めてください（例: 「Verse 1: 静かで神秘的な電子音」）。
- video_prompts はRemotionでの編集指示として、楽曲との同期を意識した内容にしてください。
- image_prompts は楽曲の感情やビジュアルテーマを反映した構図にしてください。
"""
    return """
出力モード: Standard video-generation prep.
動画生成APIへ渡す前段の制作設計として、first frame / last frame、時間変化、カメラ移動を具体化してください。
"""
