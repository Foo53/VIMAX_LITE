from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from vimax_lite.agents import (
    CharacterAgent,
    ContinuityCriticAgent,
    IdeationAgent,
    ImageGenerationAgent,
    PromptEngineerAgent,
    RevisionAgent,
    ScenePlannerAgent,
    ScreenwriterAgent,
    ShotDirectorAgent,
)
from vimax_lite.models import ProductionDesign, ProjectPaths
from vimax_lite.providers import LLMProvider
from vimax_lite.rag import RAGStore
from vimax_lite.renderers import write_all_outputs, write_image_manifest

ProgressCallback = Callable[[str, str, int, int], None]


def init_project(paths: ProjectPaths) -> None:
    paths.images.mkdir(parents=True, exist_ok=True)
    if not paths.rag_store.exists():
        paths.rag_store.write_text(json.dumps({"records": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not paths.image_manifest.exists():
        paths.image_manifest.write_text(json.dumps({"images": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def run_idea_pipeline(
    *,
    idea: str,
    project: str,
    provider: LLMProvider,
    output_root: Path,
    audience: str,
    style: str,
    duration_seconds: int,
    output_mode: str = "standard",
    genre: str = "",
    mood: str = "",
    color_tone: str = "",
    narration_style: str = "",
    target_platform: str = "",
    generate_images: bool = False,
    image_model: str = "gemini-2.5-flash-image",
    max_images: int | None = None,
    image_delay_seconds: float = 0.0,
    progress: ProgressCallback | None = None,
) -> ProductionDesign:
    paths = ProjectPaths.for_project(project, output_root)
    init_project(paths)
    rag = RAGStore(paths.rag_store)
    _notify(progress, "brief", "企画整理エージェントで制作ブリーフを生成しています", 1, 9)
    brief = IdeationAgent(provider).run(idea, audience=audience, style=style, duration_seconds=duration_seconds, output_mode=output_mode, genre=genre, mood=mood, color_tone=color_tone, narration_style=narration_style, target_platform=target_platform)
    return _run_common(brief, None, provider, rag, paths, generate_images, image_model, max_images, image_delay_seconds, progress)


def run_script_pipeline(
    *,
    script: str,
    project: str,
    provider: LLMProvider,
    output_root: Path,
    audience: str,
    style: str,
    duration_seconds: int,
    output_mode: str = "standard",
    genre: str = "",
    mood: str = "",
    color_tone: str = "",
    narration_style: str = "",
    target_platform: str = "",
    generate_images: bool = False,
    image_model: str = "gemini-2.5-flash-image",
    max_images: int | None = None,
    image_delay_seconds: float = 0.0,
    progress: ProgressCallback | None = None,
) -> ProductionDesign:
    paths = ProjectPaths.for_project(project, output_root)
    init_project(paths)
    rag = RAGStore(paths.rag_store)
    _notify(progress, "brief", "企画整理エージェントで制作ブリーフを生成しています", 1, 9)
    brief = IdeationAgent(provider).run(script, audience=audience, style=style, duration_seconds=duration_seconds, output_mode=output_mode, genre=genre, mood=mood, color_tone=color_tone, narration_style=narration_style, target_platform=target_platform)
    return _run_common(brief, script, provider, rag, paths, generate_images, image_model, max_images, image_delay_seconds, progress)


def generate_images_for_existing_design(
    *,
    project: str,
    provider: LLMProvider,
    output_root: Path,
    image_model: str,
    max_images: int | None = None,
    image_delay_seconds: float = 0.0,
    progress: ProgressCallback | None = None,
) -> ProductionDesign:
    paths = ProjectPaths.for_project(project, output_root)
    design = ProductionDesign.model_validate_json(paths.design_json.read_text(encoding="utf-8"))
    rag = RAGStore(paths.rag_store)
    _notify(progress, "images", "画像生成キューを処理しています", 1, 1)
    design.generated_images = ImageGenerationAgent(provider).run(
        design,
        paths.images,
        rag,
        image_model=image_model,
        max_images=max_images,
        delay_seconds=image_delay_seconds,
    )
    design.rag_trace = rag.trace
    rag.save()
    write_all_outputs(design, paths.root)
    return design


def revise_existing_design(*, project: str, provider: LLMProvider, output_root: Path) -> ProductionDesign:
    paths = ProjectPaths.for_project(project, output_root)
    design = ProductionDesign.model_validate_json(paths.design_json.read_text(encoding="utf-8"))
    rag = RAGStore(paths.rag_store)
    report = ContinuityCriticAgent(provider).run(design, rag)
    design.continuity_issues = report.issues
    revision = RevisionAgent(provider).run(design, rag)
    design.learning_notes.extend(f"修正ループ: {note}" for note in revision.notes)
    design.rag_trace = rag.trace
    rag.save()
    write_all_outputs(design, paths.root)
    write_image_manifest(design.generated_images, paths.image_manifest)
    return design


def _run_common(
    brief,
    source_script: str | None,
    provider: LLMProvider,
    rag: RAGStore,
    paths: ProjectPaths,
    generate_images: bool,
    image_model: str,
    max_images: int | None,
    image_delay_seconds: float,
    progress: ProgressCallback | None,
) -> ProductionDesign:
    _notify(progress, "script", "脚本エージェントでビートを生成しています", 2, 9)
    script = ScreenwriterAgent(provider).run(brief, source_script)
    _notify(progress, "characters", "キャラクター設計エージェントで参照情報を整理しています", 3, 9)
    characters = CharacterAgent(provider).run(brief, script, rag)
    _notify(progress, "scenes", "シーン設計エージェントで場面構成を作っています", 4, 9)
    scenes = ScenePlannerAgent(provider).run(brief, script, characters, rag)
    _notify(progress, "shots", "ショット設計エージェントでカメラと構図を作っています", 5, 9)
    shots = ShotDirectorAgent(provider).run(brief, scenes, characters, rag)
    _notify(progress, "prompts", "プロンプト設計エージェントで画像・動画プロンプトを作っています", 6, 9)
    prompts = PromptEngineerAgent(provider).run(brief, shots, rag)

    _notify(progress, "design", "制作設計データを統合しています", 7, 9)
    design = ProductionDesign(
        brief=brief,
        script=script.items,
        characters=characters.items,
        scenes=scenes.items,
        shots=shots.items,
        image_prompts=prompts.image_prompts,
        video_prompts=prompts.video_prompts,
        rag_trace=rag.trace,
        learning_notes=_learning_notes(generate_images=generate_images, output_mode=brief.output_mode),
    )
    _notify(progress, "critic", "継続性評価エージェントで矛盾を確認しています", 8, 9)
    report = ContinuityCriticAgent(provider).run(design, rag)
    design.continuity_issues = report.issues
    if report.issues:
        revision = RevisionAgent(provider).run(design, rag)
        design.learning_notes.extend(f"修正ループ: {note}" for note in revision.notes)

    if generate_images:
        _notify(progress, "images", "画像生成Providerで参考画像を生成しています", 9, 9)
        design.generated_images = ImageGenerationAgent(provider).run(
            design,
            paths.images,
            rag,
            image_model=image_model,
            max_images=max_images,
            delay_seconds=image_delay_seconds,
        )

    _notify(progress, "write", "MarkdownとJSON成果物を書き出しています", 9, 9)
    design.rag_trace = rag.trace
    rag.save()
    write_all_outputs(design, paths.root)
    return design


def _notify(progress: ProgressCallback | None, stage: str, message: str, current: int, total: int) -> None:
    if progress is not None:
        progress(stage, message, current, total)


def _learning_notes(*, generate_images: bool, output_mode: str = "standard") -> list[str]:
    notes = [
        "Gemini Provider: モデル呼び出しをProvider層に閉じ込め、将来の差し替えを容易にしています。",
        "構造化出力: 各エージェントの返答をPydanticで検証できるデータにしています。",
        "エージェント設計: 企画、脚本、キャラクター、シーン、ショット、プロンプト、評価、修正を分離しています。",
        "RAG: キャラクター、ショット、プロンプト、画像メタデータを検索し、継続性維持に使います。",
        "評価と改善: 継続性評価エージェントで最終出力前に問題点を確認します。",
    ]
    if generate_images:
        notes.append("マルチモーダル生成: 画像プロンプトを画像生成Providerへ渡しました。")
    else:
        notes.append("マルチモーダル生成: 画像生成はスキップし、画像プロンプトだけを作成しました。")
    if output_mode == "remotion":
        notes.append("Remotionモード: 静止画を連結し、字幕と読み上げ音声を重ねる編集動画を作りやすい設計に寄せています。")
    return notes
