"""Page selection, stamp geometry, z-order and undo/redo."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_stamper import geometry as geo
from pdf_stamper.errors import AppError
from pdf_stamper.models import (History, PageSelection, Stamp, StampLayer,
                                format_page_spec, parse_page_spec)
from tests import helpers


def make_stamp(**kwargs):
    options = dict(image_path="logo.png", natural_size=(200, 100), width=200.0,
                   height=100.0, keep_ratio=False, anchor=geo.ANCHOR_CUSTOM)
    options.update(kwargs)
    return Stamp(**options)


class TestPageSpec(unittest.TestCase):
    def test_blank_and_all_mean_every_page(self):
        self.assertEqual(parse_page_spec("", 4), {0, 1, 2, 3})
        self.assertEqual(parse_page_spec("all", 4), {0, 1, 2, 3})

    def test_lists_and_ranges(self):
        self.assertEqual(parse_page_spec("1-3,5", 6), {0, 1, 2, 4})
        self.assertEqual(parse_page_spec(" 2 , 4 ", 6), {1, 3})
        self.assertEqual(parse_page_spec("4-", 6), {3, 4, 5})
        self.assertEqual(parse_page_spec("-2", 6), {0, 1})

    def test_clamped_to_document(self):
        self.assertEqual(parse_page_spec("3-99", 5), {2, 3, 4})

    def test_invalid_specs_raise_app_error(self):
        for spec in ("abc", "3-1", "0", "1;2", "-"):
            with self.subTest(spec=spec):
                with self.assertRaises(AppError):
                    parse_page_spec(spec, 5)

    def test_format_round_trip(self):
        for pages in ({0}, {0, 1, 2, 4}, {1, 3, 5}, set(range(10))):
            with self.subTest(pages=sorted(pages)):
                self.assertEqual(parse_page_spec(format_page_spec(pages), 10), pages)

    def test_format_is_compact(self):
        self.assertEqual(format_page_spec({0, 1, 2, 4}), "1-3,5")
        self.assertEqual(format_page_spec(set()), "")


class TestPageSelection(unittest.TestCase):
    def test_current_page(self):
        selection = PageSelection("current")
        self.assertEqual(selection.resolve(10, 3), {3})
        self.assertEqual(selection.resolve(10, 99), set())

    def test_all_pages(self):
        self.assertEqual(PageSelection("all").resolve(3, 0), {0, 1, 2})

    def test_range(self):
        self.assertEqual(PageSelection("range", "2-3").resolve(9, 0), {1, 2})

    def test_describe(self):
        self.assertEqual(PageSelection("current").describe(9, 2), "page 3")
        self.assertEqual(PageSelection("all").describe(9, 2), "all 9 pages")
        self.assertIn("2-3", PageSelection("range", "2-3").describe(9, 0))


class TestStampGeometry(unittest.TestCase):
    def test_custom_position_is_absolute(self):
        stamp = make_stamp(x=50.0, y=70.0)
        self.assertEqual(stamp.box_on(helpers.A4), (50.0, 70.0, 200.0, 100.0))
        # A different page size must not move a custom-positioned stamp.
        self.assertEqual(stamp.box_on(helpers.LETTER), (50.0, 70.0, 200.0, 100.0))

    def test_anchor_position_follows_page(self):
        stamp = make_stamp(anchor="bottom-right", margin_x=10.0, margin_y=10.0)
        a4 = stamp.box_on(helpers.A4)
        letter = stamp.box_on(helpers.LETTER)
        self.assertAlmostEqual(a4[0] + a4[2], 595 - 10, places=6)
        self.assertAlmostEqual(letter[1] + letter[3], 792 - 10, places=6)

    def test_keep_ratio_applies_to_box(self):
        stamp = make_stamp(width=300.0, height=300.0, keep_ratio=True)
        box = stamp.box_on(helpers.A4)
        self.assertEqual((box[2], box[3]), (300.0, 150.0))

    def test_rotated_box_keeps_centre(self):
        stamp = make_stamp(x=100.0, y=100.0, rotation=90)
        box, rotated = stamp.box_on(helpers.A4), stamp.rotated_box_on(helpers.A4)
        self.assertAlmostEqual(box[0] + box[2] / 2, rotated[0] + rotated[2] / 2)
        self.assertAlmostEqual(box[1] + box[3] / 2, rotated[1] + rotated[3] / 2)
        self.assertAlmostEqual(rotated[2], 100.0, places=6)
        self.assertAlmostEqual(rotated[3], 200.0, places=6)

    def test_move_to_switches_to_custom(self):
        stamp = make_stamp(anchor="top-left")
        stamp.move_to(33.0, 44.0)
        self.assertEqual(stamp.anchor, geo.ANCHOR_CUSTOM)
        self.assertEqual(stamp.box_on(helpers.A4)[:2], (33.0, 44.0))

    def test_copy_gets_new_identity(self):
        stamp = make_stamp()
        clone = stamp.copy()
        self.assertNotEqual(stamp.stamp_id, clone.stamp_id)
        clone.pages.mode = "current"
        self.assertEqual(stamp.pages.mode, "all")   # page selection is not shared


class TestStampLayer(unittest.TestCase):
    def setUp(self):
        self.layer = StampLayer()
        self.first = self.layer.add(make_stamp(image_path="a.png"))
        self.second = self.layer.add(make_stamp(image_path="b.png"))

    def test_add_selects_new_stamp(self):
        self.assertIs(self.layer.selected, self.second)

    def test_z_order_moves(self):
        self.assertTrue(self.layer.lower_stamp(self.second))
        self.assertEqual(self.layer.stamps, [self.second, self.first])
        self.assertTrue(self.layer.raise_stamp(self.second))
        self.assertEqual(self.layer.stamps, [self.first, self.second])
        self.assertFalse(self.layer.raise_stamp(self.second))   # already on top
        self.assertFalse(self.layer.lower_stamp(self.first))    # already at bottom

    def test_remove_moves_selection(self):
        self.layer.remove(self.second)
        self.assertIs(self.layer.selected, self.first)
        self.layer.remove(self.first)
        self.assertIsNone(self.layer.selected)

    def test_duplicate_offsets_and_selects(self):
        clone = self.layer.duplicate(self.second, offset=10)
        self.assertEqual(len(self.layer.stamps), 3)
        self.assertIs(self.layer.selected, clone)
        self.assertAlmostEqual(clone.x, self.second.x + 10)

    def test_stamps_for_page_respects_selection(self):
        self.first.pages = PageSelection("range", "1")
        self.second.pages = PageSelection("all")
        self.assertEqual(self.layer.stamps_for_page(0, 3), [self.first, self.second])
        self.assertEqual(self.layer.stamps_for_page(1, 3), [self.second])

    def test_snapshot_restore_is_deep(self):
        snapshot = self.layer.snapshot()
        self.second.x = 999.0
        self.layer.restore(snapshot)
        self.assertNotEqual(self.layer.stamps[1].x, 999.0)


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.history = History(limit=5)
        self.layer = StampLayer()
        self.history.reset(self.layer.snapshot())

    def test_starts_clean(self):
        self.assertFalse(self.history.can_undo)
        self.assertFalse(self.history.can_redo)

    def test_undo_and_redo_round_trip(self):
        self.layer.add(make_stamp(x=1.0))
        self.history.push(self.layer.snapshot())
        self.layer.add(make_stamp(x=2.0))
        self.history.push(self.layer.snapshot())
        self.assertTrue(self.history.can_undo)

        self.layer.restore(self.history.undo())
        self.assertEqual(len(self.layer.stamps), 1)
        self.layer.restore(self.history.undo())
        self.assertEqual(len(self.layer.stamps), 0)
        self.assertFalse(self.history.can_undo)

        self.layer.restore(self.history.redo())
        self.assertEqual(len(self.layer.stamps), 1)
        self.layer.restore(self.history.redo())
        self.assertEqual(len(self.layer.stamps), 2)
        self.assertFalse(self.history.can_redo)

    def test_new_action_clears_redo(self):
        self.layer.add(make_stamp())
        self.history.push(self.layer.snapshot())
        self.layer.restore(self.history.undo())
        self.assertTrue(self.history.can_redo)
        self.layer.add(make_stamp())
        self.history.push(self.layer.snapshot())
        self.assertFalse(self.history.can_redo)

    def test_identical_states_are_not_recorded(self):
        self.layer.add(make_stamp())
        self.history.push(self.layer.snapshot())
        self.history.push(self.layer.snapshot())
        self.layer.restore(self.history.undo())
        self.assertEqual(len(self.layer.stamps), 0)

    def test_limit_discards_oldest(self):
        for index in range(10):
            self.layer.add(make_stamp(x=float(index)))
            self.history.push(self.layer.snapshot())
        self.assertLessEqual(len(self.history._past), 5)
        self.assertTrue(self.history.can_undo)


if __name__ == "__main__":
    unittest.main()
