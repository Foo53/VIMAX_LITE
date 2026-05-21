from __future__ import annotations

import time
from pathlib import Path

from vimax_lite.models import GeneratedImage, ProductionBrief, ProductionDesign
from vimax_lite.providers import LLMProvider, normalize_aspect_ratio
from vimax_lite.rag import RAGStore
from vimax_lite.schemas import CharacterList, ContinuityReport, PromptBundle, RevisionResult, SceneList, ScriptList, ShotList


class Agent:
    name = "agent"

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider


class IdeationAgent(Agent):
    name = "企画整理エージェント"

    def run(self, user_input: str, *, audience: str, style: str, duration_seconds: int) -> ProductionBrief:
        prompt = f"""
あなたはViMax風の動画制作ワークフローにおける企画整理エージェントです。
ユーザーの入力を、短編映像の制作設計に使えるProductionBriefへ変換してください。
出力は必ず指定されたJSON Schemaに従ってください。

USER_INPUT: {user_input}
想定視聴者: {audience}
映像スタイル: {style}
想定尺: {duration_seconds}秒
"""
        brief = self.provider.generate_structured(prompt, ProductionBrief)
        brief.audience = brief.audience or audience
        brief.style = brief.style or style
        brief.duration_seconds = duration_seconds
        return brief


class ScreenwriterAgent(Agent):
    name = "脚本エージェント"

    def run(self, brief: ProductionBrief, source_script: str | None = None) -> ScriptList:
        prompt = f"""
あなたは脚本エージェントです。
短編映像向けに3から7個のビートを作ってください。
既存脚本がある場合は、主要な出来事を保ちながら映像向けに整理してください。

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
        prompt = f"""
あなたはショット設計エージェントです。
各シーンをショット単位に分け、カメラ、レンズ、動き、first frame、last frame、照明、音を具体化してください。
RAG参照情報に含まれるキャラクターや世界観の一貫性を必ず守ってください。

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
        prompt = f"""
あなたはプロンプト設計エージェントです。
ショット設計から、画像生成プロンプトと動画生成プロンプトを作成してください。
画像プロンプトは視覚要素を具体的に、動画プロンプトは時間変化とカメラ移動を具体的に書いてください。
画像生成モデルでの安定性を高めるため、image_prompts.prompt と image_prompts.negative_prompt は英語で書いてください。
入力情報が日本語の場合も、意味を保ったまま英語の画像生成プロンプトに変換してください。

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
