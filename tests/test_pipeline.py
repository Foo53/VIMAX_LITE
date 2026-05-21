from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vimax_lite.cli import main
from vimax_lite.manual_workflow import build_character_reference_sheet, build_manual_prompt, image_counts, prepare_manual_image_workflow
from vimax_lite.models import ProductionBrief, ProductionDesign
from vimax_lite.providers import MockProvider


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
            self.assertIn("Create one consistent character reference image", prompt)
            self.assertIn("small white delivery robot", prompt)
            self.assertIn("yellow rain poncho", prompt)
            self.assertNotIn("配達ロボット", prompt)


if __name__ == "__main__":
    unittest.main()
