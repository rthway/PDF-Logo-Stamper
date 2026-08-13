"""Geometry and screen<->page coordinate conversion."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_stamper import geometry as geo
from tests import helpers


class TestFitSize(unittest.TestCase):
    def test_no_ratio_uses_box(self):
        self.assertEqual(geo.fit_size((400, 100), (200, 100), False), (200.0, 100.0))

    def test_ratio_fits_inside_box(self):
        self.assertEqual(geo.fit_size((400, 100), (200, 100), True), (200.0, 50.0))
        self.assertEqual(geo.fit_size((100, 400), (200, 100), True), (25.0, 100.0))

    def test_square_logo_in_wide_box(self):
        self.assertEqual(geo.fit_size((512, 512), (200, 100), True), (100.0, 100.0))

    def test_degenerate_inputs_do_not_crash(self):
        self.assertEqual(geo.fit_size((0, 0), (200, 100), True), (200.0, 100.0))


class TestRotatedExtent(unittest.TestCase):
    def test_no_rotation(self):
        self.assertEqual(geo.rotated_extent(200, 100, 0), (200.0, 100.0))

    def test_quarter_turn_swaps(self):
        width, height = geo.rotated_extent(200, 100, 90)
        self.assertAlmostEqual(width, 100.0, places=6)
        self.assertAlmostEqual(height, 200.0, places=6)

    def test_half_turn_identical(self):
        width, height = geo.rotated_extent(200, 100, 180)
        self.assertAlmostEqual(width, 200.0, places=6)
        self.assertAlmostEqual(height, 100.0, places=6)

    def test_45_degrees(self):
        width, height = geo.rotated_extent(100, 100, 45)
        self.assertAlmostEqual(width, 100 * math.sqrt(2), places=5)
        self.assertAlmostEqual(height, 100 * math.sqrt(2), places=5)


class TestAnchorOrigin(unittest.TestCase):
    def test_nine_anchors_on_a4(self):
        size = (200.0, 100.0)
        cases = {
            "top-left": (20.0, 20.0),
            "top-center": ((595 - 200) / 2, 20.0),
            "top-right": (595 - 200 - 20, 20.0),
            "mid-left": (20.0, (842 - 100) / 2),
            "mid-center": ((595 - 200) / 2, (842 - 100) / 2),
            "mid-right": (595 - 200 - 20, (842 - 100) / 2),
            "bottom-left": (20.0, 842 - 100 - 20),
            "bottom-center": ((595 - 200) / 2, 842 - 100 - 20),
            "bottom-right": (595 - 200 - 20, 842 - 100 - 20),
        }
        for anchor, expected in cases.items():
            with self.subTest(anchor=anchor):
                got = geo.anchor_origin(helpers.A4, size, anchor, (20, 20))
                self.assertAlmostEqual(got[0], expected[0], places=6)
                self.assertAlmostEqual(got[1], expected[1], places=6)

    def test_anchor_adapts_to_page_size(self):
        for page in (helpers.A4, helpers.LETTER, helpers.LEGAL,
                     helpers.A4_LANDSCAPE, helpers.CUSTOM):
            with self.subTest(page=page):
                x, y = geo.anchor_origin(page, (100, 50), "bottom-right", (10, 10))
                self.assertAlmostEqual(x + 100, page[0] - 10, places=6)
                self.assertAlmostEqual(y + 50, page[1] - 10, places=6)

    def test_centered_axes_ignore_margins(self):
        a = geo.anchor_origin(helpers.A4, (100, 50), "mid-center", (0, 0))
        b = geo.anchor_origin(helpers.A4, (100, 50), "mid-center", (99, 99))
        self.assertEqual(a, b)

    def test_nearest_anchor_round_trip(self):
        for _, key in geo.ANCHOR_PRESETS:
            with self.subTest(anchor=key):
                x, y = geo.anchor_origin(helpers.A4, (120, 60), key, (0, 0))
                self.assertEqual(geo.nearest_anchor(helpers.A4, (x, y, 120, 60)), key)

    def test_nearest_anchor_custom(self):
        self.assertEqual(geo.nearest_anchor(helpers.A4, (37, 91, 120, 60)),
                         geo.ANCHOR_CUSTOM)


class TestViewport(unittest.TestCase):
    def test_round_trip_at_many_zooms_and_offsets(self):
        for zoom in (0.25, 0.5, 0.7331, 1.0, 1.5, 3.0):
            for origin in ((0, 0), (13, 25), (-140, -320)):
                view = geo.Viewport(595, 842, zoom, origin[0], origin[1])
                for point in ((0, 0), (100.5, 250.25), (595, 842)):
                    with self.subTest(zoom=zoom, origin=origin, point=point):
                        canvas = view.to_canvas(*point)
                        back = view.to_page(*canvas)
                        self.assertAlmostEqual(back[0], point[0], places=6)
                        self.assertAlmostEqual(back[1], point[1], places=6)

    def test_known_mapping(self):
        view = geo.Viewport(595, 842, 0.5, 10, 20)
        self.assertEqual(view.to_canvas(100, 200), (60.0, 120.0))
        self.assertEqual(view.to_page(60, 120), (100.0, 200.0))

    def test_rect_and_lengths(self):
        view = geo.Viewport(595, 842, 2.0, 5, 5)
        self.assertEqual(view.to_canvas_rect((10, 20, 30, 40)),
                         (25.0, 45.0, 85.0, 125.0))
        self.assertEqual(view.scale(10), 20.0)
        self.assertEqual(view.to_page_length(20), 10.0)

    def test_contains_canvas_point(self):
        view = geo.Viewport(100, 100, 1.0, 0, 0)
        self.assertTrue(view.contains_canvas_point(50, 50))
        self.assertFalse(view.contains_canvas_point(-1, 50))
        self.assertFalse(view.contains_canvas_point(50, 101))

    def test_zoom_to_fit(self):
        page = helpers.A4
        fit_page = geo.zoom_to_fit(page, (600, 500), "fit-page", padding=0)
        self.assertAlmostEqual(fit_page, 500 / 842, places=6)
        fit_width = geo.zoom_to_fit(page, (600, 500), "fit-width", padding=0)
        self.assertAlmostEqual(fit_width, 600 / 595, places=6)


class TestRotationHelpers(unittest.TestCase):
    def test_rotate_point_clockwise_on_screen(self):
        # y grows downward, so +90 deg moves +x onto +y.
        x, y = geo.rotate_point(10, 0, 0, 0, 90)
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 10.0, places=6)

    def test_rotated_corners_of_square(self):
        corners = geo.rotated_corners((0, 0, 10, 10), 90)
        xs = sorted(round(c[0], 6) for c in corners)
        ys = sorted(round(c[1], 6) for c in corners)
        self.assertEqual((xs[0], xs[-1]), (0.0, 10.0))
        self.assertEqual((ys[0], ys[-1]), (0.0, 10.0))

    def test_point_in_rotated_rect(self):
        rect = (100, 100, 200, 40)
        self.assertTrue(geo.point_in_rotated_rect((150, 110), rect, 0))
        self.assertFalse(geo.point_in_rotated_rect((150, 200), rect, 0))
        # After a quarter turn the tall direction is hit instead.
        self.assertTrue(geo.point_in_rotated_rect((200, 190), rect, 90))
        self.assertFalse(geo.point_in_rotated_rect((110, 120), rect, 90))


if __name__ == "__main__":
    unittest.main()
