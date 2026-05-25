from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from vimax_lite.models import GeneratedImage, ProductionDesign, ProjectPaths
from vimax_lite.renderers import write_image_manifest


REFERENCE_POSES = ("front", "side", "back", "detail")
SDXL_REFERENCE_NEGATIVE_PROMPT = (
    "multiple characters, duplicate subject, multiple views, turnaround sheet, model sheet, "
    "contact sheet, grid, panels, visible text, caption, logo, watermark, distorted proportions, low quality"
)
SDXL_SHOT_NEGATIVE_PROMPT = (
    "duplicate subject, inconsistent character design, multiple views, split screen, grid, panels, "
    "visible text, caption, logo, watermark, distorted anatomy, distorted wheels, blurry, low quality"
)


def prepare_manual_image_workflow(project: str, output_root: Path = Path("outputs")) -> dict[str, Any]:
    paths = ProjectPaths.for_project(project, output_root)
    design = load_design(paths)
    references = build_character_reference_sheet(design)
    annotate_reference_uploads(references, paths)
    reference_plan = build_shot_reference_plan(design, paths)
    write_reference_outputs(paths, references, reference_plan)
    return {"references": references, "reference_plan": reference_plan}


def load_design(paths: ProjectPaths) -> ProductionDesign:
    return ProductionDesign.model_validate_json(paths.design_json.read_text(encoding="utf-8"))


def build_character_reference_sheet(design: ProductionDesign) -> dict[str, Any]:
    characters: list[dict[str, Any]] = []
    for character in design.characters:
        prompts = []
        role = english_or_fallback(character.role, "main character in the project")
        appearance = english_or_fallback(character.appearance, "use a clear, distinctive, production-ready character design based on the project concept")
        wardrobe = english_or_fallback(character.wardrobe, "keep the character's established costume, exterior materials, colors, and accessories consistent")
        personality = english_or_fallback(character.personality, "express the character's personality through posture, silhouette, and subtle facial or body cues")
        continuity_notes = english_list_or_fallback(
            character.continuity_notes,
            "maintain the same identity, silhouette, proportions, colors, costume, and material details across every reference view",
        )
        base_prompt = (
            f"Create exactly one single-view character reference image for {character.name}. "
            f"Role: {role}. "
            f"Appearance: {appearance}. "
            f"Wardrobe or exterior: {wardrobe}. "
            f"Personality cue: {personality}. "
            f"Continuity rules: {'; '.join(continuity_notes)}. "
            "Use a clean neutral background, one centered character only, one pose only, clear readable silhouette, "
            "consistent colors and materials, no scene action, no caption, no logo, no visible text, "
            "no turnaround sheet, no model sheet, no contact sheet, no grid, no panels, no multiple views, no extra poses, no duplicate characters. "
            "If any source metadata was non-English, interpret its meaning internally as precise visual English guidance."
        )
        for pose in REFERENCE_POSES:
            pose_instruction = reference_pose_instruction(pose)
            manual_prompt = f"{base_prompt} {pose_instruction} Generate only this single requested view in this image."
            prompts.append(
                {
                    "reference_id": f"character_{character.id}_{pose}",
                    "character_id": character.id,
                    "pose": pose,
                    "filename": f"character_{character.id}_{pose}.png",
                    "prompt": manual_prompt,
                    "sdxl_prompt": build_sdxl_reference_prompt(
                        character.name,
                        role,
                        appearance,
                        wardrobe,
                        personality,
                        continuity_notes,
                        pose,
                    ),
                    "sdxl_negative_prompt": SDXL_REFERENCE_NEGATIVE_PROMPT,
                }
            )
        characters.append({"character": character.model_dump(), "prompts": prompts})
    return {
        "title": f"{design.brief.title} キャラクター参照シート",
        "instruction": "最初にこの参照画像を作成し、以降のショット生成では必ず添付してください。",
        "characters": characters,
    }


def annotate_reference_uploads(references: dict[str, Any], paths: ProjectPaths) -> None:
    for item in references["characters"]:
        for prompt in item["prompts"]:
            reference_id = prompt["reference_id"]
            path = paths.root / "references" / f"{reference_id}.png"
            prompt["saved"] = path.exists()
            prompt["saved_path"] = f"references/{reference_id}.png" if path.exists() else None
            prompt["saved_mtime"] = str(int(path.stat().st_mtime)) if path.exists() else ""


def reference_pose_instruction(pose: str) -> str:
    if pose == "front":
        return "View: front view. Show exactly one full-body character facing the camera."
    if pose == "side":
        return "View: side profile. Show exactly one full-body character in a clean left-facing side view."
    if pose == "back":
        return "View: back view. Show exactly one full-body character facing away from the camera."
    if pose == "detail":
        return "View: detail reference. Show exactly one close-up crop focused on the most important design details, materials, colors, and distinctive features."
    return f"View: {pose}. Show exactly one character in one pose."


def build_sdxl_reference_prompt(
    name: str,
    role: str,
    appearance: str,
    wardrobe: str,
    personality: str,
    continuity_notes: list[str],
    pose: str,
) -> str:
    """SDXL向けに、参照画像ファイルの操作説明を含まない視覚プロンプトを作る。"""
    framing = {
        "front": "front view, full body, facing camera",
        "side": "clean left-facing side profile, full body",
        "back": "back view, full body, facing away from camera",
        "detail": "close-up detail view of distinctive materials and design features",
    }.get(pose, f"{pose} view, single pose")
    return (
        f"single character reference image, {framing}, {name}, {role}, {appearance}, {wardrobe}, "
        f"{personality}, {'; '.join(continuity_notes)}, clean neutral studio background, centered composition, "
        "clear silhouette, consistent materials and colors, production concept art, highly detailed"
    )


def english_or_fallback(text: str, fallback: str) -> str:
    cleaned = " ".join((text or "").split())
    if cleaned and is_english_prompt_text(cleaned):
        return cleaned
    return fallback


def english_list_or_fallback(values: list[str], fallback: str) -> list[str]:
    english_values = [english_or_fallback(value, "") for value in values]
    english_values = [value for value in english_values if value]
    return english_values or [fallback]


def is_english_prompt_text(text: str) -> bool:
    if not text:
        return False
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    return ascii_chars / max(len(text), 1) >= 0.9


def build_shot_reference_plan(design: ProductionDesign, paths: ProjectPaths) -> dict[str, Any]:
    scene_characters = {scene.scene_id: scene.characters for scene in design.scenes}
    prompt_by_shot = {prompt.shot_id: prompt for prompt in design.image_prompts}
    shots: list[dict[str, Any]] = []
    previous_shot_file: str | None = None
    for shot in sorted(design.shots, key=lambda item: item.order):
        character_refs = []
        for character_id in scene_characters.get(shot.scene_id, []):
            character_refs.append(f"references/character_{character_id}_front.png")
            character_refs.append(f"references/character_{character_id}_side.png")
        required_refs = list(dict.fromkeys(character_refs))
        if previous_shot_file:
            required_refs.append(previous_shot_file)
        image_prompt = prompt_by_shot.get(shot.shot_id)
        visual_prompt = build_shot_visual_prompt(shot, image_prompt.prompt if image_prompt else "")
        manual_prompt = build_manual_prompt(shot.shot_id, visual_prompt, required_refs)
        sdxl_prompt = build_sdxl_shot_prompt(visual_prompt, image_prompt.style_tags if image_prompt else [])
        sdxl_negative_prompt = build_sdxl_negative_prompt(image_prompt.negative_prompt if image_prompt else "")
        output_file = f"images/manual/{shot.shot_id}.png"
        output_path = paths.root / output_file
        shots.append(
            {
                "shot_id": shot.shot_id,
                "scene_id": shot.scene_id,
                "order": shot.order,
                "description": shot.description,
                "required_references": required_refs,
                "reference_assets": build_reference_assets(paths, required_refs),
                "output_file": output_file,
                "output_saved_path": output_file if output_path.exists() else None,
                "output_saved_mtime": str(int(output_path.stat().st_mtime)) if output_path.exists() else "",
                "manual_prompt": manual_prompt,
                "sdxl_prompt": sdxl_prompt,
                "sdxl_negative_prompt": sdxl_negative_prompt,
                "status": image_status(paths, shot.shot_id),
            }
        )
        previous_shot_file = output_file
    total = len(shots)
    done = sum(1 for shot in shots if shot["status"] == "generated")
    return {"total": total, "generated": done, "remaining": total - done, "shots": shots}


def build_shot_visual_prompt(shot, image_prompt: str) -> str:
    prompt = english_or_fallback(image_prompt, "")
    if not prompt:
        prompt = (
            "Create a cinematic still image for this shot based on the structured shot design. "
            "Translate any non-English shot notes internally into precise visual English. "
            f"Shot description: {shot.description}. "
            f"Camera: {shot.camera}. Lens: {shot.lens}. Lighting: {shot.lighting}. "
            f"First-frame intent: {shot.first_frame}. Last-frame intent: {shot.last_frame}."
        )
    return prompt


def build_sdxl_shot_prompt(visual_prompt: str, style_tags: list[str]) -> str:
    """SDXL向けに、参照の添付手順ではなく描画内容だけを渡すプロンプトを作る。"""
    styles = ", ".join(tag for tag in style_tags if tag)
    style_clause = f", {styles}" if styles else ""
    return (
        f"{visual_prompt} Cinematic production still, one coherent frame, consistent subject identity and wardrobe, "
        f"detailed environment, controlled composition, high quality{style_clause}."
    )


def build_sdxl_negative_prompt(image_negative_prompt: str) -> str:
    """エージェント設計の禁止条件をSDXLの共通negative promptへ統合する。"""
    additional = english_or_fallback(image_negative_prompt, "")
    if additional:
        return f"{SDXL_SHOT_NEGATIVE_PROMPT}, {additional}"
    return SDXL_SHOT_NEGATIVE_PROMPT


def build_reference_assets(paths: ProjectPaths, required_refs: list[str]) -> list[dict[str, Any]]:
    assets = []
    for index, ref in enumerate(required_refs):
        path = paths.root / ref
        assets.append(
            {
                "index": index,
                "path": ref,
                "exists": path.exists(),
                "mtime": str(int(path.stat().st_mtime)) if path.exists() else "",
                "role": describe_reference_role(ref),
            }
        )
    return assets


def build_manual_prompt(shot_id: str, image_prompt: str, required_refs: list[str]) -> str:
    ref_lines = build_reference_instruction_lines(required_refs)
    refs = "\n".join(ref_lines) if ref_lines else "- No reference image is attached for this shot."
    return f"""Generate one production-quality still image for the following shot.

Shot ID: {shot_id}

Required reference images to attach:
{refs}

Reference usage rules:
- Keep the character identity, proportions, materials, colors, costume, and distinctive features consistent with the attached character reference images.
- If a previous shot image is attached, use it for continuity of environment, lighting, weather, spatial layout, character state, and overall visual tone.
- Do not redesign the character, costume, environment, color palette, or story world unless the shot prompt explicitly requires it.
- Use the attached references as visual anchors, but compose a new finished image for this exact shot.
- Generate a single final cinematic still image.
- Do not copy the reference images as a reference sheet. Do not show multiple views, multiple poses, duplicate characters, grids, panels, turnarounds, contact sheets, labels, captions, logos, watermarks, or visible text.
- If the shot prompt contains non-English text, translate and interpret it internally as precise visual English before generating.

Shot prompt:
{image_prompt}
"""


def build_reference_instruction_lines(required_refs: list[str]) -> list[str]:
    lines = []
    for index, ref in enumerate(required_refs):
        role = describe_reference_role(ref)
        lines.append(f"- Image {index}: `{ref}`. {role}")
    return lines


def describe_reference_role(ref: str) -> str:
    if ref.startswith("references/character_"):
        if ref.endswith("_front.png"):
            return "Use this as the primary character design reference for face, body shape, costume, colors, and materials."
        if ref.endswith("_side.png"):
            return "Use this to preserve the character silhouette, side profile, proportions, costume, and material continuity."
        if ref.endswith("_back.png"):
            return "Use this to preserve the character's back view, silhouette, costume, and material continuity."
        if ref.endswith("_detail.png"):
            return "Use this to preserve close-up design details, textures, colors, and distinctive features."
        return "Use this as a character consistency reference."
    if ref.startswith("images/manual/"):
        return "Use this previous generated shot as the temporal continuity reference for lighting, environment, camera feel, atmosphere, and story state."
    return "Use this as a visual continuity reference."


def write_reference_outputs(paths: ProjectPaths, references: dict[str, Any], reference_plan: dict[str, Any]) -> None:
    references_dir = paths.root / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    (references_dir / "character_reference_sheet.json").write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding="utf-8")
    (references_dir / "character_reference_sheet.md").write_text(render_character_reference_sheet(references), encoding="utf-8")
    (paths.root / "reference_plan.json").write_text(json.dumps(reference_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (paths.root / "reference_plan.md").write_text(render_reference_plan(reference_plan), encoding="utf-8")
    (paths.root / "manual_generation_guide.md").write_text(render_manual_generation_guide(references, reference_plan), encoding="utf-8")
    (paths.root / "sdxl_generation_guide.md").write_text(render_sdxl_generation_guide(references, reference_plan), encoding="utf-8")


def render_character_reference_sheet(references: dict[str, Any]) -> str:
    lines = [f"# {references['title']}", "", references["instruction"], ""]
    for item in references["characters"]:
        character = item["character"]
        lines.extend([f"## {character['name']}", ""])
        for prompt in item["prompts"]:
            lines.extend([f"### {prompt['reference_id']}", f"保存名: `{prompt['filename']}`", "", prompt["prompt"], ""])
    return "\n".join(lines)


def render_reference_plan(reference_plan: dict[str, Any]) -> str:
    lines = [
        "# ショット参照画像計画",
        "",
        f"- 総ショット数: {reference_plan['total']}",
        f"- 生成済み: {reference_plan['generated']}",
        f"- 残り: {reference_plan['remaining']}",
        "",
    ]
    for shot in reference_plan["shots"]:
        refs = ", ".join(shot["required_references"]) if shot["required_references"] else "なし"
        lines.extend([f"## {shot['shot_id']}", f"- 状態: {shot['status']}", f"- 添付参照画像: {refs}", f"- 保存先: `{shot['output_file']}`", ""])
    return "\n".join(lines)


def render_manual_generation_guide(references: dict[str, Any], reference_plan: dict[str, Any]) -> str:
    lines = [
        "# ChatGPT手作業画像生成ガイド",
        "",
        "## 1. キャラクター参照画像を先に生成",
        "",
        "以下の参照画像を生成し、Web UIからアップロードしてください。",
        "",
    ]
    for item in references["characters"]:
        for prompt in item["prompts"]:
            lines.extend([f"### {prompt['reference_id']}", prompt["prompt"], ""])
    lines.extend(["## 2. ショット画像を順番に生成", ""])
    for shot in reference_plan["shots"]:
        lines.extend([f"### {shot['shot_id']}", shot["manual_prompt"], f"保存先: `{shot['output_file']}`", ""])
    return "\n".join(lines)


def render_sdxl_generation_guide(references: dict[str, Any], reference_plan: dict[str, Any]) -> str:
    lines = [
        "# SDXL + IP-Adapter 候補画像生成ガイド",
        "",
        "このプロンプトはローカルSDXL用です。参照画像ファイルは文章ではなく、Web UIからIP-Adapter条件として渡されます。",
        "",
        "## 1. キャラクター参照画像",
        "",
    ]
    for item in references["characters"]:
        for prompt in item["prompts"]:
            lines.extend(
                [
                    f"### {prompt['reference_id']}",
                    "",
                    "Positive Prompt:",
                    "",
                    prompt["sdxl_prompt"],
                    "",
                    "Negative Prompt:",
                    "",
                    prompt["sdxl_negative_prompt"],
                    "",
                ]
            )
    lines.extend(["## 2. ショット画像", ""])
    for shot in reference_plan["shots"]:
        lines.extend(
            [
                f"### {shot['shot_id']}",
                "",
                "Positive Prompt:",
                "",
                shot["sdxl_prompt"],
                "",
                "Negative Prompt:",
                "",
                shot["sdxl_negative_prompt"],
                "",
            ]
        )
    return "\n".join(lines)


def image_status(paths: ProjectPaths, image_id: str) -> str:
    manual_path = paths.root / "images" / "manual" / f"{image_id}.png"
    return "generated" if manual_path.exists() else "not_started"


def image_counts(project: str, output_root: Path = Path("outputs")) -> dict[str, int]:
    paths = ProjectPaths.for_project(project, output_root)
    if not paths.design_json.exists():
        return {"total": 0, "generated": 0, "remaining": 0}
    design = load_design(paths)
    total = len(design.image_prompts)
    generated = sum(1 for prompt in design.image_prompts if image_status(paths, prompt.shot_id) == "generated")
    return {"total": total, "generated": generated, "remaining": total - generated}


def register_uploaded_image(
    project: str,
    image_id: str,
    source_path: Path,
    *,
    output_root: Path = Path("outputs"),
    kind: str = "shot",
    model: str = "manual-chatgpt",
    prompt: str = "Web UIからアップロードされた手作業生成画像",
) -> Path:
    paths = ProjectPaths.for_project(project, output_root)
    target_dir = paths.root / ("references" if kind == "reference" else "images/manual")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{image_id}.png"
    shutil.copyfile(source_path, target_path)

    images = read_image_manifest(paths.image_manifest)
    images = [image for image in images if image.shot_id != image_id]
    images.append(
        GeneratedImage(
            shot_id=image_id,
            path=str(target_path),
            model=model,
            prompt=prompt,
            status="success",
        )
    )
    write_image_manifest(images, paths.image_manifest)
    return target_path


def register_uploaded_file_bytes(project: str, image_id: str, data: bytes, *, output_root: Path = Path("outputs"), kind: str = "shot") -> Path:
    paths = ProjectPaths.for_project(project, output_root)
    target_dir = paths.root / ("references" if kind == "reference" else "images/manual")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{image_id}.png"
    target_path.write_bytes(data)

    images = read_image_manifest(paths.image_manifest)
    images = [image for image in images if image.shot_id != image_id]
    images.append(
        GeneratedImage(
            shot_id=image_id,
            path=str(target_path),
            model="manual-chatgpt",
            prompt="Web UIからアップロードされた手作業生成画像",
            status="success",
        )
    )
    write_image_manifest(images, paths.image_manifest)
    return target_path


def read_image_manifest(path: Path) -> list[GeneratedImage]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [GeneratedImage.model_validate(item) for item in data.get("images", [])]
