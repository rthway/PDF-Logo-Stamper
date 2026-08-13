"""UI tests: they build the real window and synthesise real mouse/key events.

Skipped automatically when no display is available. Dialogs and file pickers are
stubbed, because the point of these tests is the editing behaviour, not Tk's own
modal machinery.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk

from pdf_stamper import config as config_module
from pdf_stamper import geometry as geo
from pdf_stamper.models import PageSelection
from tests import helpers

try:
    _probe = tk.Tk()
    _probe.destroy()
    HAS_DISPLAY = True
except Exception:                                      # noqa: BLE001
    HAS_DISPLAY = False


def event(x, y, state=0):
    """A minimal stand-in for a Tk mouse event."""
    return types.SimpleNamespace(x=x, y=y, x_root=x, y_root=y, state=state,
                                 delta=0)


@unittest.skipUnless(HAS_DISPLAY, "no display available")
class UiTestCase(unittest.TestCase):
    """Builds a real MainWindow against a synthetic PDF and logo."""

    @classmethod
    def setUpClass(cls):
        from pdf_stamper.ui import app as app_module
        cls.app_module = app_module
        cls.pdf = helpers.make_pdf(helpers.temp_path("ui_doc.pdf"), 5, helpers.A4)
        cls.wide_pdf = helpers.make_pdf(helpers.temp_path("ui_wide.pdf"), 2,
                                        helpers.A4_LANDSCAPE)
        cls.logo = helpers.make_transparent_logo(helpers.temp_path("ui_logo.png"))
        cls.tall_logo = helpers.make_logo(helpers.temp_path("ui_tall.png"), (100, 300))

    def setUp(self):
        settings = config_module.Config(helpers.temp_path("ui_settings.json"))
        settings.data.update(config_module.DEFAULTS)
        self.root = tk.Tk()
        self.root.geometry("1280x840+30+30")
        self.window = self.app_module.MainWindow(self.root, config=settings)
        self.canvas = self.window.canvas
        self.messages = []
        self._stub_dialogs()
        self.pump()

    def tearDown(self):
        try:
            if self.window.document:
                self.window.document.close()
            self.root.destroy()
        except tk.TclError:
            pass

    def pump(self, cycles=3):
        for _ in range(cycles):
            self.root.update_idletasks()
            self.root.update()

    def _stub_dialogs(self):
        module = self.app_module.dialogs
        self._real = {name: getattr(module, name)
                      for name in ("show_error", "show_info", "ask_yes_no",
                                   "MessageDialog", "ProgressDialog")}

        def show_error(parent, exc, title="error"):
            self.messages.append(("error", title, getattr(exc, "message", str(exc))))

        def show_info(parent, title, message, detail="", kind="info"):
            self.messages.append((kind, title, message))

        def ask_yes_no(parent, title, message, **kwargs):
            self.messages.append(("ask", title, message))
            return self.answer_yes_no

        class FakeMessageDialog:
            def __init__(inner, parent, title, message, detail="", kind="info",
                         buttons=("OK",), default="OK"):
                self.messages.append((kind, title, message))
                inner.default = default

            def show(inner):
                return inner.default

        class FakeProgressDialog:
            """Runs the job synchronously so tests stay deterministic."""

            def __init__(inner, parent, title, description, work, cancellable=True):
                inner.work = work

            def run(inner):
                return inner.work(lambda *args, **kwargs: None, lambda: False)

        self.answer_yes_no = True
        module.show_error = show_error
        module.show_info = show_info
        module.ask_yes_no = ask_yes_no
        module.MessageDialog = FakeMessageDialog
        module.ProgressDialog = FakeProgressDialog
        self.addCleanup(lambda: [setattr(module, name, value)
                                 for name, value in self._real.items()])

    # -- helpers ---------------------------------------------------------
    def open_document(self, path=None):
        self.assertTrue(self.window.load_pdf(path or self.pdf))
        self.pump()

    def add_stamp(self, path=None):
        self.window._add_stamp_from_path(path or self.logo)
        self.pump()
        return self.window.layer.selected

    def canvas_point_of(self, stamp, fx=0.5, fy=0.5):
        """Canvas pixel at a fractional position inside the stamp's box."""
        view = self.canvas.viewport()
        box = stamp.box_on(self.canvas.page_size())
        page_point = geo.rotate_point(box[0] + box[2] * fx, box[1] + box[3] * fy,
                                      box[0] + box[2] / 2, box[1] + box[3] / 2,
                                      stamp.rotation)
        return view.to_canvas(*page_point)

    def widget_point(self, canvas_point):
        """Canvas coordinates -> widget coordinates.

        Real Tk events carry widget coordinates and the canvas converts them with
        canvasx()/canvasy(); once the view scrolls the two differ, so tests must
        hand over widget coordinates too.
        """
        widget = self.canvas.canvas
        return (canvas_point[0] - widget.canvasx(0),
                canvas_point[1] - widget.canvasy(0))

    def press(self, canvas_point, state=0):
        self.canvas._on_press(event(*self.widget_point(canvas_point), state=state))

    def motion(self, canvas_point, state=0):
        self.canvas._on_motion(event(*self.widget_point(canvas_point), state=state))

    def release(self, canvas_point, state=0):
        self.canvas._on_release(event(*self.widget_point(canvas_point), state=state))
        self.pump()

    def click(self, canvas_point, state=0):
        self.press(canvas_point, state)
        self.release(canvas_point, state)

    def press_drag_release(self, start, offsets, state=0):
        self.press(start, state)
        for offset in offsets:
            self.motion((start[0] + offset[0], start[1] + offset[1]), state)
        self.release((start[0] + offsets[-1][0], start[1] + offsets[-1][1]), state)


class TestStartupAndDocument(UiTestCase):
    def test_starts_with_empty_state(self):
        self.assertIsNone(self.window.document)
        self.assertEqual(self.window.layer.stamps, [])
        self.assertIn("No PDF", self.window.doc_name.cget("text"))
        self.assertEqual(self.window.status.page.cget("text"), "")

    def test_opening_a_pdf_populates_the_ui(self):
        self.open_document()
        self.assertEqual(self.window.document.page_count, 5)
        self.assertIn("ui_doc.pdf", self.window.doc_name.cget("text"))
        self.assertIn("5 page", self.window.doc_meta.cget("text"))
        self.assertIn("Page 1 of 5", self.window.status.page.cget("text"))
        self.assertTrue(self.window.output_path.endswith("_stamped.pdf"))

    def test_opening_a_broken_pdf_shows_a_friendly_error(self):
        path = helpers.temp_path("ui_broken.pdf")
        with open(path, "wb") as handle:
            handle.write(b"%PDF-1.4 nope")
        self.assertFalse(self.window.load_pdf(path))
        self.assertTrue(self.messages)
        self.assertIn("Unable to open", self.messages[-1][2])
        self.assertNotIn("Traceback", self.messages[-1][2])

    def test_page_navigation(self):
        self.open_document()
        self.window.change_page(1)
        self.assertEqual(self.canvas.page_index, 1)
        self.assertEqual(self.window.page_var.get(), "2")
        self.window.page_var.set("5")
        self.window._on_page_field()
        self.assertEqual(self.canvas.page_index, 4)
        self.window.change_page(1)                     # clamped at the last page
        self.assertEqual(self.canvas.page_index, 4)
        self.window.change_page(-10)
        self.assertEqual(self.canvas.page_index, 0)

    def test_zoom_controls_and_status(self):
        self.open_document()
        start = self.canvas.zoom
        self.canvas.zoom_in()
        self.assertGreater(self.canvas.zoom, start)
        self.assertIn("%", self.window.status.zoom.cget("text"))
        self.canvas.zoom_out()
        self.canvas.fit_width()
        self.assertEqual(self.canvas.zoom_mode, "fit-width")
        self.canvas.fit_page()
        self.assertEqual(self.canvas.zoom_mode, "fit-page")
        self.assertIn("Fit page", self.window.status.zoom.cget("text"))

    def test_recent_files_menu_is_populated(self):
        self.open_document()
        labels = [self.window.recent_menu.entrycget(index, "label")
                  for index in range(self.window.recent_menu.index("end") + 1)]
        self.assertIn("ui_doc.pdf", labels)


class TestStampEditing(UiTestCase):
    def test_adding_a_stamp_selects_it_and_shows_properties(self):
        self.open_document()
        stamp = self.add_stamp()
        self.assertIsNotNone(stamp)
        self.assertIs(self.window.layer.selected, stamp)
        self.assertIn("ui_logo.png", self.window.stamp_image_label.cget("text"))
        self.assertIn("transparent", self.window.transparency_label.cget("text"))
        self.assertTrue(self.window.x_field.get() is not None)
        # A sensible default size: a quarter of the page width, aspect kept.
        box = stamp.box_on(helpers.A4)
        self.assertLess(box[2], helpers.A4[0] * 0.4)
        self.assertAlmostEqual(box[2] / box[3],
                               stamp.natural_size[0] / stamp.natural_size[1],
                               places=3)

    def test_stamp_without_document_is_refused_gracefully(self):
        self.window._add_stamp_from_path(self.logo)
        self.assertEqual(self.window.layer.stamps, [])
        self.assertIn("Open a PDF", self.window.status.message.cget("text"))

    def test_invalid_image_shows_a_friendly_error(self):
        self.open_document()
        path = helpers.temp_path("ui_corrupt.png")
        with open(path, "wb") as handle:
            handle.write(b"not an image")
        self.window._add_stamp_from_path(path)
        self.assertEqual(self.window.layer.stamps, [])
        self.assertIn("Unable to load", self.messages[-1][2])

    def test_drag_moves_the_stamp_by_the_pixel_delta(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.anchor = geo.ANCHOR_CUSTOM
        stamp.move_to(200.0, 300.0)
        self.canvas.redraw()
        before = stamp.box_on(helpers.A4)
        start = self.canvas_point_of(stamp)
        self.press_drag_release(start, [(20, 10), (60, 40)])
        after = stamp.box_on(helpers.A4)
        expected = self.canvas.viewport().to_page_length(60)
        self.assertAlmostEqual(after[0] - before[0], expected, delta=0.5)
        self.assertAlmostEqual(after[1] - before[1],
                               self.canvas.viewport().to_page_length(40), delta=0.5)
        self.assertEqual(stamp.anchor, geo.ANCHOR_CUSTOM)

    def test_shift_drag_constrains_to_one_axis(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(200.0, 300.0)
        self.canvas.redraw()
        before = stamp.box_on(helpers.A4)
        start = self.canvas_point_of(stamp)
        self.press_drag_release(start, [(80, 12)], state=0x0001)
        after = stamp.box_on(helpers.A4)
        self.assertGreater(after[0] - before[0], 1.0)
        self.assertAlmostEqual(after[1], before[1], delta=0.01)

    def test_corner_handle_resizes_and_pins_the_opposite_corner(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.keep_ratio = False
        stamp.move_to(150.0, 200.0)
        stamp.width, stamp.height = 200.0, 100.0
        self.canvas.redraw()
        view = self.canvas.viewport()
        handle = view.to_canvas(350.0, 300.0)          # south-east corner
        self.press_drag_release(handle, [(30, 20)])
        box = stamp.box_on(helpers.A4)
        self.assertAlmostEqual(box[0], 150.0, delta=0.5)     # NW pinned
        self.assertAlmostEqual(box[1], 200.0, delta=0.5)
        self.assertAlmostEqual(box[2], 200.0 + view.to_page_length(30), delta=0.6)
        self.assertAlmostEqual(box[3], 100.0 + view.to_page_length(20), delta=0.6)

    def test_edge_handle_resizes_one_axis_only(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.keep_ratio = False
        stamp.move_to(150.0, 200.0)
        stamp.width, stamp.height = 200.0, 100.0
        self.canvas.redraw()
        view = self.canvas.viewport()
        handle = view.to_canvas(350.0, 250.0)          # east edge midpoint
        self.press_drag_release(handle, [(40, 35)])
        box = stamp.box_on(helpers.A4)
        self.assertAlmostEqual(box[3], 100.0, delta=0.5, msg="height must not change")
        self.assertAlmostEqual(box[2], 200.0 + view.to_page_length(40), delta=0.6)
        self.assertAlmostEqual(box[1], 200.0, delta=0.5)

    def test_resize_keeps_aspect_ratio_when_locked(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.keep_ratio = True
        stamp.move_to(100.0, 100.0)
        stamp.width, stamp.height = 200.0, 100.0
        self.canvas.redraw()
        view = self.canvas.viewport()
        self.press_drag_release(view.to_canvas(300.0, 200.0), [(60, 4)])
        box = stamp.box_on(helpers.A4)
        self.assertAlmostEqual(box[2] / box[3], 2.0, places=2)

    def test_resize_cannot_go_below_the_minimum(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.keep_ratio = False
        stamp.move_to(200.0, 200.0)
        stamp.width, stamp.height = 120.0, 60.0
        self.canvas.redraw()
        view = self.canvas.viewport()
        self.press_drag_release(view.to_canvas(320.0, 260.0), [(-400, -400)])
        self.assertGreaterEqual(stamp.width, 8.0)
        self.assertGreaterEqual(stamp.height, 8.0)

    def test_rotation_handle_rotates_the_stamp(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(200.0, 300.0)
        stamp.width, stamp.height = 200.0, 100.0
        self.canvas.redraw()
        handle = self.canvas._rotate_handle_pos
        centre = self.canvas.viewport().to_canvas(300.0, 350.0)
        # Drag the handle a quarter turn clockwise: to the right of the centre.
        radius = centre[1] - handle[1]
        self.press(handle)
        self.motion((centre[0] + radius, centre[1]))
        self.release((centre[0] + radius, centre[1]))
        self.assertAlmostEqual(stamp.rotation, 90.0, delta=2.0)

    def test_shift_rotation_snaps_to_15_degrees(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(200.0, 300.0)
        self.canvas.redraw()
        handle = self.canvas._rotate_handle_pos
        box = stamp.box_on(helpers.A4)
        centre = self.canvas.viewport().to_canvas(box[0] + box[2] / 2,
                                                 box[1] + box[3] / 2)
        self.press(handle, state=0x0001)
        self.motion((centre[0] + 60, centre[1] - 20), state=0x0001)
        self.release((centre[0] + 60, centre[1] - 20), state=0x0001)
        self.assertAlmostEqual(stamp.rotation % 15, 0, places=6)

    def test_click_selects_topmost_and_empty_space_deselects(self):
        self.open_document()
        first = self.add_stamp()
        first.move_to(100.0, 100.0)
        second = self.add_stamp(self.tall_logo)
        second.move_to(110.0, 110.0)
        self.canvas.redraw()
        self.click(self.canvas.viewport().to_canvas(150.0, 150.0))
        self.assertIs(self.window.layer.selected, second, "topmost wins")
        self.click(self.canvas.viewport().to_canvas(560.0, 800.0))
        self.assertIsNone(self.window.layer.selected)

    def test_arrow_keys_nudge_only_the_canvas(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(200.0, 200.0)
        self.canvas.redraw()
        self.canvas._nudge((1, 0), 1)
        self.assertAlmostEqual(stamp.box_on(helpers.A4)[0], 201.0, delta=0.001)
        self.canvas._nudge((0, 1), 10)
        self.assertAlmostEqual(stamp.box_on(helpers.A4)[1], 210.0, delta=0.001)

    def test_typing_in_a_field_does_not_move_the_stamp(self):
        """Regression: arrows used to be bound to the window, not the canvas."""
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(200.0, 200.0)
        self.canvas.redraw()
        before = stamp.box_on(helpers.A4)
        self.window.width_field.spin.focus_set()
        self.pump()
        self.window.width_field.spin.event_generate("<Left>")
        self.window.width_field.spin.event_generate("<Right>")
        self.pump()
        self.assertEqual(stamp.box_on(helpers.A4)[:2], before[:2])

    def test_delete_and_duplicate(self):
        self.open_document()
        stamp = self.add_stamp()
        self.window.duplicate_stamp()
        self.assertEqual(len(self.window.layer.stamps), 2)
        self.window.delete_stamp()
        self.assertEqual(len(self.window.layer.stamps), 1)
        self.window.delete_stamp()
        self.assertEqual(self.window.layer.stamps, [])
        self.window.delete_stamp()                     # nothing selected
        self.assertIn("Select a stamp", self.window.status.message.cget("text"))
        del stamp

    def test_z_order_buttons(self):
        self.open_document()
        first = self.add_stamp()
        second = self.add_stamp(self.tall_logo)
        self.assertEqual(self.window.layer.stamps, [first, second])
        self.window.send_backward()
        self.assertEqual(self.window.layer.stamps, [second, first])
        self.window.bring_forward()
        self.assertEqual(self.window.layer.stamps, [first, second])

    def test_property_fields_drive_the_model(self):
        self.open_document()
        stamp = self.add_stamp()
        self.window.x_field.var.set("120")
        self.window.y_field.var.set("240")
        self.pump()
        box = stamp.box_on(helpers.A4)
        self.assertAlmostEqual(box[0], 120.0, delta=0.01)
        self.assertAlmostEqual(box[1], 240.0, delta=0.01)

        stamp.keep_ratio = False
        self.window.keep_ratio_var.set(False)
        self.window.width_field.var.set("250")
        self.window.height_field.var.set("125")
        self.pump()
        self.assertAlmostEqual(stamp.width, 250.0, delta=0.01)
        self.assertAlmostEqual(stamp.height, 125.0, delta=0.01)

        self.window.rotation_field.var.set("45")
        self.pump()
        self.assertAlmostEqual(stamp.rotation, 45.0, delta=0.01)

        self.window.opacity_var.set(60)
        self.window._on_opacity_slider()
        self.assertEqual(stamp.opacity, 60)
        self.assertIn("60", self.window.opacity_label.cget("text"))

    def test_invalid_field_text_is_rejected_not_silently_defaulted(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(150.0, 150.0)
        self.window.x_field.set(150.0)
        self.pump()
        self.window.x_field.var.set("abc")
        self.pump()
        self.assertAlmostEqual(stamp.box_on(helpers.A4)[0], 150.0, delta=0.01)
        self.assertEqual(str(self.window.x_field.spin.cget("foreground")),
                         "#DC2626")

    def test_presets_and_margins(self):
        self.open_document()
        stamp = self.add_stamp()
        self.window.margin_x_field.set(30)
        self.window.margin_y_field.set(30)
        self.window.apply_preset("top-right")
        box = stamp.box_on(helpers.A4)
        self.assertAlmostEqual(box[0] + box[2], helpers.A4[0] - 30, delta=0.01)
        self.assertAlmostEqual(box[1], 30.0, delta=0.01)
        self.assertEqual(str(self.window.preset_buttons["top-right"].cget("style")),
                         "Primary.TButton")

    def test_preset_adapts_to_a_different_page_size(self):
        self.open_document(self.wide_pdf)
        stamp = self.add_stamp()
        self.window.margin_x_field.set(20)
        self.window.margin_y_field.set(20)
        self.window.apply_preset("bottom-right")
        box = stamp.box_on(helpers.A4_LANDSCAPE)
        self.assertAlmostEqual(box[0] + box[2], helpers.A4_LANDSCAPE[0] - 20,
                               delta=0.01)
        self.assertAlmostEqual(box[1] + box[3], helpers.A4_LANDSCAPE[1] - 20,
                               delta=0.01)

    def test_centre_and_reset_size(self):
        self.open_document()
        stamp = self.add_stamp()
        self.window.centre_stamp()
        box = stamp.box_on(helpers.A4)
        self.assertAlmostEqual(box[0] + box[2] / 2, helpers.A4[0] / 2, delta=0.01)
        self.assertAlmostEqual(box[1] + box[3] / 2, helpers.A4[1] / 2, delta=0.01)
        self.window.reset_stamp_size()
        self.assertAlmostEqual(stamp.width / stamp.height,
                               stamp.natural_size[0] / stamp.natural_size[1],
                               places=3)

    def test_snapping_to_page_centre(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.keep_ratio = False
        stamp.width, stamp.height = 100.0, 50.0
        centre_x = (helpers.A4[0] - 100) / 2
        stamp.move_to(centre_x + 8, 400.0)
        self.canvas.redraw()
        start = self.canvas_point_of(stamp)
        # Nudge a couple of pixels: within the snap radius it should lock to centre.
        self.press_drag_release(start, [(-2, 0)])
        self.assertAlmostEqual(stamp.box_on(helpers.A4)[0], centre_x, delta=0.5)


class TestPageSelectionUi(UiTestCase):
    def test_apply_to_modes_update_the_selected_stamp(self):
        self.open_document()
        stamp = self.add_stamp()
        self.window.page_mode.set("current")
        self.window._on_page_mode()
        self.assertEqual(stamp.pages.mode, "current")
        self.assertEqual(str(self.window.range_entry.cget("state")), "disabled")

        self.window.page_mode.set("range")
        self.window.range_var.set("2-4")
        self.window._on_page_mode()
        self.assertEqual(stamp.pages.spec, "2-4")
        self.assertEqual(stamp.pages.resolve(5, 0), {1, 2, 3})
        self.assertEqual(str(self.window.range_entry.cget("state")), "normal")
        self.assertIn("3 of 5", self.window.pages_summary.cget("text"))

    def test_invalid_range_is_reported_not_crashed(self):
        self.open_document()
        self.add_stamp()
        self.window.page_mode.set("range")
        self.window.range_var.set("9-2")
        self.window._on_page_mode()
        self.assertEqual(str(self.window.pages_summary.cget("style")),
                         "Danger.TLabel")

    def test_stamp_list_shows_page_scope(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.pages = PageSelection("range", "1-2")
        self.window._refresh_stamp_tree()
        values = self.window.stamp_tree.item(str(stamp.stamp_id), "values")
        self.assertIn("1-2", values[0])


class TestUndoRedo(UiTestCase):
    def test_undo_redo_across_add_move_resize_delete(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(100.0, 100.0)
        self.canvas.redraw()
        self.window._commit_change("moved")
        stamp.width = 300.0
        self.window._commit_change("resized")
        self.window.delete_stamp()
        self.assertEqual(self.window.layer.stamps, [])

        self.window.undo()                             # delete
        self.assertEqual(len(self.window.layer.stamps), 1)
        self.assertAlmostEqual(self.window.layer.stamps[0].width, 300.0, delta=0.01)
        self.window.undo()                             # resize
        self.assertLess(self.window.layer.stamps[0].width, 300.0)
        self.window.undo()                             # move
        self.window.undo()                             # add
        self.assertEqual(self.window.layer.stamps, [])
        self.window.redo()
        self.assertEqual(len(self.window.layer.stamps), 1)

    def test_undo_button_states_follow_history(self):
        self.open_document()
        self.assertFalse(self.window.buttons["undo"]._enabled)
        self.add_stamp()
        self.assertTrue(self.window.buttons["undo"]._enabled)
        self.assertFalse(self.window.buttons["redo"]._enabled)
        self.window.undo()
        self.assertTrue(self.window.buttons["redo"]._enabled)

    def test_drag_creates_exactly_one_undo_step(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(200.0, 200.0)
        self.window._commit_change()          # baseline the position first
        depth = len(self.window.history._past)
        start = self.canvas_point_of(stamp)
        self.press_drag_release(start, [(10, 0), (20, 0), (30, 0)])
        self.assertEqual(len(self.window.history._past), depth + 1)
        self.window.undo()
        # Undo restores deep copies, so read the position back from the layer.
        restored = self.window.layer.stamps[0]
        self.assertAlmostEqual(restored.box_on(helpers.A4)[0], 200.0, delta=0.6)


class TestSaving(UiTestCase):
    def test_save_writes_the_file_and_reports(self):
        self.open_document()
        stamp = self.add_stamp()
        stamp.move_to(120.0, 240.0)
        output = helpers.temp_path("ui_saved.pdf")
        self.window.output_path = output
        if os.path.exists(output):
            os.remove(output)
        self.window.save()
        self.pump()
        self.assertTrue(os.path.exists(output))
        import pymupdf
        with pymupdf.open(output) as doc:
            self.assertEqual(doc.page_count, 5)
            self.assertTrue(doc[0].get_images())
        self.assertFalse(self.window.dirty)
        self.assertIn("Saved", self.window.status.message.cget("text"))

    def test_save_without_stamps_is_refused(self):
        self.open_document()
        self.window.save()
        self.assertTrue(any("Nothing to save" in message[1]
                            for message in self.messages))

    def test_overwrite_asks_first_and_cancel_keeps_the_file(self):
        self.open_document()
        self.add_stamp()
        output = helpers.temp_path("ui_existing.pdf")
        with open(output, "wb") as handle:
            handle.write(b"original bytes")
        self.window.output_path = output
        self.answer_yes_no = False
        self.window.save()
        with open(output, "rb") as handle:
            self.assertEqual(handle.read(), b"original bytes")
        self.assertTrue(any(message[0] == "ask" for message in self.messages))

    def test_saving_over_the_source_asks_and_then_reopens(self):
        source = helpers.make_pdf(helpers.temp_path("ui_inplace.pdf"), 2, helpers.A4)
        self.open_document(source)
        self.add_stamp()
        self.window.output_path = source
        self.answer_yes_no = True
        self.window.save()
        self.pump()
        self.assertIsNotNone(self.window.document, "document must be reopened")
        self.assertEqual(self.window.document.page_count, 2)
        import pymupdf
        with pymupdf.open(source) as doc:
            self.assertTrue(doc[0].get_images())

    def test_exported_position_matches_the_preview(self):
        """End-to-end: drag in the UI, save, and measure the exported ink."""
        self.open_document()
        stamp = self.add_stamp(helpers.make_logo(helpers.temp_path("ui_solid.png"),
                                                 (200, 100)))
        stamp.keep_ratio = False
        stamp.width, stamp.height = 180.0, 90.0
        stamp.move_to(90.0, 120.0)
        stamp.opacity = 100
        self.canvas.redraw()
        start = self.canvas_point_of(stamp)
        self.press_drag_release(start, [(70, 55)])
        box = stamp.box_on(helpers.A4)

        output = helpers.temp_path("ui_accuracy.pdf")
        self.window.output_path = output
        if os.path.exists(output):
            os.remove(output)
        self.window.save()
        self.pump()
        image = helpers.render(output, 0, 2.0)
        measured = helpers.red_bbox(image)
        self.assertIsNotNone(measured)
        for got, want in zip(measured, (box[0] * 2, box[1] * 2,
                                        (box[0] + box[2]) * 2,
                                        (box[1] + box[3]) * 2)):
            self.assertAlmostEqual(got, want, delta=3.0)


class TestRemoveExistingStamps(UiTestCase):
    def test_removes_stamps_from_a_saved_file(self):
        source = helpers.make_pdf(helpers.temp_path("ui_rm_src.pdf"), 3, helpers.A4)
        self.open_document(source)
        self.add_stamp(helpers.make_logo(helpers.temp_path("ui_rm_logo.png")))
        stamped = helpers.temp_path("ui_rm_stamped.pdf")
        self.window.output_path = stamped
        self.window.save()
        self.pump()
        self.open_document(stamped)

        module = self.app_module.dialogs
        cleaned = helpers.temp_path("ui_rm_clean.pdf")

        class FakeRemoveDialog:
            def __init__(inner, parent, page_count, current_page=0):
                pass

            def show(inner):
                return ("1", True)

        original_dialog = module.RemoveStampsDialog
        original_save = self.app_module.filedialog.asksaveasfilename
        module.RemoveStampsDialog = FakeRemoveDialog
        self.app_module.filedialog.asksaveasfilename = lambda **kwargs: cleaned
        try:
            self.window.remove_existing_stamps()
        finally:
            module.RemoveStampsDialog = original_dialog
            self.app_module.filedialog.asksaveasfilename = original_save

        self.assertTrue(os.path.exists(cleaned))
        import pymupdf
        with pymupdf.open(cleaned) as doc:
            names = {info[7] for info in doc[0].get_images(full=True)}
            streams = b" ".join(doc.xref_stream(x) for x in doc[0].get_contents())
            self.assertFalse(any(f"/{name} Do".encode() in streams
                                 for name in names), "page 1 still draws a stamp")
            self.assertIn("Test page 1", doc[0].get_text())


class TestBatchUi(UiTestCase):
    def test_batch_runs_over_a_folder(self):
        folder = os.path.join(helpers.temp_dir(), "ui_batch_in")
        output = os.path.join(helpers.temp_dir(), "ui_batch_out")
        os.makedirs(folder, exist_ok=True)
        if os.path.isdir(output):            # numbered names accumulate otherwise
            import shutil
            shutil.rmtree(output)
        for name in ("alpha.pdf", "beta.pdf"):
            helpers.make_pdf(os.path.join(folder, name), 1, helpers.A4)
        self.open_document()
        self.add_stamp()

        module = self.app_module.dialogs
        recorded = {}

        class FakeBatchDialog:
            def __init__(inner, parent, summary, config, pick_folder):
                recorded["summary"] = summary

            def show(inner):
                return {"input": folder, "output": output, "suffix": "_stamped",
                        "recursive": False}

        class FakeResults:
            def __init__(inner, parent, results):
                recorded["results"] = results

            def show(inner):
                return None

        original = (module.BatchDialog, module.BatchResultsDialog)
        module.BatchDialog, module.BatchResultsDialog = FakeBatchDialog, FakeResults
        try:
            self.window.run_batch()
        finally:
            module.BatchDialog, module.BatchResultsDialog = original

        self.assertIn("ui_logo.png", recorded["summary"])
        self.assertEqual(len(recorded["results"]), 2)
        self.assertTrue(all(result.ok for result in recorded["results"]))
        self.assertEqual(len(os.listdir(output)), 2)

    def test_batch_without_stamps_explains_itself(self):
        self.open_document()
        self.window.run_batch()
        self.assertTrue(any("Add a stamp first" in message[1]
                            for message in self.messages))


if __name__ == "__main__":
    unittest.main()


class TestEmptyStateAndDnd(UiTestCase):
    def test_empty_workspace_tells_the_user_what_to_do(self):
        self.pump(4)
        texts = [self.canvas.canvas.itemcget(item, "text")
                 for item in self.canvas.canvas.find_all()
                 if self.canvas.canvas.type(item) == "text"]
        self.assertTrue(any("No document open" in text for text in texts), texts)
        self.assertTrue(any("Open PDF" in text for text in texts), texts)

    def test_drop_handler_opens_pdfs_and_adds_images(self):
        payload = types.SimpleNamespace(data="{%s}" % self.pdf, action="copy")
        self.window._on_drop(payload)
        self.assertIsNotNone(self.window.document)
        payload = types.SimpleNamespace(data="{%s}" % self.logo, action="copy")
        self.window._on_drop(payload)
        self.assertEqual(len(self.window.layer.stamps), 1)

    def test_drop_of_an_unsupported_file_is_ignored(self):
        path = helpers.temp_path("ui_notes.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("hello")
        self.window._on_drop(types.SimpleNamespace(data="{%s}" % path, action="copy"))
        self.assertIsNone(self.window.document)
        self.assertEqual(self.window.layer.stamps, [])


class TestShortcutsAndMenus(UiTestCase):
    def test_documented_shortcuts_are_registered(self):
        expected = ("<Control-o>", "<Control-l>", "<Control-s>", "<Control-Shift-S>",
                    "<Control-z>", "<Control-y>", "<Control-d>", "<Control-plus>",
                    "<Control-minus>", "<Control-Key-0>", "<Control-Key-1>",
                    "<Next>", "<Prior>", "<F1>")
        for sequence in expected:
            with self.subTest(sequence=sequence):
                self.assertTrue(self.root.bind_all(sequence),
                                f"{sequence} is not bound")

    def test_delete_is_bound_to_the_canvas_not_the_window(self):
        self.assertTrue(self.canvas.canvas.bind("<Delete>"))
        self.assertFalse(self.root.bind_all("<Delete>"))

    def test_context_menu_offers_the_documented_actions(self):
        labels = [self.window.context_menu.entrycget(index, "label")
                  for index in range(self.window.context_menu.index("end") + 1)
                  if self.window.context_menu.type(index) != "separator"]
        for expected in ("Duplicate", "Delete", "Bring forward", "Send backward",
                         "Centre on page", "Reset size", "Reset rotation"):
            self.assertIn(expected, labels)

    def test_menubar_has_the_expected_top_level_menus(self):
        menubar = self.root.nametowidget(self.root.cget("menu"))
        # On Windows index 0 is the window's system menu, which has no label.
        labels = [menubar.entrycget(index, "label")
                  for index in range(menubar.index("end") + 1)
                  if menubar.type(index) == "cascade"]
        self.assertEqual(labels, ["File", "Edit", "View", "Tools", "Help"])

    def test_toolbar_buttons_have_tooltips(self):
        for key, button in self.window.buttons.items():
            with self.subTest(button=key):
                self.assertTrue(button.button.bind("<Enter>"),
                                f"{key} has no hover/tooltip binding")
