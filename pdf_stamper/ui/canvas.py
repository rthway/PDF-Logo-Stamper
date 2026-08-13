"""The interactive page view: continuous scrolling, select, drag, resize, rotate.

Every page of the document is laid out in one vertical strip, so the user can
scroll through the whole file and adjust the stamp on any page - the way a PDF
reader behaves. Only the pages that are actually visible are rasterised.

All editing happens here in *canvas pixels*, but every value written back to a
Stamp goes through `geometry.Viewport`, so the model only ever holds page points.
That is the invariant the export-accuracy tests lock down.
"""

import math
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from .. import geometry as geo
from ..errors import AppError
from ..logging_setup import get_logger
from . import theme

log = get_logger(__name__)

PAGE_PAD = 28            # gap between the page strip and the workspace edge
PAGE_GAP = 30            # vertical gap between pages (holds the page label)
OVERSCAN = 240           # extra pixels rendered above/below the viewport
HANDLE_HIT = 7           # click tolerance around a handle, in pixels
SNAP_PIXELS = 6          # snap distance while dragging
MIN_SIZE_POINTS = 8.0
ZOOM_STEPS = (0.10, 0.15, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
MIN_ZOOM, MAX_ZOOM = 0.05, 4.0

# Resize handles: name -> (x factor, y factor) in box space.
HANDLES = {
    "nw": (0.0, 0.0), "n": (0.5, 0.0), "ne": (1.0, 0.0),
    "e": (1.0, 0.5), "se": (1.0, 1.0), "s": (0.5, 1.0),
    "sw": (0.0, 1.0), "w": (0.0, 0.5),
}
HANDLE_CURSORS = {"nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw",
                  "sw": "size_ne_sw", "n": "size_ns", "s": "size_ns",
                  "e": "size_we", "w": "size_we"}


class StampCanvas(ttk.Frame):
    """Scrollable, zoomable view of every page, with direct stamp manipulation."""

    def __init__(self, master, store, on_select=None, on_live_change=None,
                 on_commit=None, on_context_menu=None, on_status=None,
                 on_zoom_change=None, on_double_click=None, on_page_change=None):
        super().__init__(master, style="App.TFrame")
        self.store = store
        self.on_select = on_select
        self.on_live_change = on_live_change
        self.on_commit = on_commit
        self.on_context_menu = on_context_menu
        self.on_status = on_status
        self.on_zoom_change = on_zoom_change
        self.on_double_click = on_double_click
        self.on_page_change = on_page_change

        self.document = None
        self.layer = None
        self.page_index = 0                  # the "current" page (most visible)
        self.zoom = 1.0
        self.zoom_mode = "fit-page"          # fit-page | fit-width | manual

        self._page_photos = {}               # page index -> PhotoImage
        self._stamp_photos = {}              # (stamp id, page index) -> PhotoImage
        self._drag = None
        self._pan = None
        self._resize_job = None
        self._scroll_job = None
        self._scroll_top = None              # last observed scroll position
        self._drawing = False
        self._visible_pages = ()
        self._layout = None
        self._page_sizes = ()
        self._render_error = None
        self._dnd_hint = False        # set by the app when file drag-and-drop works
        self._handle_positions = {}
        self._rotate_handle_pos = None

        self.canvas = tk.Canvas(self, background=theme.BG_WORKSPACE,
                                highlightthickness=0, takefocus=True,
                                xscrollincrement=1, yscrollincrement=1)
        self.vbar = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal",
                                  command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self._on_yview,
                              xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._bind_events()
        # Cancel pending work when the widget goes away, so a queued redraw can
        # never fire against a destroyed window during shutdown.
        self.bind("<Destroy>", self._on_destroy)
        # Paint the empty state straight away: an all-grey canvas at start-up
        # gives the user nothing to act on.
        self.after_idle(self.redraw)

    # ------------------------------------------------------------------
    # wiring
    # ------------------------------------------------------------------
    def _bind_events(self):
        canvas = self.canvas
        canvas.bind("<Configure>", self._on_configure)
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_motion)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<Motion>", self._on_hover)
        canvas.bind("<Double-Button-1>", self._on_double)
        canvas.bind("<Button-3>", self._on_right_click)
        canvas.bind("<ButtonPress-2>", self._on_pan_start)
        canvas.bind("<B2-Motion>", self._on_pan_move)
        canvas.bind("<ButtonRelease-2>", lambda e: setattr(self, "_pan", None))
        canvas.bind("<MouseWheel>", self._on_wheel)
        canvas.bind("<Shift-MouseWheel>", self._on_wheel_horizontal)
        canvas.bind("<Control-MouseWheel>", self._on_wheel_zoom)
        canvas.bind("<Enter>", lambda e: canvas.focus_set())
        # Arrow keys are bound to the canvas, never to the window, so typing in a
        # number field does not also nudge the stamp.
        for key, delta in (("Left", (-1, 0)), ("Right", (1, 0)),
                           ("Up", (0, -1)), ("Down", (0, 1))):
            canvas.bind(f"<{key}>", lambda e, d=delta: self._nudge(d, 1))
            canvas.bind(f"<Shift-{key}>", lambda e, d=delta: self._nudge(d, 10))
        canvas.bind("<Escape>", lambda e: self.select_stamp(None))
        canvas.bind("<Home>", lambda e: self.scroll_to_page(0))
        canvas.bind("<End>", lambda e: self.scroll_to_page(
            (self.document.page_count - 1) if self.document else 0))

    # ------------------------------------------------------------------
    # document / model
    # ------------------------------------------------------------------
    def set_document(self, document, layer):
        self.document = document
        self.layer = layer
        self.page_index = 0
        self._page_photos.clear()
        self._stamp_photos.clear()
        self._render_error = None
        self._layout = None
        self._page_sizes = tuple(document.page_size(index)
                                 for index in range(document.page_count)) \
            if document else ()
        self.canvas.yview_moveto(0.0)
        self.canvas.xview_moveto(0.0)
        self.apply_zoom_mode()
        self.redraw()

    def set_page(self, index):
        """Make `index` the current page and scroll it into view."""
        if not self.document:
            return
        index = int(geo.clamp(index, 0, self.document.page_count - 1))
        if index != self.page_index and self.zoom_mode != "manual":
            # Page sizes can differ, so fit-page/-width re-evaluates per page.
            self.apply_zoom_mode(redraw=False, for_page=index)
        self.scroll_to_page(index)

    def scroll_to_page(self, index, redraw=True):
        """Scroll `index` into view and make it the current page.

        This is the one place a deliberate page jump happens (page field, Prev /
        Next, Home / End, fit changes), so it owns both the scroll and the
        current-page bookkeeping.
        """
        layout = self._ensure_layout()
        if not layout:
            return
        index = int(geo.clamp(index, 0, len(layout["origins"]) - 1))
        changed = index != self.page_index
        self.page_index = index
        target = layout["origins"][index][1] - PAGE_GAP / 2
        total = max(layout["content_height"], 1)
        self.canvas.yview_moveto(max(target, 0) / total)
        self._scroll_top = self.canvas.canvasy(0)
        if redraw:
            self.redraw()
        if changed:
            self._notify_page()

    def page_size(self, index=None):
        """Visible size of a page in points (defaults to the current page)."""
        if not self.document:
            return (595.0, 842.0)
        index = self.page_index if index is None else index
        if 0 <= index < len(self._page_sizes):
            return self._page_sizes[index]
        return self.document.page_size(index)

    # ------------------------------------------------------------------
    # layout of the page strip
    # ------------------------------------------------------------------
    def _ensure_layout(self):
        """Positions of every page in canvas coordinates, cached per zoom/size."""
        if not self.document:
            self._layout = None
            return None
        view_w = max(self.canvas.winfo_width(), 1)
        view_h = max(self.canvas.winfo_height(), 1)
        key = (round(self.zoom, 4), view_w, view_h, len(self._page_sizes))
        if self._layout and self._layout["key"] == key:
            return self._layout

        widths = [size[0] * self.zoom for size in self._page_sizes]
        heights = [size[1] * self.zoom for size in self._page_sizes]
        strip_width = max(widths) if widths else 0
        content_width = max(strip_width + PAGE_PAD * 2, view_w)
        content_height = PAGE_PAD * 2 + sum(heights) + PAGE_GAP * max(
            len(heights) - 1, 0)
        # A short document should sit in the middle of the workspace.
        top = PAGE_PAD
        if content_height < view_h:
            top = (view_h - (content_height - PAGE_PAD * 2)) / 2
            content_height = view_h

        origins, cursor = {}, top
        for index, (width, height) in enumerate(zip(widths, heights)):
            origins[index] = ((content_width - width) / 2, cursor)
            cursor += height + PAGE_GAP

        self._layout = {"key": key, "origins": origins, "widths": widths,
                        "heights": heights, "content_width": content_width,
                        "content_height": content_height}
        return self._layout

    def viewport_for(self, index):
        """Mapping between page points and canvas pixels for one page."""
        layout = self._ensure_layout()
        size = self.page_size(index)
        if not layout or index not in layout["origins"]:
            return geo.Viewport(size[0], size[1], self.zoom, PAGE_PAD, PAGE_PAD)
        origin_x, origin_y = layout["origins"][index]
        return geo.Viewport(size[0], size[1], self.zoom, origin_x, origin_y)

    def viewport(self):
        """Viewport of the current page (what the properties panel refers to)."""
        return self.viewport_for(self.page_index)

    def _visible_span(self):
        """The vertical canvas range currently on screen, plus overscan."""
        top = self.canvas.canvasy(0)
        height = max(self.canvas.winfo_height(), 1)
        return (top - OVERSCAN, top + height + OVERSCAN)

    def _pages_in_view(self):
        layout = self._ensure_layout()
        if not layout:
            return ()
        low, high = self._visible_span()
        found = []
        for index, (_, origin_y) in layout["origins"].items():
            if origin_y <= high and origin_y + layout["heights"][index] >= low:
                found.append(index)
        if not found:                       # scrolled past the end somehow
            found = [min(max(0, len(layout["origins"]) - 1), self.page_index)]
        return tuple(sorted(found))

    def _most_visible_page(self):
        """The page occupying most of the viewport - i.e. the one being worked on."""
        layout = self._ensure_layout()
        if not layout:
            return 0
        top = self.canvas.canvasy(0)
        bottom = top + max(self.canvas.winfo_height(), 1)
        best, best_area = self.page_index, -1.0
        for index, (_, origin_y) in layout["origins"].items():
            page_bottom = origin_y + layout["heights"][index]
            overlap = min(bottom, page_bottom) - max(top, origin_y)
            if overlap > best_area + 0.5:
                best, best_area = index, overlap
        return best

    def _page_at(self, canvas_point):
        """Which page a canvas point belongs to (nearest one when in a gap)."""
        layout = self._ensure_layout()
        if not layout:
            return None
        _, y = canvas_point
        nearest, distance = None, None
        for index, (_, origin_y) in layout["origins"].items():
            height = layout["heights"][index]
            if origin_y <= y <= origin_y + height:
                return index
            gap = origin_y - y if y < origin_y else y - (origin_y + height)
            if distance is None or gap < distance:
                nearest, distance = index, gap
        return nearest

    # ------------------------------------------------------------------
    # zoom
    # ------------------------------------------------------------------
    def apply_zoom_mode(self, redraw=True, for_page=None):
        """Recompute the zoom for fit-page / fit-width (for a given page's size)."""
        if not self.document:
            return
        if self.zoom_mode in ("fit-page", "fit-width"):
            view = (max(self.canvas.winfo_width(), 200),
                    max(self.canvas.winfo_height(), 200))
            zoom = geo.zoom_to_fit(self.page_size(for_page), view, self.zoom_mode,
                                   padding=PAGE_PAD * 2)
            new_zoom = geo.clamp(zoom, MIN_ZOOM, MAX_ZOOM)
            if abs(new_zoom - self.zoom) > 1e-9:
                self.zoom = new_zoom
                self._layout = None
        if redraw:
            self.redraw()
        self._notify_zoom()

    def set_zoom(self, zoom, focus=None, mode="manual"):
        """Zoom, keeping the page point under `focus` (canvas px) in place."""
        new_zoom = geo.clamp(float(zoom), MIN_ZOOM, MAX_ZOOM)
        if abs(new_zoom - self.zoom) < 1e-6 and mode == self.zoom_mode:
            return
        anchor = None
        if focus is not None and self.document:
            index = self._page_at(focus)
            if index is not None:
                anchor = (index, self.viewport_for(index).to_page(*focus))
        self.zoom_mode = mode
        self.zoom = new_zoom
        self._layout = None
        self.redraw()
        if anchor is not None:
            index, page_point = anchor
            moved = self.viewport_for(index).to_canvas(*page_point)
            self.canvas.xview_scroll(int(round(moved[0] - focus[0])), "units")
            self.canvas.yview_scroll(int(round(moved[1] - focus[1])), "units")
            self.redraw()
        self._notify_zoom()

    def zoom_in(self):
        for step in ZOOM_STEPS:
            if step > self.zoom + 1e-4:
                return self.set_zoom(step)
        self.set_zoom(MAX_ZOOM)

    def zoom_out(self):
        for step in reversed(ZOOM_STEPS):
            if step < self.zoom - 1e-4:
                return self.set_zoom(step)
        self.set_zoom(MIN_ZOOM)

    def fit_page(self):
        self.zoom_mode = "fit-page"
        self.apply_zoom_mode()
        self.scroll_to_page(self.page_index)

    def fit_width(self):
        self.zoom_mode = "fit-width"
        self.apply_zoom_mode()
        self.scroll_to_page(self.page_index)

    def _notify_zoom(self):
        if self.on_zoom_change:
            self.on_zoom_change(self.zoom, self.zoom_mode)

    def _notify_page(self):
        if self.on_page_change:
            self.on_page_change(self.page_index)

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------
    def _on_destroy(self, event):
        if event.widget is not self:
            return
        for attribute in ("_resize_job", "_scroll_job"):
            job = getattr(self, attribute, None)
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)
        self._destroyed = True

    def redraw(self):
        if self._drawing or getattr(self, "_destroyed", False):
            return
        if not self.canvas.winfo_exists():
            return
        self._drawing = True
        try:
            canvas = self.canvas
            canvas.delete("all")
            self._stamp_photos.clear()
            self._page_photos.clear()
            self._handle_positions = {}
            self._rotate_handle_pos = None
            if not self.document:
                self._draw_empty_state()
                return

            layout = self._ensure_layout()
            canvas.configure(scrollregion=(0, 0, layout["content_width"],
                                           layout["content_height"]))
            self._visible_pages = self._pages_in_view()
            for index in self._visible_pages:
                self._draw_page(index, layout)
            self._draw_selection()
        finally:
            self._drawing = False

    def _draw_page(self, index, layout):
        canvas = self.canvas
        origin_x, origin_y = layout["origins"][index]
        width, height = layout["widths"][index], layout["heights"][index]
        x1, y1 = origin_x + width, origin_y + height

        canvas.create_rectangle(origin_x + 3, origin_y + 4, x1 + 4, y1 + 5,
                                fill=theme.PAGE_SHADOW, outline="")
        canvas.create_rectangle(origin_x, origin_y, x1, y1, fill="#FFFFFF",
                                outline=theme.BORDER_STRONG)
        # Page label in the gap above the sheet, so scrolling stays oriented.
        canvas.create_text(origin_x, origin_y - 9, anchor="w",
                           text=f"Page {index + 1} of {self.document.page_count}",
                           fill="#D7DBE0" if index == self.page_index else "#A9AEB4",
                           font=theme.fonts()["small"])
        if index == self.page_index:
            canvas.create_rectangle(origin_x - 2, origin_y - 2, x1 + 2, y1 + 2,
                                    outline=theme.ACCENT, width=1)

        try:
            image = self.document.render_page(index, self.zoom)
            photo = ImageTk.PhotoImage(image)
            self._page_photos[index] = photo
            canvas.create_image(origin_x, origin_y, image=photo, anchor="nw")
        except AppError as exc:
            self._render_error = exc.message
            canvas.create_text((origin_x + x1) / 2, (origin_y + y1) / 2,
                               width=width * 0.7, text=exc.message,
                               fill=theme.TEXT_MUTED, font=theme.fonts()["body"],
                               justify="center")

        self._draw_stamps(index)

    def _draw_empty_state(self):
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        width = max(self.canvas.winfo_width(), 320)
        height = max(self.canvas.winfo_height(), 320)
        centre_x, centre_y = width / 2, height / 2
        # A dashed drop zone reads as "put something here".
        half_w, half_h = min(width * 0.3, 260), min(height * 0.22, 150)
        self.canvas.create_rectangle(centre_x - half_w, centre_y - half_h,
                                     centre_x + half_w, centre_y + half_h,
                                     outline="#8D9196", dash=(6, 4))
        self.canvas.create_text(centre_x, centre_y - 14, text="No document open",
                                fill="#FFFFFF", font=theme.fonts()["title"])
        self.canvas.create_text(
            centre_x, centre_y + 16,
            text="Click “Open PDF” (Ctrl+O)" +
                 ("  or drop a PDF here" if self._dnd_hint else ""),
            fill="#DCE0E5", font=theme.fonts()["body"])

    def _draw_stamps(self, index):
        view = self.viewport_for(index)
        page_size = (view.page_width, view.page_height)
        page_count = self.document.page_count
        for stamp in self.layer.stamps:
            applies = index in stamp.pages.resolve_or_empty(page_count,
                                                            self.page_index)
            box = stamp.box_on(page_size, index)
            rotated = stamp.rotated_box_on(page_size, index)
            canvas_x, canvas_y = view.to_canvas(rotated[0], rotated[1])
            try:
                image = self.store.render(stamp.image_for(index),
                                          (box[2], box[3]),
                                          stamp.value_for("rotation", index),
                                          stamp.value_for("opacity", index)
                                          if applies else 30,
                                          self.zoom)
            except AppError:
                continue
            photo = ImageTk.PhotoImage(image)
            self._stamp_photos[(stamp.stamp_id, index)] = photo
            self.canvas.create_image(canvas_x, canvas_y, image=photo, anchor="nw",
                                     tags=("stamp", f"stamp-{stamp.stamp_id}"))
            if not applies:
                self._draw_excluded_badge(view, box, index)
            elif stamp.has_override(index):
                self._draw_custom_badge(view, box)

    def _draw_excluded_badge(self, view, box, page_index=None):
        x, y = view.to_canvas(box[0] + box[2] / 2, box[1])
        skipped = page_index is not None and self.layer and any(
            stamp.pages.is_skipped(page_index, self.document.page_count)
            for stamp in self.layer.stamps)
        self.canvas.create_text(
            x, y - 9, fill="#FFE08A", font=theme.fonts()["small"],
            text="skipped on this page" if skipped else "not applied to this page")

    def _draw_custom_badge(self, view, box):
        x, y = view.to_canvas(box[0] + box[2] / 2, box[1])
        self.canvas.create_text(x, y - 9, text="custom for this page",
                                fill="#9DC4FF", font=theme.fonts()["small"])

    def _draw_selection(self):
        """Handles are drawn on the current page's copy of the selected stamp."""
        stamp = self.layer.selected if self.layer else None
        if stamp is None or self.page_index not in self._visible_pages:
            return
        view = self.viewport_for(self.page_index)
        page_size = (view.page_width, view.page_height)
        box = stamp.box_on(page_size, self.page_index)
        rotation = stamp.value_for("rotation", self.page_index)
        corners = [view.to_canvas(*point)
                   for point in geo.rotated_corners(box, rotation)]
        flat = [value for point in corners for value in point]
        self.canvas.create_polygon(flat, outline=theme.SELECTION, fill="",
                                   width=1, dash=(4, 3), tags="selection")

        # rotation handle above the top edge
        top_mid = ((corners[0][0] + corners[1][0]) / 2,
                   (corners[0][1] + corners[1][1]) / 2)
        centre = view.to_canvas(box[0] + box[2] / 2, box[1] + box[3] / 2)
        length = math.hypot(top_mid[0] - centre[0], top_mid[1] - centre[1]) or 1
        offset = 22
        handle = (top_mid[0] + (top_mid[0] - centre[0]) / length * offset,
                  top_mid[1] + (top_mid[1] - centre[1]) / length * offset)
        self.canvas.create_line(top_mid[0], top_mid[1], handle[0], handle[1],
                                fill=theme.SELECTION, width=1, tags="selection")
        radius = theme.HANDLE_SIZE / 2 + 1
        self.canvas.create_oval(handle[0] - radius, handle[1] - radius,
                                handle[0] + radius, handle[1] + radius,
                                fill="#FFFFFF", outline=theme.SELECTION, width=2,
                                tags=("selection", "handle-rotate"))
        self._rotate_handle_pos = handle

        # resize handles
        self._handle_positions = {}
        for name, (fx, fy) in HANDLES.items():
            point = geo.rotate_point(box[0] + box[2] * fx, box[1] + box[3] * fy,
                                     box[0] + box[2] / 2, box[1] + box[3] / 2,
                                     rotation)
            canvas_point = view.to_canvas(*point)
            self._handle_positions[name] = canvas_point
            half = theme.HANDLE_SIZE / 2
            self.canvas.create_rectangle(canvas_point[0] - half,
                                         canvas_point[1] - half,
                                         canvas_point[0] + half,
                                         canvas_point[1] + half,
                                         fill="#FFFFFF", outline=theme.SELECTION,
                                         width=2, tags=("selection",
                                                        f"handle-{name}"))

    def _draw_guides(self, guides, view):
        self.canvas.delete("guide")
        height = view.page_height * self.zoom
        width = view.page_width * self.zoom
        for axis, value in guides:
            if axis == "x":
                x = view.to_canvas(value, 0)[0]
                self.canvas.create_line(x, view.origin_y, x, view.origin_y + height,
                                        fill=theme.GUIDE, dash=(3, 3), tags="guide")
            else:
                y = view.to_canvas(0, value)[1]
                self.canvas.create_line(view.origin_x, y, view.origin_x + width, y,
                                        fill=theme.GUIDE, dash=(3, 3), tags="guide")

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------
    def select_stamp(self, stamp):
        if not self.layer:
            return
        new_id = stamp.stamp_id if stamp is not None else None
        if new_id != self.layer.selected_id:
            self.layer.selected_id = new_id
            if self.on_select:
                self.on_select(stamp)
        self.redraw()

    def _set_current_page(self, index, notify=True):
        """Change the working page without scrolling (used when clicking a page)."""
        # Remember where we are, so the idle scroll check does not treat this as a
        # scroll and snap the working page back to whichever one fills the view.
        self._scroll_top = self.canvas.canvasy(0)
        if index is None or index == self.page_index:
            return False
        self.page_index = index
        if notify:
            self._notify_page()
        return True

    def _edit_page(self, stamp, page_index):
        """Where edits should be written for this page.

        A page the user customised keeps its own values, so edits there must not
        touch the shared settings (and so must not move the stamp on any other
        page). Everywhere else, edits apply to the stamp as a whole.
        """
        if stamp is not None and page_index is not None and                 stamp.has_override(page_index):
            return page_index
        return None

    def _stamp_at(self, canvas_point, page_index=None):
        """Topmost stamp under a canvas point, on the page that point is over."""
        if page_index is None:
            page_index = self._page_at(canvas_point)
        if page_index is None:
            return None
        view = self.viewport_for(page_index)
        page_point = view.to_page(*canvas_point)
        page_size = (view.page_width, view.page_height)
        for stamp in reversed(self.layer.stamps):
            box = stamp.box_on(page_size, page_index)
            rotation = stamp.value_for("rotation", page_index)
            if geo.point_in_rotated_rect(page_point, box, rotation):
                return stamp
        return None

    def _handle_at(self, canvas_point):
        """Handle name under a canvas point for the selected stamp."""
        if not self.layer or self.layer.selected is None:
            return None
        positions = dict(self._handle_positions)
        if self._rotate_handle_pos:
            positions["rotate"] = self._rotate_handle_pos
        for name, point in positions.items():
            if abs(canvas_point[0] - point[0]) <= HANDLE_HIT and \
                    abs(canvas_point[1] - point[1]) <= HANDLE_HIT:
                return name
        return None

    # ------------------------------------------------------------------
    # mouse
    # ------------------------------------------------------------------
    def _canvas_point(self, event):
        return (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    def _on_press(self, event):
        self.canvas.focus_set()
        if not self.document or not self.layer:
            return
        point = self._canvas_point(event)

        handle = self._handle_at(point)
        if handle:
            stamp = self.layer.selected
            view = self.viewport_for(self.page_index)
            box = stamp.box_on((view.page_width, view.page_height),
                               self.page_index)
            self._drag = {
                "mode": "rotate" if handle == "rotate" else "resize",
                "handle": handle, "stamp": stamp, "view": view,
                "page": self.page_index,
                "edit_page": self._edit_page(stamp, self.page_index),
                "start_box": box,
                "start_rotation": stamp.value_for("rotation", self.page_index),
                "start_angle": self._angle_to_centre(point, box, view),
                "moved": False,
            }
            return

        page_index = self._page_at(point)
        stamp = self._stamp_at(point, page_index)
        page_changed = self._set_current_page(page_index)
        if stamp is None:
            if self.layer.selected_id is not None:
                self.select_stamp(None)
            elif page_changed:
                self.redraw()
            return
        if stamp.stamp_id != self.layer.selected_id or page_changed:
            self.layer.selected_id = stamp.stamp_id
            if self.on_select:
                self.on_select(stamp)
            self.redraw()

        view = self.viewport_for(page_index)
        box = stamp.box_on((view.page_width, view.page_height), page_index)
        self._drag = {"mode": "move", "stamp": stamp, "view": view,
                      "page": page_index,
                      "edit_page": self._edit_page(stamp, page_index),
                      "start_box": box, "grab": view.to_page(*point),
                      "moved": False}

    def _angle_to_centre(self, canvas_point, box, view):
        centre = view.to_canvas(box[0] + box[2] / 2, box[1] + box[3] / 2)
        return math.degrees(math.atan2(canvas_point[1] - centre[1],
                                       canvas_point[0] - centre[0]))

    def _on_motion(self, event):
        if not self._drag:
            return
        point = self._canvas_point(event)
        drag = self._drag
        drag["moved"] = True
        shift = bool(event.state & 0x0001)
        if drag["mode"] == "move":
            self._drag_move(point, drag, shift)
        elif drag["mode"] == "resize":
            self._drag_resize(point, drag, shift)
        else:
            self._drag_rotate(point, drag, shift)
        self.redraw()
        if drag["mode"] == "move" and drag.get("guides"):
            self._draw_guides(drag["guides"], drag["view"])
        if self.on_live_change:
            self.on_live_change(drag["stamp"])

    def _drag_move(self, point, drag, shift):
        view = drag["view"]
        stamp, box = drag["stamp"], drag["start_box"]
        page_point = view.to_page(*point)
        dx = page_point[0] - drag["grab"][0]
        dy = page_point[1] - drag["grab"][1]
        if shift:                                   # constrain to one axis
            if abs(dx) > abs(dy):
                dy = 0
            else:
                dx = 0
        x, y = box[0] + dx, box[1] + dy
        x, y, guides = self._snap(x, y, box, view)
        stamp.move_to(x, y, drag.get("edit_page"))
        drag["guides"] = guides

    def _snap(self, x, y, box, view):
        """Snap to page centre and edges; returns adjusted position + guides."""
        tolerance = view.to_page_length(SNAP_PIXELS)
        page_w, page_h = view.page_width, view.page_height
        guides = []
        # (snapped position, guide line to draw) per axis.
        targets_x = (((page_w - box[2]) / 2, page_w / 2),
                     (0.0, 0.0),
                     (page_w - box[2], page_w))
        targets_y = (((page_h - box[3]) / 2, page_h / 2),
                     (0.0, 0.0),
                     (page_h - box[3], page_h))
        for target, guide in targets_x:
            if abs(x - target) <= tolerance:
                x, _ = target, guides.append(("x", guide))
                break
        for target, guide in targets_y:
            if abs(y - target) <= tolerance:
                y, _ = target, guides.append(("y", guide))
                break
        return x, y, guides

    def _drag_resize(self, point, drag, shift):
        """Resize around the opposite corner, in the stamp's own rotated frame."""
        view = drag["view"]
        stamp, box = drag["stamp"], drag["start_box"]
        handle = drag["handle"]
        fx, fy = HANDLES[handle]
        rotation = drag["start_rotation"]
        centre = (box[0] + box[2] / 2, box[1] + box[3] / 2)
        # The pinned point is the opposite handle, in page space.
        pinned_local = (box[0] + box[2] * (1 - fx), box[1] + box[3] * (1 - fy))
        pinned = geo.rotate_point(*pinned_local, *centre, rotation)

        page_point = view.to_page(*point)
        # Express the cursor in the stamp's unrotated frame relative to `pinned`.
        local = geo.rotate_point(page_point[0], page_point[1], pinned[0], pinned[1],
                                 -rotation)
        width = box[2] if fx == 0.5 else abs(local[0] - pinned[0])
        height = box[3] if fy == 0.5 else abs(local[1] - pinned[1])

        keep_ratio = stamp.keep_ratio or shift
        if keep_ratio and fx != 0.5 and fy != 0.5:
            ratio = box[2] / box[3] if box[3] else 1.0
            if width / max(height, 1e-6) > ratio:
                height = width / ratio
            else:
                width = height * ratio
        width = max(width, MIN_SIZE_POINTS)
        height = max(height, MIN_SIZE_POINTS)

        # Put the pinned point back where it was. For an edge handle the pinned
        # point is that edge's midpoint, so on that axis it already *is* the centre.
        sign_x = -1 if fx < 0.5 else (1 if fx > 0.5 else 0)
        sign_y = -1 if fy < 0.5 else (1 if fy > 0.5 else 0)
        local_centre = (pinned[0] + sign_x * width / 2 if sign_x else pinned[0],
                        pinned[1] + sign_y * height / 2 if sign_y else pinned[1])
        new_centre = geo.rotate_point(local_centre[0], local_centre[1],
                                      pinned[0], pinned[1], rotation)
        edit_page = drag.get("edit_page")
        stamp.set_values({"width": width, "height": height}, edit_page)
        stamp.move_to(new_centre[0] - width / 2, new_centre[1] - height / 2,
                      edit_page)

    def _drag_rotate(self, point, drag, shift):
        stamp = drag["stamp"]
        angle = self._angle_to_centre(point, drag["start_box"], drag["view"])
        rotation = drag["start_rotation"] + (angle - drag["start_angle"])
        if shift:
            rotation = round(rotation / 15.0) * 15.0
        stamp.set_values({"rotation": round(rotation % 360.0, 2)},
                         drag.get("edit_page"))

    def _on_release(self, _event):
        drag, self._drag = self._drag, None
        self.canvas.delete("guide")
        if drag and drag.get("moved") and self.on_commit:
            self.on_commit(drag["stamp"], drag["mode"])
        elif drag:
            self.redraw()

    def _on_hover(self, event):
        if self._drag or not self.layer:
            return
        point = self._canvas_point(event)
        handle = self._handle_at(point)
        if handle == "rotate":
            cursor = "exchange"
        elif handle:
            cursor = HANDLE_CURSORS.get(handle, "arrow")
        elif self.document and self._stamp_at(point) is not None:
            cursor = "hand2"
        else:
            cursor = "arrow"
        self.canvas.configure(cursor=cursor)
        if self.on_status and self.document:
            index = self._page_at(point)
            view = self.viewport_for(index) if index is not None else None
            page_point = view.to_page(*point) if view else None
            inside = page_point is not None and \
                0 <= page_point[0] <= view.page_width and \
                0 <= page_point[1] <= view.page_height
            self.on_status(page_point if inside else None)

    def _on_double(self, event):
        if self.on_double_click:
            self.on_double_click(self._stamp_at(self._canvas_point(event)))

    def _on_right_click(self, event):
        if not self.layer or not self.document:
            return
        point = self._canvas_point(event)
        page_index = self._page_at(point)
        stamp = self._stamp_at(point, page_index)
        self._set_current_page(page_index)
        if stamp is not None and stamp.stamp_id != self.layer.selected_id:
            self.select_stamp(stamp)
        else:
            self.redraw()
        if self.on_context_menu:
            self.on_context_menu(event, stamp)

    # -- panning, scrolling and the wheel --------------------------------
    def _on_pan_start(self, event):
        self._pan = (event.x, event.y)
        self.canvas.configure(cursor="fleur")

    def _on_pan_move(self, event):
        if not self._pan:
            return
        self.canvas.xview_scroll(self._pan[0] - event.x, "units")
        self.canvas.yview_scroll(self._pan[1] - event.y, "units")
        self._pan = (event.x, event.y)

    def _on_wheel(self, event):
        # One notch scrolls a comfortable distance; the strip spans every page,
        # so this keeps going into the next page instead of stopping.
        self.canvas.yview_scroll(-int(event.delta / 3), "units")

    def _on_wheel_horizontal(self, event):
        self.canvas.xview_scroll(-int(event.delta / 3), "units")

    def _on_wheel_zoom(self, event):
        factor = 1.1 if event.delta > 0 else 1 / 1.1
        self.set_zoom(self.zoom * factor, focus=self._canvas_point(event))

    def _on_yview(self, first, last):
        """Scrollbar callback: also our signal that the visible pages may differ."""
        self.vbar.set(first, last)
        if self._drawing or not self.document:
            return
        if self._scroll_job is None:
            self._scroll_job = self.after_idle(self._after_scroll)

    def _after_scroll(self):
        self._scroll_job = None
        if not self.document or self._drawing:
            return
        top = self.canvas.canvasy(0)
        scrolled = self._scroll_top is None or abs(top - self._scroll_top) > 0.5
        self._scroll_top = top
        pages = self._pages_in_view()
        # Only a real scroll re-picks the working page; a click on another page
        # must keep its selection and handles where the user put them.
        page_changed = self._set_current_page(self._most_visible_page())             if scrolled else False
        if pages != self._visible_pages or page_changed:
            self.redraw()

    def _on_configure(self, _event):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        # Debounced: dragging the window edge must not queue dozens of renders.
        self._resize_job = self.after(60, self._after_resize)

    def _after_resize(self):
        self._resize_job = None
        self._layout = None
        if self.document and self.zoom_mode in ("fit-page", "fit-width"):
            self.apply_zoom_mode()
        else:
            self.redraw()      # also re-centres the empty state

    # -- keyboard --------------------------------------------------------
    def _nudge(self, delta, step):
        if not self.layer:
            return
        stamp = self.layer.selected
        if stamp is None:
            return
        box = stamp.box_on(self.page_size(), self.page_index)
        stamp.move_to(box[0] + delta[0] * step, box[1] + delta[1] * step,
                      self._edit_page(stamp, self.page_index))
        self.redraw()
        if self.on_live_change:
            self.on_live_change(stamp)
        if self.on_commit:
            self.on_commit(stamp, "nudge")
        return "break"
