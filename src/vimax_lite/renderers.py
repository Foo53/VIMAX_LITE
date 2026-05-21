from __future__ import annotations

import json
from pathlib import Path

from vimax_lite.models import GeneratedImage, ProductionDesign


def write_all_outputs(design: ProductionDesign, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "design.json").write_text(design.model_dump_json(indent=2), encoding="utf-8")
    (root / "design.md").write_text(render_design(design), encoding="utf-8")
    (root / "storyboard.md").write_text(render_storyboard(design), encoding="utf-8")
    (root / "image_prompts.md").write_text(render_image_prompts(design), encoding="utf-8")
    (root / "video_prompts.md").write_text(render_video_prompts(design), encoding="utf-8")
    (root / "continuity_report.md").write_text(render_continuity(design), encoding="utf-8")
    (root / "rag_trace.md").write_text(render_rag_trace(design), encoding="utf-8")
    (root / "learning_notes.md").write_text(render_learning_notes(design), encoding="utf-8")
    write_image_manifest(design.generated_images, root / "images" / "image_manifest.json")


def write_image_manifest(images: list[GeneratedImage], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"images": [image.model_dump() for image in images]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_design(design: ProductionDesign) -> str:
    lines = [
        f"# {design.brief.title}",
        "",
        "## ログライン",
        design.brief.logline,
        "",
        "## 制作ブリーフ",
        f"- 想定視聴者: {design.brief.audience}",
        f"- 映像スタイル: {design.brief.style}",
        f"- 想定尺: {design.brief.duration_seconds}秒",
        f"- 出力モード: {design.brief.output_mode}",
        f"- テーマ: {', '.join(design.brief.themes)}",
        "",
        "## キャラクター",
    ]
    for character in design.characters:
        lines.extend(
            [
                f"### {character.name}",
                f"- 役割: {character.role}",
                f"- 性格: {character.personality}",
                f"- 外見: {character.appearance}",
                f"- 衣装: {character.wardrobe}",
                f"- 継続性メモ: {'; '.join(character.continuity_notes)}",
                "",
            ]
        )
    lines.append("## シーン")
    for scene in design.scenes:
        lines.extend(
            [
                f"### {scene.scene_id}: {scene.title}",
                f"- 場所: {scene.location}",
                f"- 時間帯: {scene.time_of_day}",
                f"- 概要: {scene.summary}",
                f"- 登場人物: {', '.join(scene.characters)}",
                "",
            ]
        )
    return "\n".join(lines)


def render_storyboard(design: ProductionDesign) -> str:
    lines = ["# 絵コンテ", ""]
    for shot in design.shots:
        lines.extend(
            [
                f"## {shot.shot_id}",
                f"- シーン: {shot.scene_id}",
                f"- 内容: {shot.description}",
                f"- カメラ: {shot.camera}",
                f"- レンズ: {shot.lens}",
                f"- 動き: {shot.motion}",
                f"- First frame: {shot.first_frame}",
                f"- Last frame: {shot.last_frame}",
                f"- 照明: {shot.lighting}",
                f"- 音: {shot.audio}",
                "",
            ]
        )
    return "\n".join(lines)


def render_image_prompts(design: ProductionDesign) -> str:
    lines = ["# 画像生成プロンプト", ""]
    for prompt in design.image_prompts:
        lines.extend(
            [
                f"## {prompt.shot_id}",
                prompt.prompt,
                "",
                f"ネガティブプロンプト: {prompt.negative_prompt}",
                f"アスペクト比: {prompt.aspect_ratio}",
                "",
            ]
        )
    return "\n".join(lines)


def render_video_prompts(design: ProductionDesign) -> str:
    lines = ["# 動画生成プロンプト", ""]
    for prompt in design.video_prompts:
        lines.extend(
            [
                f"## {prompt.shot_id}",
                prompt.prompt,
                "",
                f"尺: {prompt.duration_seconds}秒",
                f"カメラ移動: {prompt.camera_motion}",
                f"時間変化メモ: {prompt.temporal_notes}",
                "",
            ]
        )
    return "\n".join(lines)


def render_continuity(design: ProductionDesign) -> str:
    lines = ["# 継続性レポート", ""]
    if not design.continuity_issues:
        lines.append("継続性の問題は検出されませんでした。")
        return "\n".join(lines)
    for issue in design.continuity_issues:
        lines.extend(
            [
                f"## {issue.severity.upper()} - {issue.location}",
                issue.issue,
                "",
                f"修正提案: {issue.recommendation}",
                "",
            ]
        )
    return "\n".join(lines)


def render_rag_trace(design: ProductionDesign) -> str:
    lines = ["# RAG参照履歴", ""]
    for item in design.rag_trace:
        lines.extend(
            [
                f"## {item.used_by}",
                f"検索クエリ: {item.query}",
                f"参照結果: {', '.join(item.results) if item.results else 'なし'}",
                "",
            ]
        )
    return "\n".join(lines)


def render_learning_notes(design: ProductionDesign) -> str:
    lines = [
        "# 学習メモ",
        "",
        "この実行では、次の生成AIエンジニアリング要素を確認できます。",
        "",
    ]
    for note in design.learning_notes:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"
