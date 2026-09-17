import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
VISUALIZATION_DIR = ROOT_DIR / "visualization"
if str(VISUALIZATION_DIR) not in sys.path:
    sys.path.insert(0, str(VISUALIZATION_DIR))

import generate_paper_feature_gallery as gallery


class PaperFeatureGalleryGenerationTest(unittest.TestCase):
    def test_requested_features_use_large_opening_range(self):
        for feature_name in (
            "6sides_pocket",
            "6sides_passage",
            "rectangular_passage",
            "triangular_passage",
            "triangular_pocket",
            "blind_hole",
            "h_circular_end_blind_slot",
        ):
            min_scale, max_scale = gallery.paper_shifter_range_for_feature(feature_name)

            self.assertGreaterEqual(min_scale, 0.7)
            self.assertGreaterEqual(max_scale, 0.9)

    def test_pocket_gallery_depth_is_capped_well_before_through_depth(self):
        min_depth, max_depth = gallery.paper_blind_depth_range_for_feature(
            "6sides_pocket",
            min_depth=4.0,
            max_depth=23.0,
        )

        self.assertGreaterEqual(min_depth, 4.0)
        self.assertLessEqual(max_depth, 11.5)
        self.assertLess(max_depth, 23.0)

    def test_non_target_features_keep_default_opening_range(self):
        self.assertEqual(
            gallery.paper_shifter_range_for_feature("through_hole"),
            (gallery.PAPER_SHIFTER_MIN, gallery.PAPER_SHIFTER_MAX),
        )

    def test_requested_features_prefer_top_opening_bounds(self):
        self.assertTrue(gallery.paper_prefers_top_opening("6sides_pocket"))
        self.assertTrue(gallery.paper_prefers_top_opening("triangular_passage"))
        self.assertFalse(gallery.paper_prefers_top_opening("blind_hole"))

    def test_requested_features_keep_largest_top_opening_bound(self):
        small_top = (
            (0.0, 2.0, 0.0),
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (2.0, 2.0, 0.0),
            (0.0, 0.0, -1.0),
        )
        large_top = (
            (0.0, 8.0, 0.0),
            (0.0, 0.0, 0.0),
            (8.0, 0.0, 0.0),
            (8.0, 8.0, 0.0),
            (0.0, 0.0, -1.0),
        )
        side = (
            (0.0, 0.0, 8.0),
            (0.0, 0.0, 0.0),
            (8.0, 0.0, 0.0),
            (8.0, 0.0, 8.0),
            (0.0, -1.0, 0.0),
        )

        self.assertEqual(gallery.paper_bounds_for_feature("6sides_pocket", [small_top, side, large_top]), [large_top])

    def test_requested_blind_features_keep_largest_available_bound(self):
        small = (
            (0.0, 2.0, 0.0),
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (2.0, 2.0, 0.0),
            (0.0, -1.0, 0.0),
        )
        large = (
            (0.0, 9.0, 0.0),
            (0.0, 0.0, 0.0),
            (9.0, 0.0, 0.0),
            (9.0, 9.0, 0.0),
            (0.0, -1.0, 0.0),
        )

        self.assertEqual(gallery.paper_bounds_for_feature("blind_hole", [small, large]), [large])
        self.assertEqual(gallery.paper_bounds_for_feature("h_circular_end_blind_slot", [small, large]), [large])

    def test_variable_round_gallery_uses_contrasting_radius_pair(self):
        radius_a, radius_b = gallery.paper_variable_round_radius_pair(0.4, 2.4)

        self.assertLessEqual(radius_a, 0.8)
        self.assertGreaterEqual(radius_b, 2.0)
        self.assertGreaterEqual(abs(radius_b - radius_a), 1.2)


if __name__ == "__main__":
    unittest.main()
