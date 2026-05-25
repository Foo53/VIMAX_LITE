from __future__ import annotations

import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from vimax_lite.manual_workflow import (
    build_shot_reference_plan,
    image_counts,
    load_design,
    prepare_manual_image_workflow,
    read_image_manifest,
    register_uploaded_file_bytes,
    register_uploaded_image,
)
from vimax_lite.models import GeneratedImage, ProductionDesign, ProjectPaths, SunoMusicParams
from vimax_lite.renderers import write_image_manifest
from vimax_lite.pipeline import rebuild_mv_visual_design, run_idea_pipeline
from vimax_lite.providers import ProviderError, make_provider
from vimax_lite.timeline import build_timeline_manifest, render_timeline_with_remotion, write_timeline_manifest


@dataclass
class JobState:
    id: str
    project: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "待機中です"
    current: int = 0
    total: int = 1
    error: str | None = None
    result_url: str | None = None
    events: list[str] = field(default_factory=list)

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return min(100, int(self.current / self.total * 100))


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobState] = {}

    def create(self, project: str) -> JobState:
        job = JobState(id=str(uuid.uuid4()), project=project)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> JobState:
        with self._lock:
            return self._jobs[job_id]

    def update(self, job_id: str, **kwargs: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in kwargs.items():
                setattr(job, key, value)
            if "message" in kwargs:
                job.events.append(str(kwargs["message"]))


jobs = JobStore()


AUDIENCE_OPTIONS = [
    {"value": "general", "label": "一般視聴者"},
    {"value": "children", "label": "子ども向け"},
    {"value": "young_adults", "label": "若年層・SNS向け"},
    {"value": "film_fans", "label": "映画好き・映像表現重視"},
    {"value": "tech_portfolio", "label": "採用担当・技術ポートフォリオ向け"},
]


MODEL_OPTIONS = [
    {"value": "mock-fixed", "label": "Mock 固定応答（APIなし）", "provider": "mock"},
    {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "provider": "gemini"},
    {"value": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "provider": "gemini"},
    {"value": "gemini-2.0-flash", "label": "Gemini 2.0 Flash", "provider": "gemini"},
    {"value": "claude-sonnet-4.5", "label": "Claude Sonnet 4.5（将来対応枠）", "provider": "claude"},
    {"value": "openai-gpt-5.1", "label": "OpenAI GPT-5.1（将来対応枠）", "provider": "openai"},
    {"value": "minimax-m2.7", "label": "MiniMax M2.7（将来対応枠）", "provider": "minimax"},
]


DURATION_PRESETS = [15, 30, 45, 60, 90, 120, 180, 300]


OUTPUT_MODE_OPTIONS = [
    {"value": "standard", "label": "標準: 動画生成API向け設計"},
    {"value": "remotion", "label": "Remotion: 画像連結 + 字幕 + 読み上げ向け"},
    {"value": "mv", "label": "MV: Suno音楽生成 + 歌詞字幕付き動画"},
]

GENRE_OPTIONS = [
    {"value": "", "label": "指定しない"},
    {"value": "fantasy", "label": "ファンタジー"},
    {"value": "slice_of_life", "label": "日常系"},
    {"value": "documentary", "label": "ドキュメンタリー"},
    {"value": "corporate", "label": "企業・PR"},
    {"value": "horror", "label": "ホラー・サスペンス"},
    {"value": "comedy", "label": "コメディ"},
    {"value": "poetic", "label": "詩的・実験的"},
]

MOOD_OPTIONS = [
    {"value": "", "label": "指定しない"},
    {"value": "bright", "label": "明るい・希望"},
    {"value": "dark", "label": "暗い・重厚"},
    {"value": "nostalgic", "label": "ノスタルジック"},
    {"value": "energetic", "label": "エネルギッシュ"},
    {"value": "calm", "label": "穏やか・静謐"},
    {"value": "mysterious", "label": "神秘的"},
    {"value": "whimsical", "label": "ゆかい・不思議"},
]

COLOR_TONE_OPTIONS = [
    {"value": "", "label": "指定しない"},
    {"value": "warm", "label": "暖色系"},
    {"value": "cool", "label": "寒色系"},
    {"value": "monochrome", "label": "モノクロ"},
    {"value": "vivid", "label": "ビビッド"},
    {"value": "pastel", "label": "パステル"},
    {"value": "muted", "label": "くすみ・アンティーク"},
]

NARRATION_STYLE_OPTIONS = [
    {"value": "", "label": "絵本風（デフォルト）"},
    {"value": "third_person", "label": "三人称ナレーション"},
    {"value": "first_person", "label": "一人称（主人公の語り）"},
    {"value": "dialogue", "label": "セリフ中心"},
    {"value": "none", "label": "字幕なし"},
]

TARGET_PLATFORM_OPTIONS = [
    {"value": "", "label": "指定しない（16:9）"},
    {"value": "youtube", "label": "YouTube 横長（16:9）"},
    {"value": "tiktok", "label": "TikTok 縦長（9:16）"},
    {"value": "instagram_square", "label": "Instagram 正方形（1:1）"},
    {"value": "instagram_reel", "label": "Instagram Reel（9:16）"},
    {"value": "twitter", "label": "X/Twitter（16:9）"},
]

STYLE_OPTIONS = [
    {"value": "cinematic", "label": "シネマティック"},
    {"value": "anime", "label": "アニメ"},
    {"value": "watercolor", "label": "水彩画風"},
    {"value": "oil_painting", "label": "油絵風"},
    {"value": "pixel_art", "label": "ピクセルアート"},
    {"value": "photorealistic", "label": "フォトリアル"},
    {"value": "flat_design", "label": "フラットデザイン"},
    {"value": "3d_render", "label": "3Dレンダー"},
    {"value": "stop_motion", "label": "ストップモーション風"},
    {"value": "minimal", "label": "ミニマル"},
    {"value": "retro", "label": "レトロ・ノスタルジー"},
    {"value": "cyberpunk", "label": "サイバーパンク"},
    {"value": "studio_ghibli", "label": "ジブリ風"},
    {"value": "manga", "label": "漫画風"},
]


def create_app(output_root: Path = Path("outputs")) -> FastAPI:
    app = FastAPI(title="ViMax Lite Web UI")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    output_root.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=str(output_root)), name="files")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        projects = sorted(path.name for path in output_root.iterdir() if (path / "design.json").exists())
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "projects": projects,
                "audience_options": AUDIENCE_OPTIONS,
                "model_options": MODEL_OPTIONS,
                "duration_presets": DURATION_PRESETS,
                "output_mode_options": OUTPUT_MODE_OPTIONS,
                "genre_options": GENRE_OPTIONS,
                "mood_options": MOOD_OPTIONS,
                "color_tone_options": COLOR_TONE_OPTIONS,
                "narration_style_options": NARRATION_STYLE_OPTIONS,
                "target_platform_options": TARGET_PLATFORM_OPTIONS,
                "style_options": STYLE_OPTIONS,
            },
        )

    @app.post("/projects/generate")
    def generate_project(
        project: str = Form(...),
        idea: str = Form(...),
        audience: str = Form("general"),
        style: str = Form("cinematic"),
        duration_seconds: int = Form(60),
        output_mode: str = Form("standard"),
        genre: str = Form(""),
        mood: str = Form(""),
        color_tone: str = Form(""),
        narration_style: str = Form(""),
        target_platform: str = Form(""),
        provider: str = Form("mock"),
        model: str = Form("gemini-2.5-flash"),
    ) -> RedirectResponse:
        job = jobs.create(project)
        thread = threading.Thread(
            target=_run_generation_job,
            kwargs={
                "job_id": job.id,
                "project": project,
                "idea": idea,
                "audience": audience,
                "style": style,
                "duration_seconds": duration_seconds,
                "output_mode": output_mode,
                "genre": genre,
                "mood": mood,
                "color_tone": color_tone,
                "narration_style": narration_style,
                "target_platform": target_platform,
                "provider_name": provider,
                "model": model,
                "output_root": output_root,
            },
            daemon=True,
        )
        thread.start()
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str) -> HTMLResponse:
        return templates.TemplateResponse(request, "job.html", {"job": jobs.get(job_id)})

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        return {
            "id": job.id,
            "project": job.project,
            "status": job.status,
            "stage": job.stage,
            "message": job.message,
            "current": job.current,
            "total": job.total,
            "percent": job.percent,
            "error": job.error,
            "result_url": job.result_url,
            "events": job.events[-8:],
        }

    @app.get("/projects/{project}", response_class=HTMLResponse)
    def project_page(request: Request, project: str) -> HTMLResponse:
        paths = ProjectPaths.for_project(project, output_root)
        design = load_design(paths)
        counts = image_counts(project, output_root)
        workflow = prepare_manual_image_workflow(project, output_root)
        timeline_path = paths.root / "timeline_manifest.json"
        video_path = paths.root / "videos" / "assembled_video.mp4"
        return templates.TemplateResponse(
            request,
            "project.html",
            {
                "project": project,
                "design": design,
                "counts": counts,
                "workflow": workflow,
                "timeline_exists": timeline_path.exists(),
                "video_exists": video_path.exists(),
                "is_mv": design.brief.output_mode == "mv",
            },
        )

    @app.post("/projects/{project}/timeline")
    def create_timeline(project: str) -> RedirectResponse:
        manifest = build_timeline_manifest(project=project, output_root=output_root)
        write_timeline_manifest(manifest, project, output_root)
        return RedirectResponse(f"/projects/{project}", status_code=303)

    @app.post("/projects/{project}/render-video")
    def render_video(project: str) -> RedirectResponse:
        job = jobs.create(project)
        thread = threading.Thread(
            target=_run_render_job,
            kwargs={
                "job_id": job.id,
                "project": project,
                "output_root": output_root,
                "repo_root": Path.cwd(),
            },
            daemon=True,
        )
        thread.start()
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.get("/projects/{project}/shots", response_class=HTMLResponse)
    def shots_page(request: Request, project: str) -> HTMLResponse:
        paths = ProjectPaths.for_project(project, output_root)
        design = load_design(paths)
        reference_plan = build_shot_reference_plan(design, paths)
        counts = image_counts(project, output_root)
        return templates.TemplateResponse(
            request,
            "shots.html",
            {"project": project, "design": design, "reference_plan": reference_plan, "counts": counts},
        )

    @app.post("/projects/{project}/shots/{shot_id}/upload")
    async def upload_shot_image(project: str, shot_id: str, file: UploadFile = File(...)) -> RedirectResponse:
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp.write(await file.read())
            temp_path = Path(temp.name)
        register_uploaded_image(project, shot_id, temp_path, output_root=output_root, kind="shot")
        temp_path.unlink(missing_ok=True)
        prepare_manual_image_workflow(project, output_root)
        return RedirectResponse(f"/projects/{project}/shots#shot-{shot_id}", status_code=303)

    @app.post("/projects/{project}/shots/{shot_id}/generate")
    def generate_shot_image(project: str, shot_id: str) -> RedirectResponse:
        paths = ProjectPaths.for_project(project, output_root)
        design = load_design(paths)
        reference_plan = build_shot_reference_plan(design, paths)
        shot = next((s for s in reference_plan["shots"] if s["shot_id"] == shot_id), None)
        if not shot:
            return RedirectResponse(f"/projects/{project}/shots", status_code=303)
        job = jobs.create(project)
        thread = threading.Thread(
            target=_run_sdxl_job,
            kwargs={
                "job_id": job.id,
                "project": project,
                "items": [{"id": shot_id, "prompt": shot["manual_prompt"], "kind": "shot"}],
                "return_page": f"/projects/{project}/shots#shot-{shot_id}",
                "output_root": output_root,
            },
            daemon=True,
        )
        thread.start()
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.post("/projects/{project}/shots/generate-all")
    def generate_all_shots(project: str) -> RedirectResponse:
        paths = ProjectPaths.for_project(project, output_root)
        design = load_design(paths)
        reference_plan = build_shot_reference_plan(design, paths)
        items = [
            {"id": s["shot_id"], "prompt": s["manual_prompt"], "kind": "shot"}
            for s in reference_plan["shots"]
            if s["status"] != "generated"
        ]
        if not items:
            return RedirectResponse(f"/projects/{project}/shots", status_code=303)
        job = jobs.create(project)
        thread = threading.Thread(
            target=_run_sdxl_job,
            kwargs={
                "job_id": job.id,
                "project": project,
                "items": items,
                "return_page": f"/projects/{project}/shots",
                "output_root": output_root,
            },
            daemon=True,
        )
        thread.start()
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.get("/projects/{project}/references", response_class=HTMLResponse)
    def references_page(request: Request, project: str) -> HTMLResponse:
        workflow = prepare_manual_image_workflow(project, output_root)
        return templates.TemplateResponse(request, "references.html", {"project": project, "workflow": workflow})

    @app.post("/projects/{project}/references/{reference_id}/upload")
    async def upload_reference_image(project: str, reference_id: str, file: UploadFile = File(...)) -> RedirectResponse:
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp.write(await file.read())
            temp_path = Path(temp.name)
        register_uploaded_image(project, reference_id, temp_path, output_root=output_root, kind="reference")
        temp_path.unlink(missing_ok=True)
        prepare_manual_image_workflow(project, output_root)
        return RedirectResponse(f"/projects/{project}/references#ref-{reference_id}", status_code=303)

    @app.post("/projects/{project}/references/{reference_id}/generate")
    def generate_reference_image(project: str, reference_id: str) -> RedirectResponse:
        workflow = prepare_manual_image_workflow(project, output_root)
        prompt_text = None
        for item in workflow["references"]["characters"]:
            for p in item["prompts"]:
                if p["reference_id"] == reference_id:
                    prompt_text = p["prompt"]
                    break
        if not prompt_text:
            return RedirectResponse(f"/projects/{project}/references", status_code=303)
        job = jobs.create(project)
        thread = threading.Thread(
            target=_run_sdxl_job,
            kwargs={
                "job_id": job.id,
                "project": project,
                "items": [{"id": reference_id, "prompt": prompt_text, "kind": "reference"}],
                "return_page": f"/projects/{project}/references#ref-{reference_id}",
                "output_root": output_root,
            },
            daemon=True,
        )
        thread.start()
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.post("/projects/{project}/references/generate-all")
    def generate_all_references(project: str) -> RedirectResponse:
        workflow = prepare_manual_image_workflow(project, output_root)
        items = []
        for item in workflow["references"]["characters"]:
            for p in item["prompts"]:
                if not p["saved"]:
                    items.append({"id": p["reference_id"], "prompt": p["prompt"], "kind": "reference"})
        if not items:
            return RedirectResponse(f"/projects/{project}/references", status_code=303)
        job = jobs.create(project)
        thread = threading.Thread(
            target=_run_sdxl_job,
            kwargs={
                "job_id": job.id,
                "project": project,
                "items": items,
                "return_page": f"/projects/{project}/references",
                "output_root": output_root,
            },
            daemon=True,
        )
        thread.start()
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.post("/projects/{project}/references/upload-batch")
    async def upload_reference_images_batch(request: Request, project: str) -> RedirectResponse:
        form = await request.form()
        for key, value in form.multi_items():
            if not key.startswith("reference_file__"):
                continue
            if not hasattr(value, "filename") or not hasattr(value, "read") or not value.filename:
                continue
            reference_id = key.removeprefix("reference_file__")
            data = await value.read()
            if data:
                register_uploaded_file_bytes(project, reference_id, data, output_root=output_root, kind="reference")
            await value.close()
        prepare_manual_image_workflow(project, output_root)
        return RedirectResponse(f"/projects/{project}/references#refs-list", status_code=303)

    @app.get("/projects/{project}/music", response_class=HTMLResponse)
    def music_page(request: Request, project: str) -> HTMLResponse:
        paths = ProjectPaths.for_project(project, output_root)
        design = load_design(paths)
        suno_params = design.suno_params
        if not suno_params:
            suno_params = SunoMusicParams(lyrics="")
        audio_url = f"/files/{project}/{suno_params.audio_path}" if suno_params.audio_path else None
        return templates.TemplateResponse(request, "music.html", {"project": project, "design": design, "suno": suno_params, "audio_url": audio_url, "model_options": MODEL_OPTIONS})

    @app.post("/projects/{project}/music/save")
    async def save_music_params(request: Request, project: str) -> RedirectResponse:
        paths = ProjectPaths.for_project(project, output_root)
        design = load_design(paths)
        form = await request.form()
        existing_audio_path = design.suno_params.audio_path if design.suno_params else None
        design.suno_params = SunoMusicParams(
            lyrics=str(form.get("lyrics", "")),
            style=str(form.get("style", "")),
            weirdness=int(str(form.get("weirdness", "50"))),
            style_influence=int(str(form.get("style_influence", "80"))),
            audio_influence=int(str(form.get("audio_influence", "50"))),
            audio_path=existing_audio_path,
        )
        paths.design_json.write_text(design.model_dump_json(indent=2), encoding="utf-8")
        return RedirectResponse(f"/projects/{project}/music", status_code=303)

    @app.post("/projects/{project}/music/regenerate")
    async def regenerate_music_params(request: Request, project: str) -> RedirectResponse:
        from vimax_lite.agents import MusicAgent
        paths = ProjectPaths.for_project(project, output_root)
        design = load_design(paths)
        form = await request.form()
        message = str(form.get("message", ""))
        provider_name = str(form.get("provider", "mock"))
        model = str(form.get("model", "gemini-2.5-flash"))
        provider = make_provider(provider_name, model, "gemini-2.5-flash-image")
        existing_audio_path = design.suno_params.audio_path if design.suno_params else None
        suno_params = MusicAgent(provider).run(design.brief, message=message)
        suno_params.audio_path = existing_audio_path
        design.suno_params = suno_params
        paths.design_json.write_text(design.model_dump_json(indent=2), encoding="utf-8")
        return RedirectResponse(f"/projects/{project}/music", status_code=303)

    @app.post("/projects/{project}/music/rebuild-visuals")
    async def rebuild_music_visuals(request: Request, project: str) -> RedirectResponse:
        form = await request.form()
        provider_name = str(form.get("provider", "mock"))
        model = str(form.get("model", "gemini-2.5-flash"))
        job = jobs.create(project)
        thread = threading.Thread(
            target=_run_mv_rebuild_job,
            kwargs={
                "job_id": job.id,
                "project": project,
                "provider_name": provider_name,
                "model": model,
                "output_root": output_root,
            },
            daemon=True,
        )
        thread.start()
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.post("/projects/{project}/music/upload-audio")
    async def upload_music_audio(project: str, file: UploadFile = File(...)) -> RedirectResponse:
        paths = ProjectPaths.for_project(project, output_root)
        design = load_design(paths)
        music_dir = paths.root / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        data = await file.read()
        ext = Path(file.filename or "audio.mp3").suffix or ".mp3"
        audio_filename = f"bgm{ext}"
        (music_dir / audio_filename).write_bytes(data)
        if design.suno_params:
            design.suno_params.audio_path = f"music/{audio_filename}"
        else:
            design.suno_params = SunoMusicParams(audio_path=f"music/{audio_filename}")
        paths.design_json.write_text(design.model_dump_json(indent=2), encoding="utf-8")
        return RedirectResponse(f"/projects/{project}/music#audio-section", status_code=303)

    return app


def _run_sdxl_job(
    *,
    job_id: str,
    project: str,
    items: list[dict[str, str]],
    return_page: str,
    output_root: Path,
) -> None:
    from vimax_lite.sdxl_generator import generate_image

    total = len(items)
    jobs.update(job_id, status="running", stage="generating", message=f"SDXL画像生成を開始します ({total}枚)", current=0, total=total)

    for i, item in enumerate(items):
        image_id = item["id"]
        prompt = item["prompt"]
        kind = item["kind"]
        jobs.update(job_id, message=f"{image_id} を生成中... ({i + 1}/{total})", current=i, total=total)
        try:
            paths = ProjectPaths.for_project(project, output_root)
            if kind == "reference":
                target_path = paths.root / "references" / f"{image_id}.png"
            else:
                target_path = paths.root / "images" / "manual" / f"{image_id}.png"

            generate_image(prompt=prompt, output_path=target_path)

            images = read_image_manifest(paths.image_manifest)
            images = [img for img in images if img.shot_id != image_id]
            images.append(
                GeneratedImage(
                    shot_id=image_id,
                    path=str(target_path),
                    model="sdxl-local",
                    prompt=prompt[:200],
                    status="success",
                )
            )
            write_image_manifest(images, paths.image_manifest)
        except Exception as exc:
            jobs.update(job_id, status="failed", stage="failed", message=f"{image_id} の生成に失敗しました", error=str(exc))
            return

    jobs.update(job_id, status="completed", stage="completed", message=f"SDXL画像生成が完了しました ({total}枚)", current=total, total=total, result_url=return_page)


def _run_generation_job(
    *,
    job_id: str,
    project: str,
    idea: str,
    audience: str,
    style: str,
    duration_seconds: int,
    output_mode: str,
    genre: str,
    mood: str,
    color_tone: str,
    narration_style: str,
    target_platform: str,
    provider_name: str,
    model: str,
    output_root: Path,
) -> None:
    jobs.update(job_id, status="running", message="制作設計を開始しました", current=0, total=9)

    def progress(stage: str, message: str, current: int, total: int) -> None:
        jobs.update(job_id, stage=stage, message=message, current=current, total=total)

    try:
        provider = make_provider(provider_name, model, "gemini-2.5-flash-image")
        run_idea_pipeline(
            idea=idea,
            project=project,
            provider=provider,
            output_root=output_root,
            audience=audience,
            style=style,
            duration_seconds=duration_seconds,
            output_mode=output_mode,
            genre=genre,
            mood=mood,
            color_tone=color_tone,
            narration_style=narration_style,
            target_platform=target_platform,
            generate_images=False,
            image_model="gemini-2.5-flash-image",
            progress=progress,
        )
        prepare_manual_image_workflow(project, output_root)
        jobs.update(
            job_id,
            status="completed",
            stage="completed",
            message="制作設計と画像生成ワークフローの準備が完了しました",
            current=9,
            total=9,
            result_url=f"/projects/{project}",
        )
    except ProviderError as exc:
        jobs.update(job_id, status="failed", stage="failed", message="Providerエラーで停止しました", error=str(exc))
    except Exception as exc:
        jobs.update(job_id, status="failed", stage="failed", message="予期しないエラーで停止しました", error=str(exc))


def _run_mv_rebuild_job(
    *,
    job_id: str,
    project: str,
    provider_name: str,
    model: str,
    output_root: Path,
) -> None:
    jobs.update(job_id, status="running", stage="mv-rebuild", message="MV映像設計の再生成を開始しました", current=0, total=7)

    def progress(stage: str, message: str, current: int, total: int) -> None:
        jobs.update(job_id, stage=stage, message=message, current=current, total=total)

    try:
        provider = make_provider(provider_name, model, "gemini-2.5-flash-image")
        rebuild_mv_visual_design(
            project=project,
            provider=provider,
            output_root=output_root,
            progress=progress,
        )
        prepare_manual_image_workflow(project, output_root)
        timeline = build_timeline_manifest(project=project, output_root=output_root)
        write_timeline_manifest(timeline, project, output_root)
        jobs.update(
            job_id,
            status="completed",
            stage="completed",
            message="Suno歌詞・styleに準拠したMV映像設計を再生成しました",
            current=7,
            total=7,
            result_url=f"/projects/{project}",
        )
    except ProviderError as exc:
        jobs.update(job_id, status="failed", stage="failed", message="Providerエラーで停止しました", error=str(exc))
    except Exception as exc:
        jobs.update(job_id, status="failed", stage="failed", message="MV映像設計の再生成に失敗しました", error=str(exc))


def _run_render_job(
    *,
    job_id: str,
    project: str,
    output_root: Path,
    repo_root: Path,
) -> None:
    jobs.update(job_id, status="running", stage="preparing", message="タイムラインを準備しています", current=0, total=1)

    def progress(current: int, total: int, message: str) -> None:
        jobs.update(job_id, stage="rendering", message=message, current=current, total=max(total, 1))

    try:
        result = render_timeline_with_remotion(
            project=project,
            output_root=output_root,
            repo_root=repo_root,
            progress_callback=progress,
        )
        if result.status == "success":
            jobs.update(
                job_id,
                status="completed",
                stage="completed",
                message="動画の書き出しが完了しました",
                current=result.stdout.count("Rendered") if result.stdout else 1,
                total=result.stdout.count("Rendered") if result.stdout else 1,
                result_url=f"/projects/{project}",
            )
        else:
            jobs.update(
                job_id,
                status="failed",
                stage="failed",
                message="動画の書き出しに失敗しました",
                error=result.stderr or "Remotionレンダリングエラー",
            )
    except Exception as exc:
        jobs.update(job_id, status="failed", stage="failed", message="動画の書き出しに失敗しました", error=str(exc))


def run_web_app(host: str, port: int, output_root: Path) -> None:
    import uvicorn

    uvicorn.run(create_app(output_root), host=host, port=port)
