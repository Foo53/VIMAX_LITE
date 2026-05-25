from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimax_lite.cli import main
from vimax_lite.manual_workflow import build_character_reference_sheet, build_manual_prompt, build_sdxl_negative_prompt, build_sdxl_shot_prompt, image_counts, prepare_manual_image_workflow
from vimax_lite.models import ProductionBrief, ProductionDesign
from vimax_lite.providers import MockProvider
from vimax_lite.timeline import build_timeline_manifest
from vimax_lite.web_app import _dimensions_for_aspect_ratio, _run_sdxl_job, create_app, jobs


class PipelineTest(unittest.TestCase):
    def test_mock_provider_structured_brief(self) -> None:
        provider = MockProvider()
        brief = provider.generate_structured("USER_INPUT: test idea", ProductionBrief)
        self.assertTrue(brief.title)
        self.assertIn("test idea", brief.logline)

    def test_idea_pipeline_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                ]
            )
            root = Path(temp) / "demo"
            self.assertTrue((root / "design.md").exists())
            self.assertTrue((root / "design.json").exists())
            self.assertTrue((root / "rag_trace.md").exists())
            design = ProductionDesign.model_validate_json((root / "design.json").read_text(encoding="utf-8"))
            self.assertEqual(len(design.shots), 3)
            self.assertTrue(design.image_prompts)
            self.assertTrue(design.video_prompts)
            self.assertTrue(design.learning_notes)

    def test_generate_images_with_mock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                    "--generate-images",
                    "--max-images",
                    "3",
                ]
            )
            root = Path(temp) / "demo"
            manifest = json.loads((root / "images" / "image_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["images"]), 3)
            self.assertTrue((root / "images" / "shot_001.png").exists())

    def test_inspect_rag_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                ]
            )
            output = StringIO()
            with redirect_stdout(output):
                main(["--output-root", temp, "inspect-rag", "--project", "demo"])
            self.assertIn("character:", output.getvalue())

    def test_manual_workflow_outputs_reference_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                ]
            )
            workflow = prepare_manual_image_workflow("demo", Path(temp))
            root = Path(temp) / "demo"
            self.assertTrue((root / "references" / "character_reference_sheet.md").exists())
            self.assertTrue((root / "reference_plan.md").exists())
            self.assertTrue((root / "manual_generation_guide.md").exists())
            self.assertTrue((root / "sdxl_generation_guide.md").exists())
            self.assertEqual(workflow["reference_plan"]["remaining"], 3)
            self.assertEqual(image_counts("demo", Path(temp))["remaining"], 3)

    def test_manual_prompt_is_english_and_labels_reference_roles(self) -> None:
        prompt = build_manual_prompt(
            "shot_002",
            "Rainy Tokyo alley, lonely delivery robot finds music.",
            ["references/character_robot_front.png", "images/manual/shot_001.png"],
        )
        self.assertIn("Generate one production-quality still image", prompt)
        self.assertIn("Image 0", prompt)
        self.assertIn("primary character design reference", prompt)
        self.assertIn("Image 1", prompt)
        self.assertIn("previous generated shot", prompt)
        self.assertIn("Do not show multiple views", prompt)
        self.assertIn("translate and interpret it internally", prompt)

    def test_character_reference_prompt_is_english_for_mock_design(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                ]
            )
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            references = build_character_reference_sheet(design)
            prompt = references["characters"][0]["prompts"][0]["prompt"]
            self.assertIn("Create exactly one single-view character reference image", prompt)
            self.assertIn("small white delivery robot", prompt)
            self.assertIn("yellow rain poncho", prompt)
            self.assertIn("no model sheet", prompt)
            self.assertIn("no multiple views", prompt)
            self.assertIn("Show exactly one full-body character facing the camera", prompt)
            self.assertNotIn("reference sheet style", prompt)
            self.assertNotIn("配達ロボット", prompt)
            sdxl_prompt = references["characters"][0]["prompts"][0]["sdxl_prompt"]
            self.assertIn("single character reference image", sdxl_prompt)
            self.assertIn("front view", sdxl_prompt)
            self.assertNotIn("Generate only this single requested view", sdxl_prompt)

    def test_sdxl_shot_prompt_excludes_manual_attachment_instructions(self) -> None:
        sdxl_prompt = build_sdxl_shot_prompt("A robot beneath neon rain.", ["cinematic", "night"])
        self.assertIn("A robot beneath neon rain.", sdxl_prompt)
        self.assertIn("cinematic, night", sdxl_prompt)
        self.assertNotIn("Required reference images to attach", sdxl_prompt)
        negative_prompt = build_sdxl_negative_prompt("oversaturated colors, sunny sky")
        self.assertIn("duplicate subject", negative_prompt)
        self.assertIn("oversaturated colors, sunny sky", negative_prompt)

    def test_remotion_output_mode_shapes_design(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "remotion",
                ]
            )
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            self.assertEqual(design.brief.output_mode, "remotion")
            self.assertIn("Remotion", design.video_prompts[0].prompt)
            self.assertIn("Remotionモード", "\n".join(design.learning_notes))

    def test_timeline_command_writes_manifest_for_remotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "remotion",
                    "--generate-images",
                    "--max-images",
                    "3",
                ]
            )
            output = StringIO()
            with redirect_stdout(output):
                main(["--output-root", temp, "timeline", "--project", "demo"])
            root = Path(temp) / "demo"
            manifest_path = root / "timeline_manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["output_mode"], "remotion")
            self.assertEqual(len(manifest["shots"]), 3)
            self.assertEqual(manifest["shots"][0]["status"], "ready")
            self.assertIn("BGM", "\n".join(manifest["todos"]))

    def test_timeline_manifest_marks_missing_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "remotion",
                ]
            )
            manifest = build_timeline_manifest(project="demo", output_root=Path(temp))
            self.assertEqual(manifest.shots[0].status, "missing")
            self.assertIsNone(manifest.shots[0].image_src)

    def test_reference_batch_upload_saves_each_reference_id(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "雨の中でロボットが音楽を聞く",
                    "--provider",
                    "mock",
                ]
            )
            client = TestClient(create_app(Path(temp)))
            response = client.post(
                "/projects/demo/references/upload-batch",
                files={
                    "reference_file__character_char_robot_front": ("front.png", b"front-image", "image/png"),
                    "reference_file__character_char_robot_side": ("side.png", b"side-image", "image/png"),
                },
            )
            self.assertEqual(response.status_code, 200)
            root = Path(temp) / "demo" / "references"
            self.assertEqual((root / "character_char_robot_front.png").read_bytes(), b"front-image")
            self.assertEqual((root / "character_char_robot_side.png").read_bytes(), b"side-image")

    def test_narration_caption_used_in_timeline_for_remotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "テスト",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "remotion",
                ]
            )
            manifest = build_timeline_manifest(project="demo", output_root=Path(temp))
            for shot in manifest.shots:
                self.assertTrue(shot.caption)
                self.assertNotIn("ワイドショット", shot.caption)
                self.assertNotIn("クローズアップ", shot.caption)

    def test_narration_caption_empty_for_standard_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "テスト",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "standard",
                ]
            )
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            for shot in design.shots:
                self.assertEqual(shot.narration_caption, "")

    def test_production_brief_new_fields_default_empty(self) -> None:
        brief = ProductionBrief(title="t", logline="l")
        self.assertEqual(brief.genre, "")
        self.assertEqual(brief.mood, "")
        self.assertEqual(brief.color_tone, "")
        self.assertEqual(brief.narration_style, "")
        self.assertEqual(brief.target_platform, "")

    def test_target_platform_sets_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "テスト",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "remotion",
                    "--target-platform",
                    "tiktok",
                ]
            )
            manifest = build_timeline_manifest(project="demo", output_root=Path(temp))
            self.assertEqual(manifest.width, 1080)
            self.assertEqual(manifest.height, 1920)

    def test_mv_mode_generates_suno_params(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "テストMV",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "mv",
                ]
            )
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            self.assertEqual(design.brief.output_mode, "mv")
            self.assertIsNotNone(design.suno_params)
            self.assertTrue(design.suno_params.lyrics)
            self.assertTrue(design.suno_params.style)
            self.assertIn("[Verse", design.suno_params.lyrics)
            self.assertIn("[Chorus", design.suno_params.lyrics)
            self.assertIn("[End]", design.suno_params.lyrics)
            self.assertTrue(any(":" in line for line in design.suno_params.lyrics.split("\n") if line.startswith("[")))
            self.assertTrue(design.song_sections)
            self.assertIsNotNone(design.mv_visual_plan)

    def test_mv_mode_lyrics_in_captions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "テストMV",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "mv",
                ]
            )
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            for shot in design.shots:
                self.assertTrue(shot.narration_caption, f"{shot.shot_id} should have narration_caption in MV mode")

    def test_mv_mode_image_prompts_generated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "テストMV",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "mv",
                ]
            )
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            self.assertTrue(design.image_prompts)
            self.assertTrue(design.video_prompts)
            self.assertIn("MV", "\n".join(design.learning_notes))

    def test_mv_timeline_has_lyrics_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root",
                    temp,
                    "idea2design",
                    "--project",
                    "demo",
                    "--idea",
                    "テストMV",
                    "--provider",
                    "mock",
                    "--output-mode",
                    "mv",
                ]
            )
            manifest = build_timeline_manifest(project="demo", output_root=Path(temp))
            self.assertEqual(manifest.output_mode, "mv")
            self.assertTrue(manifest.lyrics_timeline)
            for shot in manifest.shots:
                self.assertIn(shot.shot_id, manifest.lyrics_timeline)
                self.assertTrue(manifest.lyrics_timeline[shot.shot_id])

    def test_suno_music_params_model_defaults(self) -> None:
        from vimax_lite.models import SunoMusicParams
        params = SunoMusicParams(lyrics="test")
        self.assertEqual(params.weirdness, 50)
        self.assertEqual(params.style_influence, 80)
        self.assertEqual(params.audio_influence, 50)
        self.assertIsNone(params.audio_path)

    def test_music_audio_upload_saves_file(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root", temp,
                    "idea2design", "--project", "demo",
                    "--idea", "テストMV", "--provider", "mock",
                    "--output-mode", "mv",
                ]
            )
            client = TestClient(create_app(Path(temp)))
            response = client.post(
                "/projects/demo/music/upload-audio",
                files={"file": ("bgm.mp3", b"fake-mp3-data", "audio/mpeg")},
            )
            self.assertEqual(response.status_code, 200)
            audio_path = Path(temp) / "demo" / "music" / "bgm.mp3"
            self.assertTrue(audio_path.exists())
            self.assertEqual(audio_path.read_bytes(), b"fake-mp3-data")
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            self.assertEqual(design.suno_params.audio_path, "music/bgm.mp3")

    def test_music_save_preserves_uploaded_audio_path(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root", temp,
                    "idea2design", "--project", "demo",
                    "--idea", "テストMV", "--provider", "mock",
                    "--output-mode", "mv",
                ]
            )
            client = TestClient(create_app(Path(temp)))
            client.post(
                "/projects/demo/music/upload-audio",
                files={"file": ("bgm.mp3", b"fake-mp3-data", "audio/mpeg")},
            )
            response = client.post(
                "/projects/demo/music/save",
                data={
                    "lyrics": "[Verse]\n新しい歌詞\n[End]",
                    "style": "J-Pop, bright synth, female vocals",
                    "weirdness": "35",
                    "style_influence": "85",
                    "audio_influence": "60",
                },
            )
            self.assertEqual(response.status_code, 200)
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            self.assertEqual(design.suno_params.audio_path, "music/bgm.mp3")

    def test_timeline_manifest_includes_uploaded_bgm_data_uri(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root", temp,
                    "idea2design", "--project", "demo",
                    "--idea", "テストMV", "--provider", "mock",
                    "--output-mode", "mv",
                ]
            )
            client = TestClient(create_app(Path(temp)))
            client.post(
                "/projects/demo/music/upload-audio",
                files={"file": ("bgm.mp3", b"fake-mp3-data", "audio/mpeg")},
            )
            manifest = build_timeline_manifest(project="demo", output_root=Path(temp))
            self.assertTrue(manifest.audio["bgm"].startswith("data:audio/mpeg;base64,"))

    def test_rebuild_mv_visuals_uses_existing_suno_params(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root", temp,
                    "idea2design", "--project", "demo",
                    "--idea", "テストMV", "--provider", "mock",
                    "--output-mode", "mv",
                ]
            )
            main(["--output-root", temp, "rebuild-mv-visuals", "--project", "demo", "--provider", "mock"])
            design = ProductionDesign.model_validate_json((Path(temp) / "demo" / "design.json").read_text(encoding="utf-8"))
            self.assertTrue(design.song_sections)
            self.assertIsNotNone(design.mv_visual_plan)
            self.assertIn("MV再設計", "\n".join(design.learning_notes))

    def test_sdxl_job_saves_candidate_without_overwriting_adopted_shot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root", temp,
                    "idea2design", "--project", "demo",
                    "--idea", "雨の中でロボットが音楽を聞く", "--provider", "mock",
                ]
            )
            root = Path(temp) / "demo"
            adopted = root / "images" / "manual" / "shot_001.png"
            adopted.parent.mkdir(parents=True, exist_ok=True)
            adopted.write_bytes(b"adopted-image")
            reference = root / "references" / "character_char_robot_front.png"
            reference.parent.mkdir(parents=True, exist_ok=True)
            reference.write_bytes(b"reference-image")

            job = jobs.create("demo")

            def fake_generate_image(**kwargs: object) -> Path:
                output_path = Path(str(kwargs["output_path"]))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"candidate-image")
                return output_path

            with (
                patch(
                    "vimax_lite.sdxl_generator.runtime_status",
                    return_value={"available": True, "device": "test", "reference_support": True, "message": "ok"},
                ),
                patch("vimax_lite.sdxl_generator.generate_image", side_effect=fake_generate_image) as generate_image,
            ):
                _run_sdxl_job(
                    job_id=job.id,
                    project="demo",
                    items=[
                        {
                            "id": "shot_001",
                            "prompt": "A cinematic still",
                            "negative_prompt": "duplicate subject, watermark",
                            "kind": "shot",
                            "reference_paths": [str(reference)],
                            "width": 1344,
                            "height": 768,
                        }
                    ],
                    return_page="/projects/demo/shots",
                    output_root=Path(temp),
                )

            candidate = root / "images" / "sdxl_candidates" / "shot" / "shot_001.png"
            metadata = json.loads(candidate.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(adopted.read_bytes(), b"adopted-image")
            self.assertEqual(candidate.read_bytes(), b"candidate-image")
            self.assertEqual(metadata["model"], "sdxl-local-ip-adapter")
            self.assertEqual(metadata["width"], 1344)
            self.assertEqual(metadata["height"], 768)
            self.assertEqual(generate_image.call_args.kwargs["reference_paths"], [reference])
            self.assertEqual(generate_image.call_args.kwargs["negative_prompt"], "duplicate subject, watermark")
            self.assertEqual(jobs.get(job.id).status, "completed")

    def test_adopting_sdxl_candidate_promotes_it_to_shot_image(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root", temp,
                    "idea2design", "--project", "demo",
                    "--idea", "雨の中でロボットが音楽を聞く", "--provider", "mock",
                ]
            )
            root = Path(temp) / "demo"
            candidate = root / "images" / "sdxl_candidates" / "shot" / "shot_001.png"
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(b"approved-candidate")
            candidate.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "prompt": "selected prompt",
                        "reference_paths": ["references/character_char_robot_front.png"],
                    }
                ),
                encoding="utf-8",
            )

            response = TestClient(create_app(Path(temp))).post("/projects/demo/shots/shot_001/adopt-sdxl")

            self.assertEqual(response.status_code, 200)
            adopted = root / "images" / "manual" / "shot_001.png"
            self.assertEqual(adopted.read_bytes(), b"approved-candidate")
            manifest = json.loads((root / "images" / "image_manifest.json").read_text(encoding="utf-8"))
            record = next(item for item in manifest["images"] if item["shot_id"] == "shot_001")
            self.assertEqual(record["model"], "sdxl-local-ip-adapter")

    def test_sdxl_unavailable_reports_failed_job_instead_of_hanging(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            job = jobs.create("demo")
            with patch(
                "vimax_lite.sdxl_generator.runtime_status",
                return_value={"available": False, "device": "unavailable", "reference_support": False, "message": "依存関係が未導入です"},
            ):
                _run_sdxl_job(
                    job_id=job.id,
                    project="demo",
                    items=[{"id": "shot_001", "prompt": "test", "kind": "shot"}],
                    return_page="/projects/demo/shots",
                    output_root=Path(temp),
                )

            failed_job = jobs.get(job.id)
            self.assertEqual(failed_job.status, "failed")
            self.assertIn("依存関係が未導入", failed_job.error)

    def test_sdxl_dimensions_keep_cinematic_aspect_ratio(self) -> None:
        self.assertEqual(_dimensions_for_aspect_ratio("16:9"), (1344, 768))
        self.assertEqual(_dimensions_for_aspect_ratio("2.35:1"), (1536, 640))

    def test_reference_page_renders_sdxl_candidate_and_adopt_action(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp:
            main(
                [
                    "--output-root", temp,
                    "idea2design", "--project", "demo",
                    "--idea", "雨の中でロボットが音楽を聞く", "--provider", "mock",
                ]
            )
            candidate = Path(temp) / "demo" / "images" / "sdxl_candidates" / "reference" / "character_char_robot_front.png"
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(b"candidate")
            with patch(
                "vimax_lite.web_app._sdxl_status",
                return_value={"available": True, "device": "CUDA (test)", "reference_support": True, "message": "準備完了"},
            ):
                response = TestClient(create_app(Path(temp))).get("/projects/demo/references")

            self.assertEqual(response.status_code, 200)
            self.assertIn("SDXL候補画像", response.text)
            self.assertIn("この候補を参照画像として採用", response.text)
            self.assertIn("画像生成モデル", response.text)
            self.assertIn("SDXL Positive Prompt", response.text)


if __name__ == "__main__":
    unittest.main()
