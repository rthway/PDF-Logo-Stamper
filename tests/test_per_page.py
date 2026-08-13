"""Per-page control: skip a page, or give one page its own position / size / logo."""

import os
import sys
import unittest

import pymupdf
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_stamper import geometry as geo
from pdf_stamper import image_service, pdf_service
from pdf_stamper.errors import AppError
from pdf_stamper.models import PageSelection, Stamp
from tests import helpers
from tests.test_ui import UiTestCase

GREEN = (30, 170, 60, 255)


def make_green_logo(path, size=(200, 100)):
    Image.new("RGBA", size, GREEN).save(path)
    return path


def green_bbox(image):
    from PIL import ImageChops
    channels = dict(zip("rgb", image.split()))
    mask = None
    for name, test in (("r", lambda v: v < 120), ("g", lambda v: v > 120),
                       ("b", lambda v: v < 120)):
        layer = channels[name].point(lambda v, t=test: 255 if t(v) else 0).convert("1")
        mask = layer if mask is None else ImageChops.logical_and(mask, layer)
    return mask.getbbox()


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

class TestSkippedPages(unittest.TestCase):
    def test_skip_removes_pages_from_the_selection(self):
        selection = PageSelection("all", skip="2,4")
        self.assertEqual(selection.resolve(5, 0), {0, 2, 4})

    def test_skip_applies_to_ranges_too(self):
        selection = PageSelection("range", "1-5", skip="3")
        self.assertEqual(selection.resolve(8, 0), {0, 1, 3, 4})

    def test_skip_can_empty_the_selection(self):
        self.assertEqual(PageSelection("current", skip="1").resolve(3, 0), set())

    def test_toggle_round_trip(self):
        selection = PageSelection("all")
        self.assertTrue(selection.toggle_skipped(2, 6))
        self.assertEqual(selection.skip, "3")
        self.assertTrue(selection.is_skipped(2, 6))
        self.assertFalse(selection.toggle_skipped(2, 6))
        self.assertEqual(selection.skip, "")
        self.assertFalse(selection.is_skipped(2, 6))

    def test_skip_list_stays_compact(self):
        selection = PageSelection("all")
        for page in (1, 2, 3, 7):
            selection.set_skipped(page, True, 10)
        self.assertEqual(selection.skip, "2-4,8")

    def test_describe_mentions_skipped_pages(self):
        selection = PageSelection("all", skip="3")
        self.assertIn("skip 3", selection.describe(5, 0))
        self.assertIn("all 5 pages", selection.describe(5, 0))

    def test_invalid_skip_is_reported_but_never_crashes_display(self):
        selection = PageSelection("all", skip="9-2")
        self.assertFalse(selection.is_valid(5))
        self.assertEqual(selection.resolve_or_empty(5, 0), set())
        self.assertEqual(selection.describe(5, 0), "invalid page numbers")
        with self.assertRaises(AppError):
            selection.resolve(5, 0)


class TestStampOverrides(unittest.TestCase):
    def setUp(self):
        self.stamp = Stamp(image_path="logo.png", natural_size=(200, 100),
                           width=200.0, height=100.0, keep_ratio=False,
                           anchor="bottom-right", margin_x=20.0, margin_y=20.0,
                           pages=PageSelection("all"))

    def test_no_override_means_shared_values(self):
        shared = self.stamp.box_on(helpers.A4)
        self.assertEqual(self.stamp.box_on(helpers.A4, 3), shared)
        self.assertFalse(self.stamp.has_override(3))

    def test_customise_freezes_the_current_appearance(self):
        shared = self.stamp.box_on(helpers.A4)
        self.stamp.customise(3, helpers.A4)
        self.assertTrue(self.stamp.has_override(3))
        # Nothing moves at the moment of customising.
        for got, want in zip(self.stamp.box_on(helpers.A4, 3), shared):
            self.assertAlmostEqual(got, want, places=6)
        # And it is pinned, so it no longer follows the anchor.
        self.assertEqual(self.stamp.value_for("anchor", 3), geo.ANCHOR_CUSTOM)

    def test_editing_a_custom_page_leaves_the_others_alone(self):
        self.stamp.customise(3, helpers.A4)
        self.stamp.move_to(10.0, 20.0, page_index=3)
        self.assertEqual(self.stamp.box_on(helpers.A4, 3)[:2], (10.0, 20.0))
        shared = self.stamp.box_on(helpers.A4, 0)
        self.assertAlmostEqual(shared[0], 595 - 200 - 20, places=6)
        self.assertNotEqual(shared[:2], (10.0, 20.0))

    def test_editing_a_shared_page_leaves_custom_pages_alone(self):
        self.stamp.customise(3, helpers.A4)
        self.stamp.move_to(10.0, 20.0, page_index=3)
        self.stamp.move_to(300.0, 400.0)              # shared edit
        self.assertEqual(self.stamp.box_on(helpers.A4, 0)[:2], (300.0, 400.0))
        self.assertEqual(self.stamp.box_on(helpers.A4, 3)[:2], (10.0, 20.0))

    def test_per_page_size_rotation_and_opacity(self):
        self.stamp.customise(2, helpers.A4)
        self.stamp.set_values({"width": 50.0, "height": 25.0, "rotation": 45.0,
                               "opacity": 40}, page_index=2)
        self.assertEqual(self.stamp.box_on(helpers.A4, 2)[2:], (50.0, 25.0))
        self.assertEqual(self.stamp.value_for("rotation", 2), 45.0)
        self.assertEqual(self.stamp.value_for("opacity", 2), 40)
        self.assertEqual(self.stamp.value_for("rotation", 0), 0.0)
        self.assertEqual(self.stamp.value_for("opacity", 0), 100)
        rotated = self.stamp.rotated_box_on(helpers.A4, 2)
        self.assertAlmostEqual(rotated[2], geo.rotated_extent(50, 25, 45)[0],
                               places=6)

    def test_per_page_image(self):
        self.stamp.customise(1, helpers.A4)
        self.stamp.set_values({"image_path": "other.png",
                               "natural_size": (300, 300)}, page_index=1)
        self.assertEqual(self.stamp.image_for(1), "other.png")
        self.assertEqual(self.stamp.name_for(1), "other.png")
        self.assertEqual(self.stamp.image_for(0), "logo.png")
        self.assertEqual(self.stamp.natural_for(1), (300, 300))

    def test_keep_ratio_uses_the_page_image_aspect(self):
        self.stamp.keep_ratio = True
        self.stamp.customise(1, helpers.A4)
        self.stamp.set_values({"image_path": "square.png", "natural_size": (300, 300),
                               "width": 120.0, "height": 120.0}, page_index=1)
        box = self.stamp.box_on(helpers.A4, 1)
        self.assertAlmostEqual(box[2] / box[3], 1.0, places=6)
        shared = self.stamp.box_on(helpers.A4, 0)
        self.assertAlmostEqual(shared[2] / shared[3], 2.0, places=6)

    def test_clear_override_returns_the_page_to_shared(self):
        self.stamp.customise(3, helpers.A4)
        self.stamp.move_to(10.0, 20.0, page_index=3)
        self.assertTrue(self.stamp.clear_override(3))
        self.assertEqual(self.stamp.box_on(helpers.A4, 3),
                         self.stamp.box_on(helpers.A4, 0))
        self.assertFalse(self.stamp.clear_override(3))

    def test_custom_pages_listing(self):
        self.stamp.customise(4, helpers.A4)
        self.stamp.customise(1, helpers.A4)
        self.assertEqual(self.stamp.custom_pages, [1, 4])

    def test_copy_does_not_share_overrides(self):
        self.stamp.customise(2, helpers.A4)
        clone = self.stamp.copy()
        clone.move_to(1.0, 2.0, page_index=2)
        self.assertNotEqual(self.stamp.box_on(helpers.A4, 2)[:2], (1.0, 2.0))


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

class TestPerPageExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = image_service.ImageStore()
        cls.red = helpers.make_logo(helpers.temp_path("pp_red.png"), (200, 100))
        cls.green = make_green_logo(helpers.temp_path("pp_green.png"), (200, 100))

    def base_stamp(self, **kwargs):
        options = dict(image_path=self.red, natural_size=(200, 100),
                       x=60.0, y=80.0, width=160.0, height=80.0, keep_ratio=False,
                       anchor=geo.ANCHOR_CUSTOM, pages=PageSelection("all"))
        options.update(kwargs)
        return Stamp(**options)

    def export(self, source, stamps, name, current_page=0):
        output = helpers.temp_path(name)
        summary = pdf_service.export_stamped_pdf(source, output, stamps,
                                                 store=self.store, dpi=200,
                                                 current_page=current_page)
        return output, summary

    def test_skipped_pages_are_not_stamped(self):
        source = helpers.make_pdf(helpers.temp_path("pp_skip.pdf"), 5, helpers.A4,
                                  text=False)
        stamp = self.base_stamp(pages=PageSelection("all", skip="2,4"))
        output, summary = self.export(source, [stamp], "pp_skip_out.pdf")
        self.assertEqual(summary["pages"], 3)
        with pymupdf.open(output) as doc:
            stamped = {index for index in range(5) if doc[index].get_images()}
        self.assertEqual(stamped, {0, 2, 4})

    def test_skipping_every_page_is_refused_with_an_explanation(self):
        source = helpers.make_pdf(helpers.temp_path("pp_none.pdf"), 2, helpers.A4)
        stamp = self.base_stamp(pages=PageSelection("all", skip="1-2"))
        with self.assertRaises(AppError) as caught:
            self.export(source, [stamp], "pp_none_out.pdf")
        self.assertIn("page selection is empty", caught.exception.message)

    def test_one_page_gets_its_own_position(self):
        source = helpers.make_pdf(helpers.temp_path("pp_pos.pdf"), 3, helpers.A4,
                                  text=False)
        stamp = self.base_stamp()
        stamp.customise(1, helpers.A4)
        stamp.move_to(320.0, 600.0, page_index=1)
        output, _ = self.export(source, [stamp], "pp_pos_out.pdf")

        shared = stamp.box_on(helpers.A4, 0)
        custom = stamp.box_on(helpers.A4, 1)
        for page, box in ((0, shared), (1, custom), (2, shared)):
            with self.subTest(page=page):
                measured = helpers.ink_bbox(helpers.render(output, page, 2.0))
                self.assertIsNotNone(measured)
                for got, want in zip(measured, (box[0] * 2, box[1] * 2,
                                                (box[0] + box[2]) * 2,
                                                (box[1] + box[3]) * 2)):
                    self.assertAlmostEqual(got, want, delta=3.0)

    def test_one_page_gets_its_own_image(self):
        source = helpers.make_pdf(helpers.temp_path("pp_img.pdf"), 3, helpers.A4,
                                  text=False)
        stamp = self.base_stamp()
        stamp.customise(2, helpers.A4)
        stamp.set_values({"image_path": self.green, "natural_size": (200, 100)},
                         page_index=2)
        output, _ = self.export(source, [stamp], "pp_img_out.pdf")

        first = helpers.render(output, 0, 2.0)
        self.assertIsNotNone(helpers.red_bbox(first))
        self.assertIsNone(green_bbox(first))
        third = helpers.render(output, 2, 2.0)
        self.assertIsNotNone(green_bbox(third))
        self.assertIsNone(helpers.red_bbox(third))

    def test_one_page_gets_its_own_size_rotation_and_opacity(self):
        source = helpers.make_pdf(helpers.temp_path("pp_geom.pdf"), 2, helpers.A4,
                                  text=False)
        stamp = self.base_stamp()
        stamp.customise(1, helpers.A4)
        stamp.set_values({"width": 240.0, "height": 60.0, "rotation": 30.0,
                          "opacity": 50}, page_index=1)
        output, _ = self.export(source, [stamp], "pp_geom_out.pdf")

        for page in (0, 1):
            with self.subTest(page=page):
                box = stamp.rotated_box_on(helpers.A4, page)
                measured = helpers.ink_bbox(helpers.render(output, page, 2.0))
                for got, want in zip(measured, (box[0] * 2, box[1] * 2,
                                                (box[0] + box[2]) * 2,
                                                (box[1] + box[3]) * 2)):
                    self.assertAlmostEqual(got, want, delta=3.0)
        with pymupdf.open(output) as doc:      # two distinct embedded bitmaps
            self.assertNotEqual(doc[0].get_images(full=True)[0][0],
                                doc[1].get_images(full=True)[0][0])

    def test_overrides_and_skips_combine(self):
        source = helpers.make_pdf(helpers.temp_path("pp_combo.pdf"), 4, helpers.A4,
                                  text=False)
        stamp = self.base_stamp(pages=PageSelection("all", skip="2"))
        stamp.customise(3, helpers.A4)
        stamp.set_values({"image_path": self.green, "natural_size": (200, 100)},
                         page_index=3)
        output, summary = self.export(source, [stamp], "pp_combo_out.pdf")
        self.assertEqual(summary["pages"], 3)
        self.assertIsNotNone(helpers.red_bbox(helpers.render(output, 0, 2.0)))
        self.assertIsNone(helpers.ink_bbox(helpers.render(output, 1, 2.0)))
        self.assertIsNotNone(helpers.red_bbox(helpers.render(output, 2, 2.0)))
        self.assertIsNotNone(green_bbox(helpers.render(output, 3, 2.0)))

    def test_a_custom_page_on_a_different_page_size(self):
        path = helpers.temp_path("pp_sizes.pdf")
        doc = pymupdf.open()
        for size in (helpers.A4, helpers.LETTER):
            doc.new_page(width=size[0], height=size[1])
        doc.save(path)
        doc.close()
        stamp = self.base_stamp(anchor="bottom-right", margin_x=20.0, margin_y=20.0)
        stamp.customise(1, helpers.LETTER)
        stamp.move_to(30.0, 40.0, page_index=1)
        output, _ = self.export(path, [stamp], "pp_sizes_out.pdf")

        anchored = stamp.box_on(helpers.A4, 0)
        measured = helpers.ink_bbox(helpers.render(output, 0, 2.0))
        self.assertAlmostEqual(measured[2], (anchored[0] + anchored[2]) * 2, delta=3)
        custom = helpers.ink_bbox(helpers.render(output, 1, 2.0))
        self.assertAlmostEqual(custom[0], 30.0 * 2, delta=3)
        self.assertAlmostEqual(custom[1], 40.0 * 2, delta=3)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class TestPerPageUi(UiTestCase):
    def test_skip_button_toggles_the_current_page(self):
        self.open_document()
        stamp = self.add_stamp()
        self.window.set_page = getattr(self.window, "set_page", None)
        self.window.page_var.set("3")
        self.window._on_page_field()
        self.pump()
        self.window.toggle_skip_page()
        self.assertEqual(stamp.pages.skip, "3")
        self.assertEqual(stamp.pages.resolve(5, 2), {0, 1, 3, 4})
        self.assertIn("skipped on page 3", self.window.status.message.cget("text"))
        self.assertIn("skipped", self.window.page_state_label.cget("text"))
        self.window.toggle_skip_page()
        self.assertEqual(stamp.pages.skip, "")

    def test_skip_field_edits_the_selected_stamp(self):
        self.open_document()
        stamp = self.add_stamp()
        self.window.skip_var.set("2,4")
        self.pump()
        self.assertEqual(stamp.pages.skip, "2,4")
        self.assertEqual(stamp.pages.resolve(5, 0), {0, 2, 4})
        self.assertIn("3 of 5", self.window.pages_summary.cget("text"))

    def test_invalid_skip_field_does_not_crash_the_preview(self):
        self.open_document()
        self.add_stamp()
        self.window.skip_var.set("9-2")
        self.pump()
        self.canvas.redraw()
        self.assertEqual(str(self.window.pages_summary.cget("style")),
                         "Danger.TLabel")

    def test_customise_then_edit_only_affects_that_page(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.keep_ratio = False
        stamp.width, stamp.height = 150.0, 75.0
        stamp.move_to(100.0, 150.0)
        self.window.page_var.set("2")
        self.window._on_page_field()
        self.pump()

        self.window.toggle_customise_page()
        self.assertTrue(stamp.has_override(1))
        self.assertIn("its own position", self.window.page_state_label.cget("text"))

        view = self.canvas.viewport_for(1)
        start = view.to_canvas(100.0 + 75.0, 150.0 + 37.5)
        self.press_drag_release(start, [(40, 30)])
        self.assertAlmostEqual(stamp.box_on(helpers.A4, 1)[0],
                               100.0 + view.to_page_length(40), delta=0.6)
        self.assertAlmostEqual(stamp.box_on(helpers.A4, 0)[0], 100.0, delta=0.01,
                               msg="other pages must not move")

    def test_property_fields_edit_only_the_custom_page(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.keep_ratio = False
        stamp.move_to(100.0, 100.0)
        self.window.page_var.set("2")
        self.window._on_page_field()
        self.pump()
        self.window.toggle_customise_page()
        self.window.x_field.var.set("300")
        self.window.rotation_field.var.set("25")
        self.window.opacity_var.set(40)
        self.window._on_opacity_slider()
        self.pump()
        self.assertAlmostEqual(stamp.box_on(helpers.A4, 1)[0], 300.0, delta=0.01)
        self.assertAlmostEqual(stamp.value_for("rotation", 1), 25.0, delta=0.01)
        self.assertEqual(stamp.value_for("opacity", 1), 40)
        self.assertAlmostEqual(stamp.box_on(helpers.A4, 0)[0], 100.0, delta=0.01)
        self.assertEqual(stamp.value_for("rotation", 0), 0.0)
        self.assertEqual(stamp.value_for("opacity", 0), 100)

    def test_reset_puts_the_page_back_under_shared_settings(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(100.0, 100.0)
        self.window.page_var.set("2")
        self.window._on_page_field()
        self.window.toggle_customise_page()
        stamp.move_to(400.0, 500.0, page_index=1)
        self.window.toggle_customise_page()             # button now resets
        self.assertFalse(stamp.has_override(1))
        self.assertEqual(stamp.box_on(helpers.A4, 1), stamp.box_on(helpers.A4, 0))
        self.assertIn("Shared", self.window.page_state_label.cget("text"))

    def test_different_image_on_one_page(self):
        self.open_document()
        stamp = self.add_stamp()
        other = make_green_logo(helpers.temp_path("pp_ui_green.png"))
        original = self.app_module.filedialog.askopenfilename
        self.app_module.filedialog.askopenfilename = lambda **kwargs: other
        try:
            self.window.page_var.set("3")
            self.window._on_page_field()
            self.window.replace_page_image()
        finally:
            self.app_module.filedialog.askopenfilename = original
        self.assertTrue(stamp.has_override(2))
        self.assertEqual(stamp.image_for(2), other)
        self.assertNotEqual(stamp.image_for(0), other)
        self.assertIn("pp_ui_green.png", self.window.stamp_image_label.cget("text"))

    def test_stamp_list_shows_skips_and_custom_pages(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.pages.skip = "2"
        stamp.customise(3, helpers.A4)
        self.window._refresh_stamp_tree()
        scope = self.window.stamp_tree.item(str(stamp.stamp_id), "values")[0]
        self.assertIn("skip 2", scope)
        self.assertIn("1 custom", scope)

    def test_undo_restores_skip_and_customisation(self):
        self.open_document()
        stamp = self.add_stamp()
        self.window.toggle_skip_page()
        self.assertTrue(self.window.layer.stamps[0].pages.is_skipped(0, 5))
        self.window.undo()
        self.assertFalse(self.window.layer.stamps[0].pages.is_skipped(0, 5))

        self.window.toggle_customise_page()
        self.assertTrue(self.window.layer.stamps[0].has_override(0))
        self.window.undo()
        self.assertFalse(self.window.layer.stamps[0].has_override(0))
        self.window.redo()
        self.assertTrue(self.window.layer.stamps[0].has_override(0))
        del stamp

    def test_context_menu_exposes_the_per_page_actions(self):
        labels = [self.window.context_menu.entrycget(index, "label")
                  for index in range(self.window.context_menu.index("end") + 1)
                  if self.window.context_menu.type(index) != "separator"]
        self.assertIn("Skip on this page", labels)
        self.assertIn("Customise for this page", labels)

    def test_saving_writes_skips_and_per_page_edits(self):
        self.open_document()
        stamp = self.add_stamp(helpers.make_logo(helpers.temp_path("pp_ui_red.png"),
                                                (200, 100)))
        stamp.keep_ratio = False
        stamp.width, stamp.height = 150.0, 75.0
        stamp.move_to(80.0, 120.0)
        stamp.opacity = 100
        stamp.pages.set_skipped(1, True, 5)             # skip page 2
        stamp.customise(2, helpers.A4)                  # page 3 is different
        stamp.move_to(300.0, 500.0, page_index=2)

        output = helpers.temp_path("pp_ui_out.pdf")
        self.window.output_path = output
        if os.path.exists(output):
            os.remove(output)
        self.window.save()
        self.pump()

        self.assertTrue(os.path.exists(output))
        with pymupdf.open(output) as doc:
            self.assertFalse(doc[1].get_images(), "page 2 was skipped")
            self.assertTrue(doc[0].get_images())
        shared = stamp.box_on(helpers.A4, 0)
        custom = stamp.box_on(helpers.A4, 2)
        first = helpers.red_bbox(helpers.render(output, 0, 2.0))
        third = helpers.red_bbox(helpers.render(output, 2, 2.0))
        self.assertAlmostEqual(first[0], shared[0] * 2, delta=3)
        self.assertAlmostEqual(third[0], custom[0] * 2, delta=3)
        self.assertAlmostEqual(third[1], custom[1] * 2, delta=3)

    def test_skipped_page_shows_a_badge_in_the_preview(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.pages.set_skipped(0, True, 5)
        self.canvas.redraw()
        self.pump()
        texts = [self.canvas.canvas.itemcget(item, "text")
                 for item in self.canvas.canvas.find_all()
                 if self.canvas.canvas.type(item) == "text"]
        self.assertTrue(any("skipped" in text for text in texts), texts)

    def test_custom_page_shows_a_badge_in_the_preview(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.customise(0, helpers.A4)
        self.canvas.redraw()
        self.pump()
        texts = [self.canvas.canvas.itemcget(item, "text")
                 for item in self.canvas.canvas.find_all()
                 if self.canvas.canvas.type(item) == "text"]
        self.assertTrue(any("custom for this page" in text for text in texts), texts)

    def test_per_page_controls_are_disabled_without_a_selection(self):
        self.open_document()
        self.assertIn("disabled", self.window.skip_page_button.state())
        self.add_stamp()
        self.assertNotIn("disabled", self.window.skip_page_button.state())
        self.window.delete_stamp()
        self.assertIn("disabled", self.window.customise_button.state())


if __name__ == "__main__":
    unittest.main()
