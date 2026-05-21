from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductionBrief(BaseModel):
    title: str = Field(description="作品タイトル")
    logline: str = Field(description="作品の短い説明")
    audience: str = Field(default="general", description="想定視聴者")
    style: str = Field(default="cinematic", description="映像スタイル")
    duration_seconds: int = Field(default=60, description="想定尺")
    output_mode: Literal["standard", "remotion"] = Field(default="standard", description="出力モード")
    themes: list[str] = Field(default_factory=list, description="テーマ")
    visual_rules: list[str] = Field(default_factory=list, description="映像上の一貫性ルール")
    negative_constraints: list[str] = Field(default_factory=list, description="避けるべき表現")


class CharacterProfile(BaseModel):
    id: str
    name: str
    role: str
    personality: str
    appearance: str
    wardrobe: str
    voice: str = ""
    continuity_notes: list[str] = Field(default_factory=list)


class ScriptBeat(BaseModel):
    beat_id: str
    summary: str
    dialogue: list[str] = Field(default_factory=list)
    emotional_purpose: str


class ScenePlan(BaseModel):
    scene_id: str
    title: str
    location: str
    time_of_day: str
    summary: str
    characters: list[str] = Field(default_factory=list)
    beats: list[ScriptBeat] = Field(default_factory=list)
    continuity_requirements: list[str] = Field(default_factory=list)


class ShotPlan(BaseModel):
    shot_id: str
    scene_id: str
    order: int
    description: str
    camera: str
    lens: str
    motion: str
    first_frame: str
    last_frame: str
    lighting: str
    audio: str
    referenced_memory: list[str] = Field(default_factory=list)


class ImagePrompt(BaseModel):
    shot_id: str
    prompt: str
    negative_prompt: str = ""
    aspect_ratio: str = "16:9"
    style_tags: list[str] = Field(default_factory=list)


class VideoPrompt(BaseModel):
    shot_id: str
    prompt: str
    duration_seconds: int = 5
    camera_motion: str
    temporal_notes: str


class ContinuityIssue(BaseModel):
    severity: Literal["low", "medium", "high"]
    location: str
    issue: str
    recommendation: str


class GeneratedImage(BaseModel):
    shot_id: str
    path: str | None = None
    model: str
    prompt: str
    status: Literal["success", "failed", "skipped"]
    error: str | None = None
    created_at: str = Field(default_factory=now_iso)


class RAGTraceItem(BaseModel):
    query: str
    results: list[str] = Field(default_factory=list)
    used_by: str


class ProductionDesign(BaseModel):
    brief: ProductionBrief
    script: list[ScriptBeat]
    characters: list[CharacterProfile]
    scenes: list[ScenePlan]
    shots: list[ShotPlan]
    image_prompts: list[ImagePrompt]
    video_prompts: list[VideoPrompt]
    continuity_issues: list[ContinuityIssue] = Field(default_factory=list)
    generated_images: list[GeneratedImage] = Field(default_factory=list)
    rag_trace: list[RAGTraceItem] = Field(default_factory=list)
    learning_notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)


class ProjectPaths(BaseModel):
    root: Path
    images: Path
    rag_store: Path
    design_json: Path
    image_manifest: Path

    @classmethod
    def for_project(cls, project: str, output_root: Path = Path("outputs")) -> "ProjectPaths":
        root = output_root / project
        return cls(
            root=root,
            images=root / "images",
            rag_store=root / "rag_store.json",
            design_json=root / "design.json",
            image_manifest=root / "images" / "image_manifest.json",
        )
