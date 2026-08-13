"""The critical guarantee: what the preview shows is where the stamp lands.

Each test drives the *same* code path the UI uses - canvas pixels through
`Viewport` into a `Stamp`, then `export_stamped_pdf` - reopens the exported file,
renders it, and measures where the ink actually is.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_stamper import geometry as geo
from pdf_stamper import image_service, pdf_service
from pdf_stamper.models import PageSelection, Stamp
from tests import helpers

RENDER_SCALE = 2.0          # render the result at 144 dpi
TOLERANCE_PX = 3.0          # ~1.5 pt of ink-edge tolerance (antialiasing included)


class ExportAccuracyBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = image_service.ImageStore()
        cls.logo = helpers.make_logo(helpers.temp_path("acc_logo.png"), (200, 100))

    def stamp_from_canvas(self, view, canvas_xy, size_pt, **kwargs):
        """Build a Stamp exactly the way a mouse drop in the canvas does."""
        x, y = view.to_page(*canvas_xy)
        return Stamp(image_path=self.logo,
                     natural_size=self.store.natural_size(self.logo),
                     x=x, y=y, width=size_pt[0], height=size_pt[1],
                     keep_ratio=False, anchor=geo.ANCHOR_CUSTOM,
                     pages=PageSelection("all"), **kwargs)

    def export(self, source, stamps, name):
        output = helpers.temp_path(name)
        pdf_service.export_stamped_pdf(source, output, stamps, store=self.store,
                                       dpi=200)
        return output

    def assert_bbox(self, measured, expected_points, msg=""):
        """Compare a measured pixel bbox with an expected point rect."""
        self.assertIsNotNone(measured, f"no stamp ink found ({msg})")
        expected = tuple(value * RENDER_SCALE for value in (
            expected_points[0], expected_points[1],
            expected_points[0] + expected_points[2],
            expected_points[1] + expected_points[3]))
        for got, want, axis in zip(measured, expected, "xyXY"):
            self.assertAlmostEqual(
                got, want, delta=TOLERANCE_PX,
                msg=f"{msg}: {axis} edge {got:.1f}px vs expected {want:.1f}px "
                    f"(measured={measured}, expected={expected})")


class TestPlacementFromCanvasCoordinates(ExportAccuracyBase):
    """Screen pixels -> preview points -> PDF points, across zooms and pages."""

    def test_dropped_position_matches_export(self):
        cases = [
            ("a4", helpers.A4, 0.7331, (13, 25)),
            ("letter", helpers.LETTER, 1.0, (0, 0)),
            ("legal", helpers.LEGAL, 0.4, (120, -340)),
            ("landscape", helpers.A4_LANDSCAPE, 1.85, (-200, 30)),
            ("custom", helpers.CUSTOM, 2.4, (7, 9)),
        ]
        for name, page, zoom, origin in cases:
            with self.subTest(page=name):
                source = helpers.make_pdf(helpers.temp_path(f"acc_{name}.pdf"),
                                          pages=1, size=page, text=False)
                view = geo.Viewport(page[0], page[1], zoom, origin[0], origin[1])
                # A drop point a third of the way into the page, in canvas pixels.
                canvas_point = view.to_canvas(page[0] / 3.0, page[1] / 4.0)
                stamp = self.stamp_from_canvas(view, canvas_point, (150.0, 75.0))
                output = self.export(source, [stamp], f"acc_out_{name}.pdf")
                image = helpers.render(output, 0, RENDER_SCALE)
                self.assert_bbox(helpers.ink_bbox(image),
                                 (stamp.x, stamp.y, 150.0, 75.0), msg=name)

    def test_all_nine_anchor_presets_land_on_their_corner(self):
        source = helpers.make_pdf(helpers.temp_path("acc_anchors.pdf"), 1,
                                  helpers.A4, text=False)
        for _, anchor in geo.ANCHOR_PRESETS:
            with self.subTest(anchor=anchor):
                stamp = Stamp(image_path=self.logo,
                              natural_size=self.store.natural_size(self.logo),
                              width=140.0, height=70.0, keep_ratio=False,
                              anchor=anchor, margin_x=24.0, margin_y=24.0,
                              pages=PageSelection("all"))
                output = self.export(source, [stamp],
                                     f"acc_anchor_{anchor}.pdf")
                image = helpers.render(output, 0, RENDER_SCALE)
                self.assert_bbox(helpers.ink_bbox(image),
                                 stamp.box_on(helpers.A4), msg=anchor)

    def test_zoom_does_not_change_the_result(self):
        """The same visual drop point at different zooms exports identically."""
        source = helpers.make_pdf(helpers.temp_path("acc_zoom.pdf"), 1, helpers.A4,
                                  text=False)
        target_point = (211.0, 377.0)
        boxes = []
        for zoom in (0.3, 1.0, 2.75):
            view = geo.Viewport(595, 842, zoom, 17, -50)
            canvas_point = view.to_canvas(*target_point)
            stamp = self.stamp_from_canvas(view, canvas_point, (120.0, 60.0))
            output = self.export(source, [stamp], f"acc_zoom_{zoom}.pdf")
            boxes.append(helpers.red_bbox(helpers.render(output, 0, RENDER_SCALE)))
            self.assertAlmostEqual(stamp.x, target_point[0], places=6)
            self.assertAlmostEqual(stamp.y, target_point[1], places=6)
        for box in boxes[1:]:
            for got, first in zip(box, boxes[0]):
                self.assertAlmostEqual(got, first, delta=TOLERANCE_PX)


class TestRotationAccuracy(ExportAccuracyBase):
    def test_rotated_extent_matches_export(self):
        source = helpers.make_pdf(helpers.temp_path("acc_rot.pdf"), 1, helpers.A4,
                                  text=False)
        for angle in (0, 15, 30, 45, 90, 135, 180, 270, 315):
            with self.subTest(angle=angle):
                stamp = Stamp(image_path=self.logo,
                              natural_size=self.store.natural_size(self.logo),
                              x=150.0, y=300.0, width=200.0, height=100.0,
                              keep_ratio=False, rotation=angle,
                              anchor=geo.ANCHOR_CUSTOM, pages=PageSelection("all"))
                output = self.export(source, [stamp], f"acc_rot_{angle}.pdf")
                image = helpers.render(output, 0, RENDER_SCALE)
                self.assert_bbox(helpers.ink_bbox(image),
                                 stamp.rotated_box_on(helpers.A4),
                                 msg=f"angle={angle}")

    def test_rotation_direction_is_clockwise_on_screen(self):
        """The corner marker must end up where the preview draws it."""
        source = helpers.make_pdf(helpers.temp_path("acc_dir.pdf"), 1, helpers.A4)
        for angle in (0, 90, 180, 270, 45):
            with self.subTest(angle=angle):
                stamp = Stamp(image_path=self.logo,
                              natural_size=self.store.natural_size(self.logo),
                              x=200.0, y=400.0, width=200.0, height=100.0,
                              keep_ratio=False, rotation=angle,
                              anchor=geo.ANCHOR_CUSTOM, pages=PageSelection("all"))
                output = self.export(source, [stamp], f"acc_dir_{angle}.pdf")
                image = helpers.render(output, 0, RENDER_SCALE)
                measured = helpers.center(helpers.blue_bbox(image))
                # Marker centre inside the unrotated stamp box, then rotated the
                # same way geometry.rotate_point rotates it for the preview.
                box = stamp.box_on(helpers.A4)
                natural = self.store.natural_size(self.logo)
                block = helpers.marker_block(natural)
                marker = (box[0] + box[2] * block / natural[0] / 2.0,
                          box[1] + box[3] * block / natural[1] / 2.0)
                cx, cy = box[0] + box[2] / 2.0, box[1] + box[3] / 2.0
                expected = geo.rotate_point(marker[0], marker[1], cx, cy, angle)
                self.assertAlmostEqual(measured[0], expected[0] * RENDER_SCALE,
                                       delta=6.0, msg=f"marker x at {angle} deg")
                self.assertAlmostEqual(measured[1], expected[1] * RENDER_SCALE,
                                       delta=6.0, msg=f"marker y at {angle} deg")


class TestPageRotationAccuracy(ExportAccuracyBase):
    """Pages carrying /Rotate must still stamp where the preview shows."""

    def test_position_on_rotated_pages(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(page_rotation=rotation):
                source = helpers.make_pdf(
                    helpers.temp_path(f"acc_pr_{rotation}.pdf"), 1, helpers.A4,
                    rotation=rotation, text=False)
                visual = pdf_service.PdfDocument(source)
                page_size = visual.page_size(0)
                visual.close()
                # Same visual spot the preview would show: 40 pt in from top-left.
                stamp = Stamp(image_path=self.logo,
                              natural_size=self.store.natural_size(self.logo),
                              x=40.0, y=40.0, width=160.0, height=80.0,
                              keep_ratio=False, anchor=geo.ANCHOR_CUSTOM,
                              pages=PageSelection("all"))
                output = self.export(source, [stamp], f"acc_pr_out_{rotation}.pdf")
                image = helpers.render(output, 0, RENDER_SCALE)
                self.assert_bbox(helpers.ink_bbox(image),
                                 stamp.box_on(page_size),
                                 msg=f"page /Rotate {rotation}")

    def test_orientation_on_rotated_pages(self):
        """The logo must be upright on screen regardless of /Rotate."""
        for rotation in (0, 90, 180, 270):
            with self.subTest(page_rotation=rotation):
                source = helpers.make_pdf(
                    helpers.temp_path(f"acc_pro_{rotation}.pdf"), 1, helpers.A4,
                    rotation=rotation)
                document = pdf_service.PdfDocument(source)
                page_size = document.page_size(0)
                document.close()
                stamp = Stamp(image_path=self.logo,
                              natural_size=self.store.natural_size(self.logo),
                              x=100.0, y=100.0, width=200.0, height=100.0,
                              keep_ratio=False, anchor=geo.ANCHOR_CUSTOM,
                              pages=PageSelection("all"))
                output = self.export(source, [stamp], f"acc_pro_out_{rotation}.pdf")
                image = helpers.render(output, 0, RENDER_SCALE)
                marker = helpers.center(helpers.blue_bbox(image))
                box = stamp.box_on(page_size)
                # Upright means the marker stays in the box's top-left quadrant.
                self.assertLess(marker[0], (box[0] + box[2] / 2) * RENDER_SCALE,
                                f"marker not on the left at /Rotate {rotation}")
                self.assertLess(marker[1], (box[1] + box[3] / 2) * RENDER_SCALE,
                                f"marker not at the top at /Rotate {rotation}")


class TestMixedPageSizes(ExportAccuracyBase):
    def test_anchor_follows_each_page_size(self):
        """One stamp, pages of different sizes: the anchor re-computes per page."""
        path = helpers.temp_path("acc_mixed.pdf")
        import pymupdf
        doc = pymupdf.open()
        sizes = [helpers.A4, helpers.LETTER, helpers.A4_LANDSCAPE, helpers.CUSTOM]
        for size in sizes:
            doc.new_page(width=size[0], height=size[1])
        doc.save(path)
        doc.close()

        stamp = Stamp(image_path=self.logo,
                      natural_size=self.store.natural_size(self.logo),
                      width=120.0, height=60.0, keep_ratio=False,
                      anchor="bottom-right", margin_x=18.0, margin_y=18.0,
                      pages=PageSelection("all"))
        output = self.export(source=path, stamps=[stamp], name="acc_mixed_out.pdf")
        for index, size in enumerate(sizes):
            with self.subTest(page=index, size=size):
                image = helpers.render(output, index, RENDER_SCALE)
                self.assert_bbox(helpers.ink_bbox(image), stamp.box_on(size),
                                 msg=f"page {index + 1} {size}")


class TestKeepAspectRatio(ExportAccuracyBase):
    def test_export_respects_aspect_lock(self):
        source = helpers.make_pdf(helpers.temp_path("acc_ratio.pdf"), 1, helpers.A4,
                                  text=False)
        stamp = Stamp(image_path=self.logo,               # logo is 200x100
                      natural_size=self.store.natural_size(self.logo),
                      x=100.0, y=100.0, width=300.0, height=300.0,
                      keep_ratio=True, anchor=geo.ANCHOR_CUSTOM,
                      pages=PageSelection("all"))
        output = self.export(source, [stamp], "acc_ratio_out.pdf")
        image = helpers.render(output, 0, RENDER_SCALE)
        box = stamp.box_on(helpers.A4)
        self.assertAlmostEqual(box[2] / box[3], 2.0, places=6)
        self.assert_bbox(helpers.ink_bbox(image), box, msg="aspect locked")


if __name__ == "__main__":
    unittest.main()
