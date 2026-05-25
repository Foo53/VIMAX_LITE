"""SDXL local image generation service with lazy pipeline loading."""
from __future__ import annotations

import threading
from pathlib import Path

import torch
from diffusers import StableDiffusionXLPipeline

MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
MODEL_CACHE_DIR = Path.home() / ".models" / "sdxl"

DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, deformed, ugly, bad anatomy, "
    "watermark, text, logo, caption, label"
)

_pipeline: StableDiffusionXLPipeline | None = None
_pipeline_lock = threading.Lock()
_generate_lock = threading.Lock()


def _get_pipeline() -> StableDiffusionXLPipeline:
    global _pipeline
    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        pipe = StableDiffusionXLPipeline.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16,
            cache_dir=str(MODEL_CACHE_DIR),
        )
        pipe.enable_model_cpu_offload()
        _pipeline = pipe
        return _pipeline


def generate_image(
    prompt: str,
    output_path: Path,
    *,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    width: int = 1024,
    height: int = 1024,
    steps: int = 30,
    seed: int | None = 42,
) -> Path:
    with _generate_lock:
        pipe = _get_pipeline()
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
        image = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            generator=generator,
        ).images[0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(output_path))
    return output_path
