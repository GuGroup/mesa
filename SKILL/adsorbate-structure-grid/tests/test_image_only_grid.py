import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "build_grid_figure", SCRIPTS / "build_grid_figure.py"
)
GRID = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GRID
SPEC.loader.exec_module(GRID)


class TableGridTests(unittest.TestCase):
    def test_compose_grid_emits_table_headers_but_not_caption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "cell.png"
            Image.new("RGBA", (20, 20), (200, 80, 40, 255)).save(image_path)
            output = tmp_path / "grid.svg"

            manifest = {
                "panel_label": "Figure 1",
                "caption": "This caption must not be drawn.",
                "rows": [{"label": "Pt(111)"}],
                "cols": [{"label": "H*"}],
            }

            GRID.compose_grid(
                manifest,
                [[image_path]],
                dict(GRID.LAYOUT_DEFAULTS),
                [output],
            )

            svg = output.read_text(encoding="utf-8")
            self.assertNotIn("Figure 1", svg)
            self.assertNotIn("This caption must not be drawn.", svg)
            self.assertIn("Pt(111)", svg)
            self.assertIn("H*", svg)
            self.assertIn("#272727", svg)


if __name__ == "__main__":
    unittest.main()
