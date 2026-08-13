"""Continuous multi-page scrolling: reach every page, and edit on any of them."""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_stamper.models import PageSelection
from tests import helpers
from tests.test_ui import UiTestCase


class TestContinuousScrolling(UiTestCase):
    """Every page must be reachable by scrolling, and editable where it lands."""

    def wheel(self, notches):
        """Spin the wheel `notches` times (positive = downwards)."""
        for _ in range(abs(notches)):
            self.canvas._on_wheel(types.SimpleNamespace(
                x=400, y=300, delta=-120 if notches > 0 else 120, state=0))
        self.canvas._after_scroll()
        self.pump()

    def test_all_pages_are_laid_out_in_one_strip(self):
        self.open_document()
        layout = self.canvas._ensure_layout()
        self.assertEqual(len(layout["origins"]), 5)
        tops = [layout["origins"][index][1] for index in range(5)]
        self.assertEqual(tops, sorted(tops), "pages must stack downwards")
        for index in range(4):
            gap = tops[index + 1] - (tops[index] + layout["heights"][index])
            self.assertGreater(gap, 0, "pages must not overlap")

    def test_scrolling_reaches_the_last_page(self):
        self.open_document()
        self.assertEqual(self.canvas.page_index, 0)
        self.canvas.canvas.yview_moveto(1.0)
        self.canvas._after_scroll()
        self.pump()
        self.assertEqual(self.canvas.page_index, 4)
        self.assertIn(4, self.canvas._visible_pages)
        self.assertIn("Page 5 of 5", self.window.status.page.cget("text"))
        self.assertEqual(self.window.page_var.get(), "5")

    def test_mouse_wheel_moves_past_the_bottom_of_a_page(self):
        """The old behaviour stopped at the end of page 1; it must not now."""
        self.open_document()
        start = self.canvas.canvas.canvasy(0)
        self.wheel(40)
        self.assertGreater(self.canvas.canvas.canvasy(0), start)
        self.assertGreater(self.canvas.page_index, 0,
                           "wheel scrolling should carry on into later pages")

    def test_scroll_updates_the_sidebar_and_stamp_scope(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.pages = PageSelection("current")
        self.window._refresh_stamp_tree()
        self.assertIn("page 1",
                      self.window.stamp_tree.item(str(stamp.stamp_id), "values")[0])
        self.canvas.canvas.yview_moveto(1.0)
        self.canvas._after_scroll()
        self.pump()
        self.assertIn("page 5",
                      self.window.stamp_tree.item(str(stamp.stamp_id), "values")[0])

    def test_page_field_and_buttons_scroll_the_strip(self):
        self.open_document()
        top_before = self.canvas.canvas.canvasy(0)
        self.window.page_var.set("4")
        self.window._on_page_field()
        self.pump()
        self.assertEqual(self.canvas.page_index, 3)
        self.assertGreater(self.canvas.canvas.canvasy(0), top_before)
        self.assertIn(3, self.canvas._visible_pages)
        self.window.change_page(-1)
        self.pump()
        self.assertEqual(self.canvas.page_index, 2)
        self.assertIn(2, self.canvas._visible_pages)

    def test_only_visible_pages_are_rendered(self):
        """A long document must not rasterise every page up front."""
        long_pdf = helpers.make_pdf(helpers.temp_path("ui_long.pdf"), 40, helpers.A4)
        self.open_document(long_pdf)
        self.assertLessEqual(len(self.canvas._visible_pages), 6)
        self.assertLessEqual(len(self.canvas._page_photos), 6)
        self.assertIn(0, self.canvas._visible_pages)

    def test_stamp_is_shown_on_every_visible_page_it_applies_to(self):
        self.open_document()
        self.canvas.set_zoom(0.25)
        self.pump()
        stamp = self.add_stamp()
        stamp.pages = PageSelection("all")
        self.canvas.redraw()
        self.pump()
        drawn = [key for key in self.canvas._stamp_photos if key[0] == stamp.stamp_id]
        self.assertGreater(len(drawn), 1,
                           "the stamp should be visible on each visible page")
        self.assertEqual({key[1] for key in drawn}, set(self.canvas._visible_pages))

    def test_dragging_the_stamp_on_a_later_page_works(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.keep_ratio = False
        stamp.width, stamp.height = 150.0, 75.0
        stamp.move_to(120.0, 200.0)
        self.window.page_var.set("3")
        self.window._on_page_field()
        self.pump()
        self.assertEqual(self.canvas.page_index, 2)

        view = self.canvas.viewport_for(2)
        start = view.to_canvas(120.0 + 75.0, 200.0 + 37.5)   # centre of the stamp
        self.press_drag_release(start, [(25, 15)])
        box = stamp.box_on(helpers.A4)
        self.assertAlmostEqual(box[0], 120.0 + view.to_page_length(25), delta=0.6)
        self.assertAlmostEqual(box[1], 200.0 + view.to_page_length(15), delta=0.6)

    def test_clicking_a_stamp_on_another_page_makes_that_page_current(self):
        self.open_document()
        self.canvas.set_zoom(0.25)              # several pages visible at once
        self.pump()
        stamp = self.add_stamp()
        stamp.move_to(100.0, 100.0)
        self.canvas.redraw()
        self.pump()
        later = max(self.canvas._visible_pages)
        self.assertGreater(later, 0, "need more than one page in view")
        view = self.canvas.viewport_for(later)
        box = stamp.box_on(self.canvas.page_size(later))
        self.click(view.to_canvas(box[0] + box[2] / 2, box[1] + box[3] / 2))
        self.assertEqual(self.canvas.page_index, later)
        self.assertIs(self.window.layer.selected, stamp)

    def test_handles_follow_the_current_page(self):
        self.open_document()
        self.canvas.set_zoom(0.25)
        self.pump()
        stamp = self.add_stamp()
        stamp.move_to(100.0, 100.0)
        self.canvas.redraw()
        first = dict(self.canvas._handle_positions)
        self.assertTrue(first)
        later = max(self.canvas._visible_pages)
        self.canvas._set_current_page(later)
        self.canvas.redraw()
        self.pump()
        self.assertNotAlmostEqual(first["nw"][1],
                                  self.canvas._handle_positions["nw"][1],
                                  delta=1.0,
                                  msg="handles should move to the current page")
        del stamp

    def test_editing_after_scrolling_still_exports_to_the_right_place(self):
        """The whole point: scroll to a page, adjust there, and the file matches."""
        self.open_document()
        stamp = self.add_stamp(helpers.make_logo(helpers.temp_path("scroll_logo.png"),
                                                (200, 100)))
        stamp.keep_ratio = False
        stamp.width, stamp.height = 160.0, 80.0
        stamp.opacity = 100
        stamp.pages = PageSelection("all")
        self.window.page_var.set("4")
        self.window._on_page_field()
        self.pump()
        view = self.canvas.viewport_for(3)
        box = stamp.box_on(helpers.A4)
        start = view.to_canvas(box[0] + box[2] / 2, box[1] + box[3] / 2)
        self.press_drag_release(start, [(-40, -60)])
        placed = stamp.box_on(helpers.A4)

        output = helpers.temp_path("scroll_out.pdf")
        self.window.output_path = output
        if os.path.exists(output):
            os.remove(output)
        self.window.save()
        self.pump()
        for page in (0, 3, 4):
            with self.subTest(page=page):
                measured = helpers.red_bbox(helpers.render(output, page, 2.0))
                self.assertIsNotNone(measured)
                for got, want in zip(measured, (placed[0] * 2, placed[1] * 2,
                                                (placed[0] + placed[2]) * 2,
                                                (placed[1] + placed[3]) * 2)):
                    self.assertAlmostEqual(got, want, delta=3.0)

    def test_home_and_end_jump_to_the_first_and_last_page(self):
        self.open_document()
        self.canvas.scroll_to_page(self.window.document.page_count - 1)
        self.canvas._after_scroll()
        self.pump()
        self.assertEqual(self.canvas.page_index, 4)
        self.canvas.scroll_to_page(0)
        self.canvas._after_scroll()
        self.pump()
        self.assertEqual(self.canvas.page_index, 0)

    def test_mixed_page_sizes_are_centred_individually(self):
        import pymupdf
        path = helpers.temp_path("ui_mixed_strip.pdf")
        doc = pymupdf.open()
        for size in (helpers.A4, helpers.A4_LANDSCAPE, helpers.LETTER):
            doc.new_page(width=size[0], height=size[1])
        doc.save(path)
        doc.close()
        self.open_document(path)
        layout = self.canvas._ensure_layout()
        centres = [layout["origins"][index][0] + layout["widths"][index] / 2
                   for index in range(3)]
        for centre in centres[1:]:
            self.assertAlmostEqual(centre, centres[0], delta=0.6)


if __name__ == "__main__":
    unittest.main()
