from __future__ import annotations

from pydantic import BaseModel, Field

from vimax_lite.models import (
    CharacterProfile,
    ContinuityIssue,
    ImagePrompt,
    ScenePlan,
    ScriptBeat,
    ShotPlan,
    VideoPrompt,
)


class ScriptList(BaseModel):
    items: list[ScriptBeat] = Field(default_factory=list)


class CharacterList(BaseModel):
    items: list[CharacterProfile] = Field(default_factory=list)


class SceneList(BaseModel):
    items: list[ScenePlan] = Field(default_factory=list)


class ShotList(BaseModel):
    items: list[ShotPlan] = Field(default_factory=list)


class PromptBundle(BaseModel):
    image_prompts: list[ImagePrompt] = Field(default_factory=list)
    video_prompts: list[VideoPrompt] = Field(default_factory=list)


class ContinuityReport(BaseModel):
    issues: list[ContinuityIssue] = Field(default_factory=list)


class RevisionResult(BaseModel):
    notes: list[str] = Field(default_factory=list)
