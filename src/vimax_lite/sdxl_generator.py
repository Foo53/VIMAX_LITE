"""SDXLとIP-Adapterによるローカル候補画像生成サービス。"""
from __future__ import annotations

import importlib.util
import threading
from pathlib import Path
from typing import Any

MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
IP_ADAPTER_ID = "h94/IP-Adapter"
MODEL_CACHE_DIR = Path.home() / ".models" / "sdxl"

DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, deformed, ugly, bad anatomy, "
    "watermark, text, logo, caption, label, grid, multiple views"
)

_pipeline: Any | None = None
_ip_adapter_loaded = False
_pipeline_lock = threading.Lock()
_generate_lock = threading.Lock()


def runtime_status() -> dict[str, Any]:
    """Web UI表示用に、重いモデルを読まず実行準備状況だけ確認する。"""
    missing = [module for module in ("torch", "diffusers", "transformers", "accelerate") if importlib.util.find_spec(module) is None]
    if missing:
        return {
            "available": False,
            "device": "unavailable",
            "reference_support": False,
            "message": f"SDXL依存関係が未導入です: {', '.join(missing)}。`pip install -e \".[sdxl]\"` を実行してください。",
        }
    import torch

    if torch.cuda.is_available():
        device = f"CUDA ({torch.cuda.get_device_name(0)})"
        message = "GPUで生成できます。初回のみSDXLおよびIP-Adapterのモデル取得に時間がかかります。"
    else:
        device = "CPU"
        message = "CPU生成は利用できますが非常に時間がかかります。GPU環境を推奨します。初回はモデル取得も発生します。"
    return {"available": True, "device": device, "reference_support": True, "message": message}


def _load_dependencies() -> tuple[Any, Any]:
    try:
        import torch
        from diffusers import StableDiffusionXLPipeline
    except ImportError as exc:
        raise RuntimeError("SDXLを使用するには `pip install -e \".[sdxl]\"` を実行してください。") from exc
    return torch, StableDiffusionXLPipeline


def _get_pipeline(*, with_reference: bool) -> Any:
    global _pipeline, _ip_adapter_loaded
    torch, pipeline_type = _load_dependencies()
    with _pipeline_lock:
        if _pipeline is None:
            cuda = torch.cuda.is_available()
            dtype = torch.float16 if cuda else torch.float32
            _pipeline = pipeline_type.from_pretrained(
                MODEL_ID,
                torch_dtype=dtype,
                cache_dir=str(MODEL_CACHE_DIR),
            )
            if cuda:
                _pipeline.to("cuda")
                _pipeline.enable_vae_slicing()
                try:
                    _pipeline.enable_xformers_memory_efficient_attention()
                except ImportError:
                    _pipeline.enable_attention_slicing()
            else:
                _pipeline.to("cpu")
        if with_reference and not _ip_adapter_loaded:
            _pipeline.load_ip_adapter(
                IP_ADAPTER_ID,
                subfolder="sdxl_models",
                weight_name="ip-adapter_sdxl.bin",
            )
            _pipeline.set_ip_adapter_scale(0.65)
            _ip_adapter_loaded = True
        return _pipeline


def _reference_condition_image(reference_paths: list[Path]) -> Any | None:
    existing_paths = [path for path in reference_paths if path.exists()]
    if not existing_paths:
        return None
    from PIL import Image, ImageOps

    if len(existing_paths) == 1:
        return Image.open(existing_paths[0]).convert("RGB")
    size = 512
    cells = [ImageOps.fit(Image.open(path).convert("RGB"), (size, size)) for path in existing_paths[:4]]
    canvas = Image.new("RGB", (size * 2, size * 2), "#e8eaed")
    positions = [(0, 0), (size, 0), (0, size), (size, size)]
    for cell, position in zip(cells, positions):
        canvas.paste(cell, position)
    return canvas


def generate_image(
    prompt: str,
    output_path: Path,
    *,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    reference_paths: list[Path] | None = None,
    width: int = 1024,
    height: int = 1024,
    steps: int = 30,
    seed: int | None = 42,
) -> Path:
    """SDXL候補を生成する。参照画像があればIP-Adapterへ実画像を渡す。"""
    with _generate_lock:
        torch, _ = _load_dependencies()
        reference_image = _reference_condition_image(reference_paths or [])
        pipe = _get_pipeline(with_reference=reference_image is not None)
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "generator": generator,
        }
        if reference_image is not None:
            kwargs["ip_adapter_image"] = reference_image
        image = pipe(**kwargs).images[0]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(output_path))
    return output_path
