from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

SUPPORTED_IMAGE_ASPECT_RATIOS = (
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:1",
    "4:3",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "21:9",
)


class ProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(self, prompt: str, schema_model: type[T]) -> T:
        raise NotImplementedError

    @abstractmethod
    def generate_image(self, prompt: str, output_path: Path, *, model: str | None = None, aspect_ratio: str = "16:9") -> None:
        raise NotImplementedError


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        image_model: str = "gemini-2.5-flash-image",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.image_model = image_model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ProviderError("provider=gemini では GEMINI_API_KEY が必要です。")
        try:
            from google import genai
        except Exception as exc:  # pragma: no cover
            raise ProviderError("google-genai が見つかりません。pip install -e . を実行してください。") from exc
        self._genai = genai
        self.client = genai.Client(api_key=self.api_key)

    def generate_structured(self, prompt: str, schema_model: type[T]) -> T:
        from google.genai import types

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema_model,
                ),
            )
        except Exception as exc:
            raise _friendly_gemini_error(exc, self.model) from exc
        if not getattr(response, "text", None):
            raise ProviderError("Gemini から構造化テキストが返りませんでした。")
        return schema_model.model_validate_json(response.text)

    def generate_image(self, prompt: str, output_path: Path, *, model: str | None = None, aspect_ratio: str = "16:9") -> None:
        try:
            from google.genai import types
            from PIL import Image
        except Exception as exc:  # pragma: no cover
            raise ProviderError("画像生成には google-genai と pillow が必要です。") from exc

        selected_model = model or self.image_model
        normalized_aspect_ratio = normalize_aspect_ratio(aspect_ratio)
        try:
            response = self.client.models.generate_content(
                model=selected_model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio=normalized_aspect_ratio),
                ),
            )
        except Exception as exc:
            raise _friendly_gemini_error(exc, selected_model) from exc
        output_path.parent.mkdir(parents=True, exist_ok=True)
        for part in response.candidates[0].content.parts:
            if getattr(part, "inline_data", None) is not None:
                image = Image.open(BytesIO(part.inline_data.data))
                image.save(output_path)
                return
        raise ProviderError("Gemini 画像生成のレスポンスに画像データがありませんでした。")


class ClaudeProvider(LLMProvider):
    """`claude -p`を使ってテキスト生成を行うProvider。画像生成は未対応。"""

    def generate_structured(self, prompt: str, schema_model: type[T]) -> T:
        schema_json = schema_model.model_json_schema()
        full_prompt = (
            f"{prompt}\n\n"
            "必ず次のJSON Schemaに従ったJSONだけを返してください。"
            "JSON以外の説明文は一切含めないでください。\n"
            f"```json-schema\n{json.dumps(schema_json, ensure_ascii=False, indent=2)}\n```"
        )
        try:
            result = subprocess.run(
                ["claude", "-p", full_prompt],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except FileNotFoundError:
            raise ProviderError("claude コマンドが見つかりません。Claude Code CLIをインストールしてください。")
        except subprocess.TimeoutExpired:
            raise ProviderError("claude -p がタイムアウトしました。")
        if result.returncode != 0:
            raise ProviderError(f"claude -p がエラーを返しました: {result.stderr.strip()}")
        text = result.stdout.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise ProviderError(f"claude -p の応答をJSONとしてパースできませんでした: {text[:300]}")
        return schema_model.model_validate(data)

    def generate_image(self, prompt: str, output_path: Path, *, model: str | None = None, aspect_ratio: str = "16:9") -> None:
        raise ProviderError("ClaudeProviderは画像生成に対応していません。--provider gemini を使用してください。")


class MockProvider(LLMProvider):
    """API課金なしで学習・テストするための決定的なProvider。"""

    def generate_structured(self, prompt: str, schema_model: type[T]) -> T:
        data = _mock_payload(schema_model.__name__, prompt)
        return schema_model.model_validate(data)

    def generate_image(self, prompt: str, output_path: Path, *, model: str | None = None, aspect_ratio: str = "16:9") -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
                "0000000c49444154789c6360f8cf00000301010118dd8db00000000049454e44ae426082"
            )
        )


def make_provider(kind: str, model: str, image_model: str) -> LLMProvider:
    if kind == "gemini":
        return GeminiProvider(model=model, image_model=image_model)
    if kind == "claude":
        return ClaudeProvider()
    if kind == "mock":
        return MockProvider()
    raise ProviderError(f"未知のProviderです: {kind}")


def normalize_aspect_ratio(aspect_ratio: str) -> str:
    """Gemini画像生成が受け付ける比率へ丸める。例: 2.35:1 -> 21:9。"""
    cleaned = (aspect_ratio or "16:9").strip()
    if cleaned in SUPPORTED_IMAGE_ASPECT_RATIOS:
        return cleaned
    try:
        width, height = cleaned.split(":", 1)
        value = float(width) / float(height)
    except Exception:
        return "16:9"

    def ratio_value(ratio: str) -> float:
        ratio_width, ratio_height = ratio.split(":", 1)
        return float(Fraction(ratio_width)) / float(Fraction(ratio_height))

    return min(SUPPORTED_IMAGE_ASPECT_RATIOS, key=lambda ratio: abs(ratio_value(ratio) - value))


def _friendly_gemini_error(exc: Exception, model: str) -> ProviderError:
    status_code = getattr(exc, "status_code", None)
    message = str(exc)
    if status_code == 429 or "RESOURCE_EXHAUSTED" in message:
        return ProviderError(
            f"Gemini APIのクォータを超過しました。model={model}。"
            "無料枠・課金設定・レート制限を確認してください。"
            "開発中は --provider mock で全体の動作確認を続けられます。"
        )
    if status_code == 503 or "UNAVAILABLE" in message:
        return ProviderError(
            f"Gemini APIが一時的に混雑しています。model={model}。"
            "少し待って再実行するか、別モデルを指定してください。"
        )
    if status_code == 401 or status_code == 403 or "API key" in message:
        return ProviderError(
            "Gemini APIキーまたは権限に問題があります。"
            "GEMINI_API_KEY とGoogle AI Studio側の設定を確認してください。"
        )
    if status_code == 400 and "aspect_ratio" in message:
        return ProviderError(
            f"Gemini画像生成が対応していないアスペクト比です。model={model}。"
            f"対応比率: {', '.join(SUPPORTED_IMAGE_ASPECT_RATIOS)}"
        )
    return ProviderError(f"Gemini API呼び出しに失敗しました。model={model}. detail={message}")


def _idea_from_prompt(prompt: str) -> str:
    marker = "USER_INPUT:"
    if marker in prompt:
        return prompt.split(marker, 1)[1].strip().splitlines()[0][:140]
    return "雨の街で小さなロボットが音楽に出会う"


def _mock_payload(name: str, prompt: str) -> dict:
    idea = _idea_from_prompt(prompt)
    if name == "ProductionBrief":
        return {
            "title": "Rain Alley Overture",
            "logline": idea,
            "audience": "general",
            "style": "cinematic anime with grounded lighting",
            "duration_seconds": 60,
            "themes": ["孤独", "好奇心", "創造性の目覚め"],
            "visual_rules": ["雨の反射", "暖かいネオン", "ロボットのシルエットを固定"],
            "negative_constraints": ["動画生成はしない", "キャラクターデザインを急に変えない"],
        }
    if name == "ScriptList":
        return {
            "items": [
                {
                    "beat_id": "beat_001",
                    "summary": "配達ロボットが雨の路地で遠くの音楽を聞いて立ち止まる。",
                    "dialogue": [],
                    "emotional_purpose": "孤独と好奇心を示す。",
                },
                {
                    "beat_id": "beat_002",
                    "summary": "ロボットは自販機の下で光る壊れたオルゴールを見つける。",
                    "dialogue": ["Robot: この音の模様は何だろう。"],
                    "emotional_purpose": "発見を描く。",
                },
                {
                    "beat_id": "beat_003",
                    "summary": "ロボットが旋律を再生すると、路地の光が応答する。",
                    "dialogue": [],
                    "emotional_purpose": "変化と余韻で締める。",
                },
            ]
        }
    if name == "CharacterList":
        return {
            "items": [
                {
                    "id": "char_robot",
                    "name": "Milo",
                    "role": "the main character, a lonely delivery robot",
                    "personality": "careful, observant, quietly brave, and curious",
                    "appearance": "a small white delivery robot with a square screen face, rounded cargo shell, compact wheels, and a glowing blue status light",
                    "wardrobe": "a yellow rain poncho clipped to the cargo shell, wet from the rain",
                    "voice": "soft electronic chimes",
                    "continuity_notes": ["always show the glowing blue status light", "keep the yellow rain poncho wet and attached to the cargo shell"],
                }
            ]
        }
    if name == "SceneList":
        return {
            "items": [
                {
                    "scene_id": "scene_001",
                    "title": "雨の中の音",
                    "location": "自販機のある東京の狭い路地",
                    "time_of_day": "夜",
                    "summary": "Miloは雨がネオンを溶かす路地で音楽を聞く。",
                    "characters": ["char_robot"],
                    "beats": _mock_payload("ScriptList", prompt)["items"][:2],
                    "continuity_requirements": ["黄色いポンチョを維持", "雨は降り続ける"],
                },
                {
                    "scene_id": "scene_002",
                    "title": "路地の応答",
                    "location": "同じ路地。自販機の近く。",
                    "time_of_day": "夜",
                    "summary": "Miloが旋律を返すと、環境が光を帯びる。",
                    "characters": ["char_robot"],
                    "beats": _mock_payload("ScriptList", prompt)["items"][2:],
                    "continuity_requirements": ["同じオルゴール", "同じ青いステータスライト"],
                },
            ]
        }
    if name == "ShotList":
        return {
            "items": [
                _shot("shot_001", "scene_001", 1, "雨とネオン反射の中に立つMiloのワイドショット", "low wide angle", "24mm", "slow dolly forward"),
                _shot("shot_002", "scene_001", 2, "Miloがオルゴールを見つけるクローズアップ", "macro close-up", "50mm", "gentle rack focus"),
                _shot("shot_003", "scene_002", 3, "Miloが旋律を鳴らすと路地の光が脈打つ", "medium orbit", "35mm", "slow semicircle"),
            ]
        }
    if name == "PromptBundle":
        shots = _mock_payload("ShotList", prompt)["items"]
        return {
            "image_prompts": [
                {
                    "shot_id": shot["shot_id"],
                    "prompt": f"{shot['description']}, {shot['lighting']}, cinematic anime, rain reflections, small white delivery robot with yellow rain poncho",
                    "negative_prompt": "inconsistent character design, extra robots, blurry face screen",
                    "aspect_ratio": "16:9",
                    "style_tags": ["cinematic anime", "rain", "neon"],
                }
                for shot in shots
            ],
            "video_prompts": [
                {
                    "shot_id": shot["shot_id"],
                    "prompt": f"{shot['description']} Start: {shot['first_frame']} End: {shot['last_frame']}.",
                    "duration_seconds": 5,
                    "camera_motion": shot["motion"],
                    "temporal_notes": "キャラクターの形状と濡れたポンチョを維持する。",
                }
                for shot in shots
            ],
        }
    if name == "ContinuityReport":
        return {"issues": [{"severity": "low", "location": "shot_003", "issue": "オルゴールの琥珀色の光を明示すると連続性が強くなる。", "recommendation": "shot_003とプロンプトに琥珀色の光を追記する。"}]}
    if name == "RevisionResult":
        return {"notes": ["オルゴールの琥珀色の光を継続性メモとして追加する方針にしました。"]}
    raise ProviderError(f"mock payload が未定義です: {name}. prompt={json.dumps(prompt[:200], ensure_ascii=False)}")


def _shot(shot_id: str, scene_id: str, order: int, description: str, camera: str, lens: str, motion: str) -> dict:
    return {
        "shot_id": shot_id,
        "scene_id": scene_id,
        "order": order,
        "description": description,
        "camera": camera,
        "lens": lens,
        "motion": motion,
        "first_frame": "雨粒が反射する路面から始まる",
        "last_frame": "Miloの青いライトが画面内に残る",
        "lighting": "青い雨光と暖かい自販機の光",
        "audio": "雨音と遠いオルゴール",
        "referenced_memory": ["character:char_robot"],
    }
