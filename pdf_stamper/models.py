"""Application state: stamps, page selection and undo/redo.

Pure data + logic, no Tkinter and no PyMuPDF, so it is cheap to test.
"""

import copy
import itertools
import os
from dataclasses import dataclass, field, replace

from . import geometry
from .errors import AppError

_ids = itertools.count(1)

# Page-selection modes offered in the UI.
PAGE_MODES = (
    ("Current page", "current"),
    ("All pages", "all"),
    ("Page range", "range"),
)


def parse_page_spec(spec, page_count):
    """Parse '1-3, 5, 9-' into a set of 0-based page numbers.

    Blank (or 'all') means every page. Raises AppError on malformed input so the
    UI can show the message directly.
    """
    text = (spec or "").strip()
    if not text or text.lower() == "all":
        return set(range(page_count))

    pages = set()
    for chunk in text.replace(" ", "").split(","):
        if not chunk:
            continue
        try:
            if "-" in chunk:
                start, _, end = chunk.partition("-")
                if not start and not end:
                    raise ValueError("open-ended on both sides")
                first = int(start) if start else 1
                last = int(end) if end else page_count
            else:
                first = last = int(chunk)
        except ValueError:
            raise AppError(f"'{chunk}' is not a valid page or page range.\n\n"
                           f"Use pages like 1, 3 or ranges like 2-5.")
        if first < 1 or last < first:
            raise AppError(f"'{chunk}' is not a valid page range.\n\n"
                           f"The first page must be 1 or higher, and ranges must "
                           f"count upwards.")
        pages.update(range(first - 1, min(last, page_count)))
    return pages


def format_page_spec(pages):
    """Turn 0-based page numbers into a compact '1-3,5' string."""
    numbers = sorted(page + 1 for page in pages)
    if not numbers:
        return ""
    parts, start, previous = [], numbers[0], numbers[0]
    for number in numbers[1:] + [None]:
        if number == previous + 1:
            previous = number
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = number
    return ",".join(parts)


@dataclass
class PageSelection:
    """Which pages a stamp applies to, minus any the user chose to skip."""

    mode: str = "all"           # current | all | range
    spec: str = ""              # used when mode == 'range'
    skip: str = ""              # pages to leave alone, e.g. "1, 4-5"

    def base_pages(self, page_count, current_page=0):
        if self.mode == "current":
            return {current_page} if 0 <= current_page < page_count else set()
        if self.mode == "range":
            return parse_page_spec(self.spec, page_count)
        return set(range(page_count))

    def skipped_pages(self, page_count):
        text = (self.skip or "").strip()
        if not text:
            return set()
        return parse_page_spec(text, page_count)

    def resolve(self, page_count, current_page=0):
        """Pages this selection covers. Raises AppError on a malformed range."""
        return self.base_pages(page_count, current_page) - \
            self.skipped_pages(page_count)

    # -- skipping individual pages ---------------------------------------
    def is_skipped(self, page_index, page_count=None):
        try:
            return page_index in self.skipped_pages(
                page_count if page_count is not None else page_index + 1)
        except AppError:
            return False

    def set_skipped(self, page_index, skipped, page_count):
        """Add or remove one page from the skip list, keeping it tidy."""
        try:
            pages = self.skipped_pages(page_count)
        except AppError:
            pages = set()
        if skipped:
            pages.add(page_index)
        else:
            pages.discard(page_index)
        self.skip = format_page_spec(pages)
        return self.skip

    def toggle_skipped(self, page_index, page_count):
        skipped = self.is_skipped(page_index, page_count)
        self.set_skipped(page_index, not skipped, page_count)
        return not skipped

    def resolve_or_empty(self, page_count, current_page=0):
        """Like resolve(), but never raises.

        The preview must keep drawing while the user is still halfway through
        typing a range, so display code uses this and only the export reports the
        error.
        """
        try:
            return self.resolve(page_count, current_page)
        except AppError:
            return set()

    def is_valid(self, page_count=1):
        try:
            self.resolve(page_count, 0)
            return True
        except AppError:
            return False

    def describe(self, page_count, current_page=0):
        if not self.is_valid(page_count):
            return "invalid page numbers"
        skipped = self.skipped_pages(page_count) & \
            self.base_pages(page_count, current_page)
        suffix = f", skip {format_page_spec(skipped)}" if skipped else ""
        if self.mode == "current":
            return f"page {current_page + 1}{suffix}"
        if self.mode == "range":
            pages = self.resolve(page_count, current_page)
            return f"pages {format_page_spec(pages) or '-'}"
        return f"all {page_count} pages{suffix}"


@dataclass
class Stamp:
    """One logo placement, stored in visual page points (top-left origin).

    x/y/width/height describe the *unrotated* box; `rotation` then spins it about
    its own centre. When `anchor` is a preset the box is re-anchored per page, so
    the same stamp lands correctly on mixed page sizes; dragging switches the
    stamp to 'custom' and pins the exact coordinates.
    """

    image_path: str
    natural_size: tuple = (1, 1)     # pixels of the source image
    x: float = 0.0
    y: float = 0.0
    width: float = 160.0
    height: float = 80.0
    rotation: float = 0.0
    opacity: int = 100
    keep_ratio: bool = True
    anchor: str = geometry.ANCHOR_CUSTOM
    margin_x: float = 24.0
    margin_y: float = 24.0
    pages: PageSelection = field(default_factory=PageSelection)
    # Per-page exceptions: {page index: {field: value}}. A page listed here keeps
    # its own position / size / rotation / opacity / image, and is unaffected by
    # later edits to the shared settings.
    overrides: dict = field(default_factory=dict)
    stamp_id: int = field(default_factory=lambda: next(_ids))

    # -- derived ---------------------------------------------------------
    @property
    def name(self):
        return os.path.basename(self.image_path) or "stamp"

    @property
    def center(self):
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    @property
    def custom_pages(self):
        return sorted(self.overrides)

    # -- per-page values -------------------------------------------------
    def has_override(self, page_index):
        return page_index in self.overrides

    def value_for(self, name, page_index=None):
        """The value of `name` on a page: its override, else the shared setting."""
        if page_index is not None:
            override = self.overrides.get(page_index)
            if override and name in override:
                return override[name]
        return getattr(self, name)

    def image_for(self, page_index=None):
        return self.value_for("image_path", page_index)

    def natural_for(self, page_index=None):
        return self.value_for("natural_size", page_index)

    def name_for(self, page_index=None):
        return os.path.basename(self.image_for(page_index)) or "stamp"

    def customise(self, page_index, page_size):
        """Start treating `page_index` separately, freezing how it looks today."""
        if page_index in self.overrides:
            return self.overrides[page_index]
        x, y, width, height = self.box_on(page_size)
        self.overrides[page_index] = {
            "anchor": geometry.ANCHOR_CUSTOM, "x": x, "y": y,
            "width": width, "height": height, "rotation": self.rotation,
            "opacity": self.opacity, "image_path": self.image_path,
            "natural_size": tuple(self.natural_size),
        }
        return self.overrides[page_index]

    def clear_override(self, page_index):
        """Put a page back under the shared settings."""
        return self.overrides.pop(page_index, None) is not None

    def set_values(self, values, page_index=None):
        """Write values to a page's override when it has one, else to the shared
        settings. This is what makes "edit only page 4" work with the same drag,
        resize and field-entry code paths."""
        if page_index is not None and page_index in self.overrides:
            self.overrides[page_index].update(values)
        else:
            for name, value in values.items():
                setattr(self, name, value)

    # -- geometry --------------------------------------------------------
    def box_on(self, page_size, page_index=None):
        """(x, y, w, h) of the unrotated box on a page of `page_size`."""
        width = self.value_for("width", page_index)
        height = self.value_for("height", page_index)
        if self.keep_ratio:
            width, height = geometry.fit_size(self.natural_for(page_index),
                                             (width, height), True)
        anchor = self.value_for("anchor", page_index)
        if anchor in geometry.ANCHOR_KEYS:
            x, y = geometry.anchor_origin(
                page_size, (width, height), anchor,
                (self.value_for("margin_x", page_index),
                 self.value_for("margin_y", page_index)))
        else:
            x, y = self.value_for("x", page_index), self.value_for("y", page_index)
        return (x, y, width, height)

    def rotated_box_on(self, page_size, page_index=None):
        """Axis-aligned box that the rotated stamp occupies (visual points)."""
        x, y, width, height = self.box_on(page_size, page_index)
        rotation = self.value_for("rotation", page_index)
        extent_w, extent_h = geometry.rotated_extent(width, height, rotation)
        cx, cy = x + width / 2.0, y + height / 2.0
        return (cx - extent_w / 2.0, cy - extent_h / 2.0, extent_w, extent_h)

    def move_to(self, x, y, page_index=None):
        self.set_values({"anchor": geometry.ANCHOR_CUSTOM,
                         "x": float(x), "y": float(y)}, page_index)

    def set_center(self, cx, cy, page_size=None, page_index=None):
        width, height = self.box_on(page_size or (0, 0), page_index)[2:] \
            if page_size else (self.value_for("width", page_index),
                               self.value_for("height", page_index))
        self.move_to(cx - width / 2.0, cy - height / 2.0, page_index)

    def copy(self):
        # The page selection and the per-page overrides must not be shared with
        # the original, or editing the copy would change both.
        return replace(self, stamp_id=next(_ids), pages=replace(self.pages),
                       overrides=copy.deepcopy(self.overrides))


class History:
    """Undo/redo over whole-state snapshots.

    Snapshots are small (a handful of dataclasses) and immune to the ordering
    bugs that per-action inverse commands invite.
    """

    def __init__(self, limit=60):
        self.limit = limit
        self._past = []
        self._future = []

    def reset(self, state):
        self._past = [copy.deepcopy(state)]
        self._future.clear()

    def push(self, state):
        """Record a new current state (called after each completed action)."""
        snapshot = copy.deepcopy(state)
        if self._past and snapshot == self._past[-1]:
            return
        self._past.append(snapshot)
        if len(self._past) > self.limit:
            self._past.pop(0)
        self._future.clear()

    @property
    def can_undo(self):
        return len(self._past) > 1

    @property
    def can_redo(self):
        return bool(self._future)

    def undo(self):
        if not self.can_undo:
            return None
        self._future.append(self._past.pop())
        return copy.deepcopy(self._past[-1])

    def redo(self):
        if not self._future:
            return None
        state = self._future.pop()
        self._past.append(state)
        return copy.deepcopy(state)


class StampLayer:
    """The ordered list of stamps on the document, plus the current selection.

    List order is z-order: later stamps paint on top.
    """

    def __init__(self):
        self.stamps = []
        self.selected_id = None

    # -- state snapshots for undo/redo -----------------------------------
    def snapshot(self):
        return copy.deepcopy(self.stamps)

    def restore(self, snapshot):
        self.stamps = copy.deepcopy(snapshot)
        if not any(stamp.stamp_id == self.selected_id for stamp in self.stamps):
            self.selected_id = self.stamps[-1].stamp_id if self.stamps else None

    # -- queries ---------------------------------------------------------
    @property
    def selected(self):
        for stamp in self.stamps:
            if stamp.stamp_id == self.selected_id:
                return stamp
        return None

    def index_of(self, stamp):
        return self.stamps.index(stamp)

    def stamps_for_page(self, page_index, page_count):
        """Stamps whose page selection includes `page_index` (current = its own page)."""
        return [stamp for stamp in self.stamps
                if page_index in stamp.pages.resolve_or_empty(page_count,
                                                              page_index)]

    # -- mutation --------------------------------------------------------
    def add(self, stamp):
        self.stamps.append(stamp)
        self.selected_id = stamp.stamp_id
        return stamp

    def remove(self, stamp):
        if stamp in self.stamps:
            index = self.stamps.index(stamp)
            self.stamps.remove(stamp)
            if self.selected_id == stamp.stamp_id:
                remaining = self.stamps[min(index, len(self.stamps) - 1)] \
                    if self.stamps else None
                self.selected_id = remaining.stamp_id if remaining else None

    def duplicate(self, stamp, offset=12.0):
        clone = stamp.copy()
        if clone.anchor in geometry.ANCHOR_KEYS:
            clone.margin_x += offset
            clone.margin_y += offset
        else:
            clone.x += offset
            clone.y += offset
        self.stamps.append(clone)
        self.selected_id = clone.stamp_id
        return clone

    def raise_stamp(self, stamp):
        index = self.stamps.index(stamp)
        if index < len(self.stamps) - 1:
            self.stamps[index], self.stamps[index + 1] = \
                self.stamps[index + 1], self.stamps[index]
            return True
        return False

    def lower_stamp(self, stamp):
        index = self.stamps.index(stamp)
        if index > 0:
            self.stamps[index], self.stamps[index - 1] = \
                self.stamps[index - 1], self.stamps[index]
            return True
        return False
