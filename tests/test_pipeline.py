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


if __name__ == "__main__":
    unittest.main()
