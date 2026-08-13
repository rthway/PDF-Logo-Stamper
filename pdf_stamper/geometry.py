"""Geometry and coordinate conversion - the single source of truth for placement.

Three coordinate spaces are involved:

1. **Screen / canvas pixels** - what the mouse reports. Includes zoom and the
   scroll offset of the page inside the canvas.
2. **Visual page points** - PDF points (72 pt = 1 inch) measured from the *visible*
   top-left corner of the page, y growing downward. This is what MuPDF's
   ``page.rect`` and ``page.get_pixmap()`` use, so it is what the preview shows,
   and it is what a Stamp stores.
3. **Unrotated PDF points** - the page's own coordinate system, which differs from
   (2) whenever the page carries a ``/Rotate`` entry. Only the export step works
   here, via ``page.derotation_matrix``.

Screen -> visual is `Viewport`; visual -> unrotated is `visual_rect_to_page`
(in pdf_service). Nothing else is allowed to invent its own mapping, which is how
the preview and the exported file stay in agreement.
"""

import math
from dataclasses import dataclass

# Preset anchors, in reading order, as (label, key).
ANCHOR_PRESETS = (
    ("Top Left", "top-left"),
    ("Top Center", "top-center"),
    ("Top Right", "top-right"),
    ("Center Left", "mid-left"),
    ("Center", "mid-center"),
    ("Center Right", "mid-right"),
    ("Bottom Left", "bottom-left"),
    ("Bottom Center", "bottom-center"),
    ("Bottom Right", "bottom-right"),
)
ANCHOR_KEYS = tuple(key for _, key in ANCHOR_PRESETS)
ANCHOR_CUSTOM = "custom"


def fit_size(natural, box, keep_ratio):
    """Size a natural (w, h) takes inside a box, optionally without distortion."""
    box_w, box_h = float(box[0]), float(box[1])
    if not keep_ratio:
        return box_w, box_h
    nat_w, nat_h = float(natural[0]), float(natural[1])
    if nat_w <= 0 or nat_h <= 0 or box_w <= 0 or box_h <= 0:
        return box_w, box_h
    scale = min(box_w / nat_w, box_h / nat_h)
    return nat_w * scale, nat_h * scale


def rotated_extent(width, height, degrees):
    """Axis-aligned bounding size of a w x h box rotated by `degrees`."""
    angle = math.radians(degrees % 360.0)
    cos_a, sin_a = abs(math.cos(angle)), abs(math.sin(angle))
    return (width * cos_a + height * sin_a, width * sin_a + height * cos_a)


def anchor_origin(page_size, size, anchor, margin=(0.0, 0.0)):
    """Top-left corner (visual points) of `size` placed at `anchor` on a page.

    Margins apply only on the edges the anchor touches; centered axes ignore them.
    """
    page_w, page_h = float(page_size[0]), float(page_size[1])
    width, height = float(size[0]), float(size[1])
    margin_x, margin_y = float(margin[0]), float(margin[1])
    vertical, _, horizontal = str(anchor).partition("-")

    if horizontal == "left":
        x = margin_x
    elif horizontal == "right":
        x = page_w - width - margin_x
    else:
        x = (page_w - width) / 2.0

    if vertical == "top":
        y = margin_y
    elif vertical == "bottom":
        y = page_h - height - margin_y
    else:
        y = (page_h - height) / 2.0

    return x, y


def nearest_anchor(page_size, rect, tolerance=1.0):
    """Anchor whose position matches `rect`, else ANCHOR_CUSTOM.

    Used to show a preset as active after the user drags a stamp back onto it.
    """
    x, y, width, height = rect
    # Margins are unknown here, so each axis is compared independently and only
    # a zero-margin match counts as a preset.
    vertical_matches = {
        "top": abs(y - 0) < tolerance,
        "mid": abs(y - (page_size[1] - height) / 2.0) < tolerance,
        "bottom": abs(y - (page_size[1] - height)) < tolerance,
    }
    horizontal_matches = {
        "left": abs(x - 0) < tolerance,
        "center": abs(x - (page_size[0] - width) / 2.0) < tolerance,
        "right": abs(x - (page_size[0] - width)) < tolerance,
    }
    for vertical, v_ok in vertical_matches.items():
        for horizontal, h_ok in horizontal_matches.items():
            if v_ok and h_ok:
                return f"{vertical}-{horizontal}"
    return ANCHOR_CUSTOM


def clamp(value, low, high):
    return low if value < low else (high if value > high else value)


@dataclass
class Viewport:
    """Maps visual page points <-> canvas pixels for one rendered page.

    origin_x/origin_y are the canvas coordinates of the page's top-left corner
    (they already include centring and scrolling), zoom is pixels per point.
    """

    page_width: float
    page_height: float
    zoom: float = 1.0
    origin_x: float = 0.0
    origin_y: float = 0.0

    # -- points -> pixels ------------------------------------------------
    def to_canvas(self, x, y):
        return (self.origin_x + x * self.zoom, self.origin_y + y * self.zoom)

    def to_canvas_rect(self, rect):
        x, y, width, height = rect
        cx, cy = self.to_canvas(x, y)
        return (cx, cy, cx + width * self.zoom, cy + height * self.zoom)

    def scale(self, length):
        return length * self.zoom

    # -- pixels -> points ------------------------------------------------
    def to_page(self, canvas_x, canvas_y):
        return ((canvas_x - self.origin_x) / self.zoom,
                (canvas_y - self.origin_y) / self.zoom)

    def to_page_length(self, pixels):
        return pixels / self.zoom

    def contains_canvas_point(self, canvas_x, canvas_y):
        x, y = self.to_page(canvas_x, canvas_y)
        return 0 <= x <= self.page_width and 0 <= y <= self.page_height

    @property
    def canvas_size(self):
        return (self.page_width * self.zoom, self.page_height * self.zoom)


def zoom_to_fit(page_size, viewport_size, mode="fit-page", padding=24.0):
    """Zoom factor for 'fit-page' or 'fit-width' inside a viewport, in px/pt."""
    page_w, page_h = page_size
    view_w = max(float(viewport_size[0]) - padding, 1.0)
    view_h = max(float(viewport_size[1]) - padding, 1.0)
    if page_w <= 0 or page_h <= 0:
        return 1.0
    if mode == "fit-width":
        return view_w / page_w
    return min(view_w / page_w, view_h / page_h)


def rotate_point(x, y, cx, cy, degrees):
    """Rotate (x, y) about (cx, cy) by `degrees`, clockwise on screen (y down)."""
    angle = math.radians(degrees)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    dx, dy = x - cx, y - cy
    return (cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)


def rotated_corners(rect, degrees):
    """The four corners of `rect` after rotating about its centre."""
    x, y, width, height = rect
    cx, cy = x + width / 2.0, y + height / 2.0
    corners = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    return tuple(rotate_point(px, py, cx, cy, degrees) for px, py in corners)


def point_in_rotated_rect(point, rect, degrees):
    """Hit-test a point against a rotated rectangle (un-rotate, then compare)."""
    x, y, width, height = rect
    cx, cy = x + width / 2.0, y + height / 2.0
    ux, uy = rotate_point(point[0], point[1], cx, cy, -degrees)
    return x <= ux <= x + width and y <= uy <= y + height
