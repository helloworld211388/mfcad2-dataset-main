import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from visualization.feature_viewer_common import (
    classify_tricolor_face,
    load_and_validate_label_json,
    resolve_label_json_path,
    temporary_parameter_overrides,
)
import Utils.parameters as param


class FeatureViewerCommonTest(unittest.TestCase):
    def test_resolve_label_json_same_directory(self):
        with TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "Chamfer.step"
            json_path = Path(tmp) / "Chamfer.json"
            step_path.write_text("", encoding="utf8")
            json_path.write_text('{"cls": {}, "seg": [], "bottom": {}}', encoding="utf8")

            self.assertEqual(resolve_label_json_path(step_path), json_path)

    def test_resolve_label_json_paper_gallery_layout(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "paper_feature_gallery"
            step_dir = root / "steps"
            label_dir = root / "labels"
            step_dir.mkdir(parents=True)
            label_dir.mkdir()
            step_path = step_dir / "Through_hole.step"
            json_path = label_dir / "Through_hole.json"
            step_path.write_text("", encoding="utf8")
            json_path.write_text('{"cls": {}, "seg": [], "bottom": {}}', encoding="utf8")

            self.assertEqual(resolve_label_json_path(step_path), json_path)

    def test_missing_label_json_raises(self):
        with TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "Blind_hole.step"
            step_path.write_text("", encoding="utf8")

            with self.assertRaisesRegex(FileNotFoundError, "Missing label JSON"):
                resolve_label_json_path(step_path)

    def test_load_and_validate_label_json_requires_bottom_count(self):
        with TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "Rectangular_pocket.json"
            json_path.write_text(
                json.dumps({"cls": {"0": 14}, "seg": [[0]], "bottom": {"0": 1}}),
                encoding="utf8",
            )

            labels = load_and_validate_label_json(json_path, expected_face_count=1)
            self.assertEqual(labels["bottom"], {"0": 1})

            with self.assertRaisesRegex(ValueError, "face count"):
                load_and_validate_label_json(json_path, expected_face_count=2)

    def test_classify_tricolor_face(self):
        self.assertEqual(classify_tricolor_face(14, 14, 1), "bottom")
        self.assertEqual(classify_tricolor_face(14, 14, 0), "feature")
        self.assertEqual(classify_tricolor_face(27, 14, 0), "stock")

    def test_load_and_validate_label_json_requires_all_keys(self):
        with TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "bad.json"
            json_path.write_text(json.dumps({"cls": {}, "bottom": {}}), encoding="utf8")

            with self.assertRaisesRegex(ValueError, "missing 'seg'"):
                load_and_validate_label_json(json_path, expected_face_count=0)

    def test_temporary_parameter_overrides_restore_values(self):
        original = param.stock_min_x
        with temporary_parameter_overrides({"stock_min_x": original + 10.0}):
            self.assertEqual(param.stock_min_x, original + 10.0)
        self.assertEqual(param.stock_min_x, original)


if __name__ == "__main__":
    unittest.main()
