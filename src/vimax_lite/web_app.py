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
    register_uploaded_image,
)
from vimax_lite.models import ProjectPaths
from vimax_lite.pipeline import run_idea_pipeline
from vimax_lite.providers import ProviderError, make_provider


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
        return templates.TemplateResponse(
            request,
            "project.html",
            {"project": project, "design": design, "counts": counts, "workflow": workflow},
        )

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
        return RedirectResponse(f"/projects/{project}/shots", status_code=303)

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
        return RedirectResponse(f"/projects/{project}/references", status_code=303)

    return app


def _run_generation_job(
    *,
    job_id: str,
    project: str,
    idea: str,
    audience: str,
    style: str,
    duration_seconds: int,
    output_mode: str,
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


def run_web_app(host: str, port: int, output_root: Path) -> None:
    import uvicorn

    uvicorn.run(create_app(output_root), host=host, port=port)
