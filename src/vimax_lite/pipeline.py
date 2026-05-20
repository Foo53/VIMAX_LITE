from __future__ import annotations

import json
from pathlib import Path

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
    generate_images: bool,
    image_model: str,
    max_images: int | None = None,
    image_delay_seconds: float = 0.0,
) -> ProductionDesign:
    paths = ProjectPaths.for_project(project, output_root)
    init_project(paths)
    rag = RAGStore(paths.rag_store)
    brief = IdeationAgent(provider).run(idea, audience=audience, style=style, duration_seconds=duration_seconds)
    return _run_common(brief, None, provider, rag, paths, generate_images, image_model, max_images, image_delay_seconds)


def run_script_pipeline(
    *,
    script: str,
    project: str,
    provider: LLMProvider,
    output_root: Path,
    audience: str,
    style: str,
    duration_seconds: int,
    generate_images: bool,
    image_model: str,
    max_images: int | None = None,
    image_delay_seconds: float = 0.0,
) -> ProductionDesign:
    paths = ProjectPaths.for_project(project, output_root)
    init_project(paths)
    rag = RAGStore(paths.rag_store)
    brief = IdeationAgent(provider).run(script, audience=audience, style=style, duration_seconds=duration_seconds)
    return _run_common(brief, script, provider, rag, paths, generate_images, image_model, max_images, image_delay_seconds)


def generate_images_for_existing_design(
    *,
    project: str,
    provider: LLMProvider,
    output_root: Path,
    image_model: str,
    max_images: int | None = None,
    image_delay_seconds: float = 0.0,
) -> ProductionDesign:
    paths = ProjectPaths.for_project(project, output_root)
    design = ProductionDesign.model_validate_json(paths.design_json.read_text(encoding="utf-8"))
    rag = RAGStore(paths.rag_store)
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
) -> ProductionDesign:
    script = ScreenwriterAgent(provider).run(brief, source_script)
    characters = CharacterAgent(provider).run(brief, script, rag)
    scenes = ScenePlannerAgent(provider).run(brief, script, characters, rag)
    shots = ShotDirectorAgent(provider).run(brief, scenes, characters, rag)
    prompts = PromptEngineerAgent(provider).run(brief, shots, rag)

    design = ProductionDesign(
        brief=brief,
        script=script.items,
        characters=characters.items,
        scenes=scenes.items,
        shots=shots.items,
        image_prompts=prompts.image_prompts,
        video_prompts=prompts.video_prompts,
        rag_trace=rag.trace,
        learning_notes=_learning_notes(generate_images=generate_images),
    )
    report = ContinuityCriticAgent(provider).run(design, rag)
    design.continuity_issues = report.issues
    if report.issues:
        revision = RevisionAgent(provider).run(design, rag)
        design.learning_notes.extend(f"修正ループ: {note}" for note in revision.notes)

    if generate_images:
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


def _learning_notes(*, generate_images: bool) -> list[str]:
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
    return notes
