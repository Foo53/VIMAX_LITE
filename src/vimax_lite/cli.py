from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vimax_lite.models import ProjectPaths
from vimax_lite.pipeline import (
    generate_images_for_existing_design,
    init_project,
    rebuild_mv_visual_design,
    revise_existing_design,
    run_idea_pipeline,
    run_script_pipeline,
)
from vimax_lite.providers import ProviderError, make_provider
from vimax_lite.rag import RAGStore
from vimax_lite.timeline import build_timeline_manifest, render_timeline_with_remotion, write_timeline_manifest


def main(argv: list[str] | None = None) -> None:
    _load_dotenv_if_available()
    parser = argparse.ArgumentParser(prog="vimax-lite")
    parser.add_argument("--output-root", default="outputs")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init")
    init_cmd.add_argument("--project", required=True)

    idea_cmd = sub.add_parser("idea2design")
    _add_common_generation_args(idea_cmd)
    idea_cmd.add_argument("--idea", required=True)

    script_cmd = sub.add_parser("script2design")
    _add_common_generation_args(script_cmd)
    script_group = script_cmd.add_mutually_exclusive_group(required=True)
    script_group.add_argument("--script")
    script_group.add_argument("--script-file")

    image_cmd = sub.add_parser("generate-images")
    _add_provider_args(image_cmd)
    image_cmd.add_argument("--project", required=True)
    image_cmd.add_argument("--max-images", type=int, default=1)
    image_cmd.add_argument("--image-delay-seconds", type=float, default=0.0)

    revise_cmd = sub.add_parser("revise")
    _add_provider_args(revise_cmd)
    revise_cmd.add_argument("--project", required=True)

    rebuild_mv_cmd = sub.add_parser("rebuild-mv-visuals")
    _add_provider_args(rebuild_mv_cmd)
    rebuild_mv_cmd.add_argument("--project", required=True)

    inspect_cmd = sub.add_parser("inspect-rag")
    inspect_cmd.add_argument("--project", required=True)

    timeline_cmd = sub.add_parser("timeline")
    timeline_cmd.add_argument("--project", required=True)
    timeline_cmd.add_argument("--fps", type=int, default=30)
    timeline_cmd.add_argument("--width", type=int, default=1920)
    timeline_cmd.add_argument("--height", type=int, default=1080)

    render_video_cmd = sub.add_parser("render-video")
    render_video_cmd.add_argument("--project", required=True)
    render_video_cmd.add_argument("--renderer", choices=["remotion"], default="remotion")

    web_cmd = sub.add_parser("web")
    web_cmd.add_argument("--host", default="127.0.0.1")
    web_cmd.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    output_root = Path(args.output_root)

    if args.command == "init":
        paths = ProjectPaths.for_project(args.project, output_root)
        init_project(paths)
        print(f"プロジェクトを初期化しました: {paths.root}")
        return

    if args.command == "idea2design":
        provider = make_provider(args.provider, args.model, args.image_model)
        try:
            design = run_idea_pipeline(
                idea=args.idea,
                project=args.project,
                provider=provider,
                output_root=output_root,
                audience=args.audience,
                style=args.style,
                duration_seconds=args.duration_seconds,
                output_mode=args.output_mode,
                genre=args.genre,
                mood=args.mood,
                color_tone=args.color_tone,
                narration_style=args.narration_style,
                target_platform=args.target_platform,
                generate_images=args.generate_images,
                image_model=args.image_model,
                max_images=args.max_images,
                image_delay_seconds=args.image_delay_seconds,
            )
        except ProviderError as exc:
            _print_provider_error(exc)
            return
        _print_done(args.project, output_root, design)
        return

    if args.command == "script2design":
        provider = make_provider(args.provider, args.model, args.image_model)
        script = args.script or Path(args.script_file).read_text(encoding="utf-8")
        try:
            design = run_script_pipeline(
                script=script,
                project=args.project,
                provider=provider,
                output_root=output_root,
                audience=args.audience,
                style=args.style,
                duration_seconds=args.duration_seconds,
                output_mode=args.output_mode,
                genre=args.genre,
                mood=args.mood,
                color_tone=args.color_tone,
                narration_style=args.narration_style,
                target_platform=args.target_platform,
                generate_images=args.generate_images,
                image_model=args.image_model,
                max_images=args.max_images,
                image_delay_seconds=args.image_delay_seconds,
            )
        except ProviderError as exc:
            _print_provider_error(exc)
            return
        _print_done(args.project, output_root, design)
        return

    if args.command == "generate-images":
        provider = make_provider(args.provider, args.model, args.image_model)
        try:
            design = generate_images_for_existing_design(
                project=args.project,
                provider=provider,
                output_root=output_root,
                image_model=args.image_model,
                max_images=args.max_images,
                image_delay_seconds=args.image_delay_seconds,
            )
        except ProviderError as exc:
            _print_provider_error(exc)
            return
        print(f"画像生成レコード数: {len(design.generated_images)}")
        return

    if args.command == "revise":
        provider = make_provider(args.provider, args.model, args.image_model)
        try:
            design = revise_existing_design(project=args.project, provider=provider, output_root=output_root)
        except ProviderError as exc:
            _print_provider_error(exc)
            return
        print(f"修正が完了しました。継続性指摘数: {len(design.continuity_issues)}")
        return

    if args.command == "rebuild-mv-visuals":
        provider = make_provider(args.provider, args.model, args.image_model)
        try:
            design = rebuild_mv_visual_design(project=args.project, provider=provider, output_root=output_root)
        except ProviderError as exc:
            _print_provider_error(exc)
            return
        print(f"MV映像設計を再生成しました: {len(design.shots)} shots")
        return

    if args.command == "inspect-rag":
        paths = ProjectPaths.for_project(args.project, output_root)
        rag = RAGStore(paths.rag_store)
        print(json.dumps({"records": [record.__dict__ for record in rag.records]}, ensure_ascii=False, indent=2))
        return

    if args.command == "timeline":
        manifest = build_timeline_manifest(
            project=args.project,
            output_root=output_root,
            fps=args.fps,
            width=args.width,
            height=args.height,
        )
        target = write_timeline_manifest(manifest, args.project, output_root)
        ready = sum(1 for shot in manifest.shots if shot.status == "ready")
        print(f"タイムラインを生成しました: {target}")
        print(f"使用可能画像: {ready}/{len(manifest.shots)}")
        return

    if args.command == "render-video":
        result = render_timeline_with_remotion(project=args.project, output_root=output_root, repo_root=Path.cwd())
        if result.status == "success":
            print(f"Remotion動画を生成しました: {result.output_path}")
        else:
            print("Remotion動画生成に失敗しました。outputs/<project>/videos/render_report.md を確認してください。", file=sys.stderr)
            print("依存関係が未導入の場合は remotion/ で npm install を実行してください。", file=sys.stderr)
        return

    if args.command == "web":
        from vimax_lite.web_app import run_web_app

        run_web_app(args.host, args.port, output_root)
        return


def _add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=["gemini", "claude", "mock"], default="mock")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--image-model", default="gemini-2.5-flash-image")


def _add_common_generation_args(parser: argparse.ArgumentParser) -> None:
    _add_provider_args(parser)
    parser.add_argument("--project", required=True)
    parser.add_argument("--audience", default="general")
    parser.add_argument("--style", default="cinematic")
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--output-mode", choices=["standard", "remotion", "mv"], default="standard")
    parser.add_argument("--genre", default="")
    parser.add_argument("--mood", default="")
    parser.add_argument("--color-tone", default="")
    parser.add_argument("--narration-style", default="")
    parser.add_argument("--target-platform", default="")
    parser.add_argument("--generate-images", action="store_true")
    parser.add_argument("--max-images", type=int, default=1)
    parser.add_argument("--image-delay-seconds", type=float, default=0.0)


def _print_done(project: str, output_root: Path, design) -> None:
    paths = ProjectPaths.for_project(project, output_root)
    print(f"制作設計を生成しました: {paths.design_json}")
    print(f"ショット数: {len(design.shots)} / 継続性指摘数: {len(design.continuity_issues)}")


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return
    load_dotenv()


def _print_provider_error(exc: ProviderError) -> None:
    print(f"エラー: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
