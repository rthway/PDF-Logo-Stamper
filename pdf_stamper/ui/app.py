"""The main window: toolbar, document sidebar, workspace, properties, status bar.

This module wires widgets to the services; it contains no PDF or image logic of
its own, so the engine can be tested (and scripted) without Tkinter.
"""

import os
import tkinter as tk
from tkinter import filedialog, ttk

from .. import APP_NAME, __version__
from .. import batch as batch_service
from .. import geometry as geo
from .. import image_service, pdf_service
from ..config import Config
from ..errors import AppError
from ..logging_setup import get_logger
from ..models import (History, PageSelection, Stamp, StampLayer, format_page_spec,
                      parse_page_spec)
from . import dialogs, theme
from .canvas import StampCanvas
from .widgets import (NumberField, ScrollableColumn, Section, StatusBar,
                      ToolbarSeparator, ToolButton, Tooltip)

log = get_logger(__name__)

PAGE_MODE_LABELS = (("Current page", "current"), ("All pages", "all"),
                    ("Page range", "range"))


class MainWindow:
    """Application shell and controller."""

    def __init__(self, root, config=None, dnd_available=False):
        self.root = root
        self.config = config or Config()
        self.dnd_available = dnd_available
        self.store = image_service.ImageStore()
        self.layer = StampLayer()
        self.history = History()
        self.document = None
        self.pdf_path = None
        self.output_path = None
        self.dirty = False
        self._history_job = None
        self._suspend_fields = False

        root.title(APP_NAME)
        root.minsize(1080, 700)
        geometry = self.config.get("window_geometry")
        root.geometry(geometry if geometry else "1280x840")
        theme.apply_theme(root)
        theme.set_window_icon(root)

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_status()
        self._bind_shortcuts()
        self._enable_drop_targets()

        self.history.reset(self.layer.snapshot())
        self._refresh_all()
        root.protocol("WM_DELETE_WINDOW", self.quit)

    # ==================================================================
    # construction
    # ==================================================================
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open PDF…", accelerator="Ctrl+O",
                              command=self.open_pdf)
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Open recent", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Add stamp image…", accelerator="Ctrl+L",
                              command=self.add_stamp)
        file_menu.add_separator()
        file_menu.add_command(label="Save stamped PDF", accelerator="Ctrl+S",
                              command=self.save)
        file_menu.add_command(label="Save as…", accelerator="Ctrl+Shift+S",
                              command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Close document", command=self.close_document)
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Duplicate stamp", accelerator="Ctrl+D",
                              command=self.duplicate_stamp)
        edit_menu.add_command(label="Delete stamp", accelerator="Delete",
                              command=self.delete_stamp)
        edit_menu.add_command(label="Centre on page", command=self.centre_stamp)
        edit_menu.add_command(label="Reset size", command=self.reset_stamp_size)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        self.edit_menu = edit_menu

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Zoom in", accelerator="Ctrl++",
                              command=lambda: self.canvas.zoom_in())
        view_menu.add_command(label="Zoom out", accelerator="Ctrl+-",
                              command=lambda: self.canvas.zoom_out())
        view_menu.add_command(label="Fit page", accelerator="Ctrl+0",
                              command=lambda: self.canvas.fit_page())
        view_menu.add_command(label="Fit width", accelerator="Ctrl+1",
                              command=lambda: self.canvas.fit_width())
        view_menu.add_separator()
        view_menu.add_command(label="Next page", accelerator="Page Down",
                              command=lambda: self.change_page(1))
        view_menu.add_command(label="Previous page", accelerator="Page Up",
                              command=lambda: self.change_page(-1))
        menubar.add_cascade(label="View", menu=view_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Batch stamp a folder…", command=self.run_batch)
        tools_menu.add_command(label="Remove stamps from a saved PDF…",
                               command=self.remove_existing_stamps)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Keyboard shortcuts",
                              command=lambda: dialogs.ShortcutsDialog(self.root).show())
        help_menu.add_command(label=f"About {APP_NAME}",
                              command=lambda: dialogs.AboutDialog(self.root).show())
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=menubar)
        self._refresh_recent_menu()

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", height=theme.TOOLBAR_HEIGHT)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        inner = ttk.Frame(bar, style="Toolbar.TFrame")
        inner.pack(side="left", padx=theme.GAP_MD)
        right = ttk.Frame(bar, style="Toolbar.TFrame")
        right.pack(side="right", padx=theme.GAP_MD)

        self.buttons = {}

        def add(parent, key, icon, text=None, command=None, tooltip=None,
                accent=False):
            button = ToolButton(parent, icon, text=text, command=command,
                                tooltip=tooltip, accent=accent)
            button.pack(side="left")
            self.buttons[key] = button
            return button

        add(inner, "open", "open", "Open PDF", self.open_pdf,
            "Open a PDF document (Ctrl+O)")
        add(inner, "add_stamp", "add-stamp", "Add Stamp", self.add_stamp,
            "Add a logo or stamp image (Ctrl+L)", accent=True)
        add(inner, "delete_stamp", "trash", None, self.delete_stamp,
            "Remove the selected stamp (Delete)")
        ToolbarSeparator(inner).pack(side="left")
        add(inner, "undo", "undo", None, self.undo, "Undo (Ctrl+Z)")
        add(inner, "redo", "redo", None, self.redo, "Redo (Ctrl+Y)")
        ToolbarSeparator(inner).pack(side="left")
        add(inner, "zoom_out", "zoom-out", None, lambda: self.canvas.zoom_out(),
            "Zoom out (Ctrl+-)")
        add(inner, "zoom_in", "zoom-in", None, lambda: self.canvas.zoom_in(),
            "Zoom in (Ctrl++)")
        add(inner, "fit", "fit-page", None, lambda: self.canvas.fit_page(),
            "Fit the whole page (Ctrl+0)")
        ToolbarSeparator(inner).pack(side="left")
        add(inner, "batch", "batch", None, self.run_batch,
            "Stamp every PDF in a folder")

        self.save_button = ttk.Button(right, text="Save PDF", style="Primary.TButton",
                                     command=self.save)
        self.save_button.pack(side="right")
        Tooltip(self.save_button, "Export the stamped PDF (Ctrl+S)")
        self.save_as_button = ttk.Button(right, text="Save As…",
                                        style="Secondary.TButton", command=self.save_as)
        self.save_as_button.pack(side="right", padx=(0, theme.GAP_SM))
        Tooltip(self.save_as_button, "Choose where to save (Ctrl+Shift+S)")

        ttk.Frame(self.root, style="Divider.TFrame", height=1).pack(fill="x")

    def _build_body(self):
        body = ttk.Frame(self.root, style="App.TFrame")
        body.pack(fill="both", expand=True)

        # ---- left sidebar ------------------------------------------------
        self.sidebar = ScrollableColumn(body, theme.SIDEBAR_WIDTH)
        self.sidebar.pack(side="left", fill="y")
        sidebar = self.sidebar.body
        self._build_document_section(sidebar)
        self._build_stamps_section(sidebar)
        self._build_presets_section(sidebar)
        self._build_pages_section(sidebar)
        ttk.Frame(body, style="Divider.TFrame", width=1).pack(side="left", fill="y")

        # ---- properties (right) -----------------------------------------
        self.properties_column = ScrollableColumn(body, theme.PROPERTIES_WIDTH)
        self.properties_column.pack(side="right", fill="y")
        self._build_properties(self.properties_column.body)
        ttk.Frame(body, style="Divider.TFrame", width=1).pack(side="right", fill="y")

        # ---- workspace ---------------------------------------------------
        self.canvas = StampCanvas(
            body, self.store, on_select=self._on_canvas_select,
            on_live_change=self._on_canvas_live_change,
            on_commit=self._on_canvas_commit,
            on_context_menu=self._show_context_menu,
            on_status=self._on_pointer_move,
            on_zoom_change=self._on_zoom_change,
            on_double_click=self._on_canvas_double_click,
            on_page_change=self._on_canvas_page_change)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._build_context_menu()

    def _build_document_section(self, parent):
        section = Section(parent, "Document", first=True)
        section.pack(fill="x", pady=(theme.GAP_LG, 0))
        self.doc_name = ttk.Label(section.body, text="No PDF open",
                                  style="Panel.TLabel", font=theme.fonts()["body_bold"],
                                  wraplength=theme.SIDEBAR_WIDTH - 48, justify="left")
        self.doc_name.pack(anchor="w")
        self.doc_meta = ttk.Label(section.body, text="Open a PDF to begin",
                                  style="Muted.TLabel")
        self.doc_meta.pack(anchor="w", pady=(2, theme.GAP_MD))

        nav = ttk.Frame(section.body, style="Panel.TFrame")
        nav.pack(fill="x")
        self.prev_button = ToolButton(nav, "prev", tooltip="Previous page (Page Up)",
                                     command=lambda: self.change_page(-1),
                                     compact=True)
        self.prev_button.pack(side="left")
        self.page_var = tk.StringVar(value="1")
        self.page_spin = ttk.Spinbox(nav, textvariable=self.page_var, width=5,
                                     from_=1, to=1, command=self._on_page_field)
        self.page_spin.pack(side="left", padx=theme.GAP_SM)
        self.page_spin.bind("<Return>", lambda e: self._on_page_field())
        self.page_total = ttk.Label(nav, text="of 1", style="Muted.TLabel")
        self.page_total.pack(side="left")
        self.next_button = ToolButton(nav, "next", tooltip="Next page (Page Down)",
                                     command=lambda: self.change_page(1),
                                     compact=True)
        self.next_button.pack(side="right")
        self.page_stamp_hint = ttk.Label(section.body, text="", style="Faint.TLabel")
        self.page_stamp_hint.pack(anchor="w", pady=(theme.GAP_SM, 0))

    def _build_stamps_section(self, parent):
        section = Section(parent, "Stamps")
        section.pack(fill="x")
        self.stamp_tree = ttk.Treeview(section.body, columns=("pages",),
                                       show="tree headings", height=4,
                                       selectmode="browse")
        self.stamp_tree.heading("#0", text="Image")
        self.stamp_tree.heading("pages", text="Applies to")
        self.stamp_tree.column("#0", width=118, anchor="w")
        self.stamp_tree.column("pages", width=86, anchor="w")
        self.stamp_tree.pack(fill="x")
        self.stamp_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        row = ttk.Frame(section.body, style="Panel.TFrame")
        row.pack(fill="x", pady=(theme.GAP_SM, 0))
        ttk.Button(row, text="Add stamp", style="Primary.TButton",
                   command=self.add_stamp).pack(side="left")
        self.duplicate_button = ttk.Button(row, text="Duplicate",
                                          style="Secondary.TButton",
                                          command=self.duplicate_stamp)
        self.duplicate_button.pack(side="left", padx=(theme.GAP_SM, 0))

    def _build_presets_section(self, parent):
        section = Section(parent, "Position presets")
        section.pack(fill="x")
        grid = ttk.Frame(section.body, style="Panel.TFrame")
        grid.pack(anchor="w")
        self.preset_buttons = {}
        self._preset_icons = {}
        for index, (label, key) in enumerate(geo.ANCHOR_PRESETS):
            self._preset_icons[key] = (theme.anchor_icon(key, 20, False),
                                       theme.anchor_icon(key, 20, True))
            button = ttk.Button(grid, image=self._preset_icons[key][0],
                                style="Secondary.TButton", padding=(6, 4),
                                command=lambda k=key: self.apply_preset(k))
            button.grid(row=index // 3, column=index % 3, padx=2, pady=2)
            Tooltip(button, f"Move the stamp to {label.lower()}")
            self.preset_buttons[key] = button
        self._paint_preset_buttons()

        margins = ttk.Frame(section.body, style="Panel.TFrame")
        margins.pack(fill="x", pady=(theme.GAP_SM, 0))
        self.margin_x_field = NumberField(margins, "Margin X", 24, minimum=-2000,
                                         maximum=2000, on_change=self._on_margin,
                                         suffix="pt",
                                         tooltip="Distance from the left/right edge")
        self.margin_x_field.pack(side="left")
        self.margin_y_field = NumberField(margins, "Margin Y", 24, minimum=-2000,
                                         maximum=2000, on_change=self._on_margin,
                                         suffix="pt",
                                         tooltip="Distance from the top/bottom edge")
        self.margin_y_field.pack(side="left", padx=(theme.GAP_MD, 0))

    def _build_pages_section(self, parent):
        section = Section(parent, "Apply stamp to")
        section.pack(fill="x")
        self.page_mode = tk.StringVar(value=self.config.get("page_selection_mode",
                                                           "all"))
        for label, key in PAGE_MODE_LABELS:
            ttk.Radiobutton(section.body, text=label, value=key,
                            variable=self.page_mode,
                            command=self._on_page_mode).pack(anchor="w")
        self.range_var = tk.StringVar()
        self.range_entry = ttk.Entry(section.body, textvariable=self.range_var)
        self.range_entry.pack(fill="x", pady=(theme.GAP_SM, 2))
        self.range_var.trace_add("write", lambda *_: self._on_page_mode())
        ttk.Label(section.body, text="Example:  1-3, 5, 9-", style="Faint.TLabel") \
            .pack(anchor="w")

        ttk.Label(section.body, text="Skip these pages", style="Muted.TLabel") \
            .pack(anchor="w", pady=(theme.GAP_MD, 0))
        self.skip_var = tk.StringVar()
        self.skip_entry = ttk.Entry(section.body, textvariable=self.skip_var)
        self.skip_entry.pack(fill="x", pady=(2, 2))
        self.skip_var.trace_add("write", lambda *_: self._on_skip_field())
        ttk.Label(section.body, text="Leave blank to stamp every selected page",
                  style="Faint.TLabel").pack(anchor="w")
        self.pages_summary = ttk.Label(section.body, text="", style="Muted.TLabel",
                                       wraplength=theme.SIDEBAR_WIDTH - 48,
                                       justify="left")
        self.pages_summary.pack(anchor="w", pady=(theme.GAP_SM, 0))

    def _build_properties(self, parent):
        header = ttk.Frame(parent, style="Panel.TFrame")
        header.pack(fill="x", padx=theme.GAP_LG, pady=(theme.GAP_LG, 0))
        ttk.Label(header, text="STAMP PROPERTIES", style="Section.TLabel") \
            .pack(anchor="w")
        self.properties_hint = ttk.Label(parent, style="Muted.TLabel",
                                        text="Select a stamp on the page to edit it.",
                                        wraplength=theme.PROPERTIES_WIDTH - 40,
                                        justify="left")
        self.properties_hint.pack(anchor="w", padx=theme.GAP_LG,
                                  pady=(theme.GAP_SM, 0))

        self.properties_body = ttk.Frame(parent, style="Panel.TFrame")
        self.properties_body.pack(fill="both", expand=True)

        image_row = ttk.Frame(self.properties_body, style="Panel.TFrame")
        image_row.pack(fill="x", padx=theme.GAP_LG, pady=(theme.GAP_MD, 0))
        self.stamp_image_label = ttk.Label(image_row, text="-", style="Panel.TLabel",
                                          wraplength=theme.PROPERTIES_WIDTH - 60,
                                          justify="left")
        self.stamp_image_label.pack(anchor="w")
        self.transparency_label = ttk.Label(image_row, text="", style="Faint.TLabel")
        self.transparency_label.pack(anchor="w")
        ttk.Button(image_row, text="Replace image…", style="Link.TButton",
                   command=self.replace_stamp_image).pack(anchor="w")

        position = Section(self.properties_body, "Position")
        position.pack(fill="x", pady=(theme.GAP_MD, 0))
        row = ttk.Frame(position.body, style="Panel.TFrame")
        row.pack(fill="x")
        self.x_field = NumberField(row, "X", 0, on_change=self._on_position_field,
                                  suffix="pt", tooltip="Distance from the page's "
                                                       "left edge")
        self.x_field.pack(side="left")
        self.y_field = NumberField(row, "Y", 0, on_change=self._on_position_field,
                                  suffix="pt", tooltip="Distance from the page's "
                                                       "top edge")
        self.y_field.pack(side="left", padx=(theme.GAP_MD, 0))

        size = Section(self.properties_body, "Size")
        size.pack(fill="x")
        row = ttk.Frame(size.body, style="Panel.TFrame")
        row.pack(fill="x")
        self.width_field = NumberField(row, "Width", 160, minimum=4, maximum=4000,
                                      on_change=self._on_size_field, suffix="pt")
        self.width_field.pack(side="left")
        self.height_field = NumberField(row, "Height", 80, minimum=4, maximum=4000,
                                       on_change=self._on_size_field, suffix="pt")
        self.height_field.pack(side="left", padx=(theme.GAP_MD, 0))
        self.keep_ratio_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(size.body, text="Maintain aspect ratio",
                        variable=self.keep_ratio_var,
                        command=self._on_keep_ratio).pack(anchor="w",
                                                          pady=(theme.GAP_SM, 0))
        ttk.Button(size.body, text="Reset to image size", style="Link.TButton",
                   command=self.reset_stamp_size).pack(anchor="w")

        rotation = Section(self.properties_body, "Rotation")
        rotation.pack(fill="x")
        self.rotation_field = NumberField(rotation.body, "Angle", 0, minimum=-360,
                                         maximum=360, step=5,
                                         on_change=self._on_rotation_field,
                                         suffix="°",
                                         tooltip="Any angle; drag the round handle "
                                                 "on the page for free rotation")
        self.rotation_field.pack(anchor="w")
        quick = ttk.Frame(rotation.body, style="Panel.TFrame")
        quick.pack(fill="x", pady=(theme.GAP_SM, 0))
        for angle in (0, 90, 180, 270):
            button = ttk.Button(quick, text=f"{angle}°", width=4,
                                style="Secondary.TButton", padding=(2, 4),
                                command=lambda a=angle: self.set_rotation(a))
            button.pack(side="left", padx=(0, 3))
            Tooltip(button, f"Rotate to {angle}°")

        opacity = Section(self.properties_body, "Opacity")
        opacity.pack(fill="x")
        row = ttk.Frame(opacity.body, style="Panel.TFrame")
        row.pack(fill="x")
        self.opacity_var = tk.IntVar(value=100)
        self.opacity_scale = ttk.Scale(row, from_=5, to=100, orient="horizontal",
                                      variable=self.opacity_var,
                                      command=self._on_opacity_slider)
        self.opacity_scale.pack(side="left", fill="x", expand=True)
        self.opacity_label = ttk.Label(row, text="100%", style="Muted.TLabel",
                                       width=5, anchor="e")
        self.opacity_label.pack(side="left", padx=(theme.GAP_SM, 0))

        this_page = Section(self.properties_body, "This page")
        this_page.pack(fill="x")
        self.page_state_label = ttk.Label(
            this_page.body, style="Muted.TLabel", justify="left",
            wraplength=theme.PROPERTIES_WIDTH - 48,
            text="Shared with every page this stamp applies to.")
        self.page_state_label.pack(anchor="w")
        self.skip_page_button = ttk.Button(this_page.body, text="Skip on this page",
                                          style="Secondary.TButton",
                                          command=self.toggle_skip_page)
        self.skip_page_button.pack(fill="x", pady=(theme.GAP_SM, 0))
        Tooltip(self.skip_page_button,
                "Leave this one page unstamped, keeping the rest")
        self.customise_button = ttk.Button(this_page.body,
                                          text="Customise for this page",
                                          style="Secondary.TButton",
                                          command=self.toggle_customise_page)
        self.customise_button.pack(fill="x", pady=(theme.GAP_XS, 0))
        Tooltip(self.customise_button,
                "Give this page its own position, size, angle, opacity and image")
        self.page_image_button = ttk.Button(this_page.body,
                                           text="Different image on this page…",
                                           style="Link.TButton",
                                           command=self.replace_page_image)
        self.page_image_button.pack(anchor="w", pady=(2, 0))

        arrange = Section(self.properties_body, "Arrange")
        arrange.pack(fill="x")
        row = ttk.Frame(arrange.body, style="Panel.TFrame")
        row.pack(fill="x")
        self.forward_button = ToolButton(row, "forward", "Forward",
                                        command=self.bring_forward,
                                        tooltip="Bring the stamp above the others",
                                        compact=True)
        self.forward_button.pack(side="left")
        self.backward_button = ToolButton(row, "backward", "Backward",
                                         command=self.send_backward,
                                         tooltip="Send the stamp below the others",
                                         compact=True)
        self.backward_button.pack(side="left", padx=(theme.GAP_SM, 0))
        row2 = ttk.Frame(arrange.body, style="Panel.TFrame")
        row2.pack(fill="x", pady=(theme.GAP_SM, 0))
        ttk.Button(row2, text="Centre on page", style="Secondary.TButton",
                   command=self.centre_stamp).pack(side="left")
        ttk.Button(row2, text="Delete", style="Danger.TButton",
                   command=self.delete_stamp).pack(side="right")

    def _build_status(self):
        self.status = StatusBar(self.root)
        self.status.pack(side="bottom", fill="x")

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Duplicate", command=self.duplicate_stamp)
        self.context_menu.add_command(label="Delete", command=self.delete_stamp)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Bring forward", command=self.bring_forward)
        self.context_menu.add_command(label="Send backward", command=self.send_backward)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Skip on this page",
                                      command=self.toggle_skip_page)
        self.context_menu.add_command(label="Customise for this page",
                                      command=self.toggle_customise_page)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Centre on page", command=self.centre_stamp)
        self.context_menu.add_command(label="Reset size", command=self.reset_stamp_size)
        self.context_menu.add_command(label="Reset rotation",
                                      command=lambda: self.set_rotation(0))
        self.empty_menu = tk.Menu(self.root, tearoff=0)
        self.empty_menu.add_command(label="Add stamp image…", command=self.add_stamp)
        self.empty_menu.add_separator()
        self.empty_menu.add_command(label="Fit page",
                                    command=lambda: self.canvas.fit_page())
        self.empty_menu.add_command(label="Fit width",
                                    command=lambda: self.canvas.fit_width())

    def _bind_shortcuts(self):
        root = self.root
        bindings = {
            "<Control-o>": lambda e: self.open_pdf(),
            "<Control-l>": lambda e: self.add_stamp(),
            "<Control-s>": lambda e: self.save(),
            "<Control-Shift-S>": lambda e: self.save_as(),
            "<Control-z>": lambda e: self.undo(),
            "<Control-y>": lambda e: self.redo(),
            "<Control-d>": lambda e: self.duplicate_stamp(),
            "<Control-plus>": lambda e: self.canvas.zoom_in(),
            "<Control-equal>": lambda e: self.canvas.zoom_in(),
            "<Control-minus>": lambda e: self.canvas.zoom_out(),
            "<Control-Key-0>": lambda e: self.canvas.fit_page(),
            "<Control-Key-1>": lambda e: self.canvas.fit_width(),
            "<Next>": lambda e: self.change_page(1),
            "<Prior>": lambda e: self.change_page(-1),
            "<F1>": lambda e: dialogs.ShortcutsDialog(self.root).show(),
        }
        for sequence, handler in bindings.items():
            root.bind_all(sequence, handler)
        # Delete only applies when the canvas has focus, so it cannot eat a
        # character while the user is typing in a field.
        self.canvas.canvas.bind("<Delete>", lambda e: self.delete_stamp())
        self.canvas.canvas.bind("<BackSpace>", lambda e: self.delete_stamp())

    def _enable_drop_targets(self):
        """OS-level file drag-and-drop, when the optional tkdnd package is present."""
        if not self.dnd_available:
            return
        try:
            from tkinterdnd2 import DND_FILES
            self.canvas._dnd_hint = True
            for widget in (self.canvas.canvas, self.root):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
                widget.dnd_bind("<<DragEnter>>", lambda e: self.status.set_message(
                    "Drop to open the PDF or add the image"))
                widget.dnd_bind("<<DragLeave>>",
                                lambda e: self.status.set_message("Ready"))
            log.info("File drag-and-drop enabled")
        except Exception as exc:                       # noqa: BLE001
            log.info("Drag-and-drop unavailable: %s", exc)

    def _on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        for path in paths:
            path = path.strip("{}")
            if path.lower().endswith(".pdf"):
                self.load_pdf(path)
            elif image_service.is_supported(path):
                self._add_stamp_from_path(path)
        return event.action if hasattr(event, "action") else None

    # ==================================================================
    # document
    # ==================================================================
    def open_pdf(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Open PDF",
            initialdir=self.config.get("last_pdf_folder") or None,
            filetypes=pdf_service.PDF_FILE_TYPES)
        if path:
            self.load_pdf(path)

    def load_pdf(self, path):
        try:
            document = pdf_service.PdfDocument(path)
        except AppError as exc:
            dialogs.show_error(self.root, exc, "Cannot open this PDF")
            return False
        if self.document:
            self.document.close()
        self.document = document
        self.pdf_path = document.path
        self.output_path = self._suggested_output(document.path)
        self.config.set("last_pdf_folder", os.path.dirname(document.path))
        self.config.add_recent("recent_files", document.path)
        self.config.save()
        self._refresh_recent_menu()
        self.canvas.set_document(document, self.layer)
        self.dirty = False
        self.status.set_message(f"Opened {document.name}", "success")
        self._refresh_all()
        return True

    def _suggested_output(self, path):
        folder = self.config.get("default_output_folder") or os.path.dirname(path)
        base, extension = os.path.splitext(os.path.basename(path))
        suffix = self.config.get("output_suffix") or "_stamped"
        return os.path.join(folder, f"{base}{suffix}{extension}")

    def close_document(self):
        if not self.document:
            return
        if not self._confirm_discard():
            return
        self.document.close()
        self.document = None
        self.pdf_path = None
        self.output_path = None
        self.layer = StampLayer()
        self.history.reset(self.layer.snapshot())
        self.canvas.set_document(None, self.layer)
        self.dirty = False
        self.status.set_message("Document closed")
        self._refresh_all()

    def _confirm_discard(self):
        if not self.dirty or not self.layer.stamps:
            return True
        return dialogs.ask_yes_no(
            self.root, "Discard stamps?",
            "This document has stamps that have not been saved.\n\n"
            "Closing it now will discard them.",
            confirm="Discard", cancel="Keep editing")

    def change_page(self, step):
        if not self.document:
            return
        self.canvas.set_page(self.canvas.page_index + step)
        self._refresh_page_controls()
        self._refresh_status()

    def _on_page_field(self):
        if not self.document:
            return
        try:
            index = int(float(self.page_var.get())) - 1
        except (TypeError, ValueError):
            return
        self.canvas.set_page(index)
        self._refresh_page_controls()
        self._refresh_status()

    # ==================================================================
    # stamps
    # ==================================================================
    def add_stamp(self):
        if not self.document:
            if not dialogs.ask_yes_no(self.root, "Open a PDF first",
                                      "A PDF must be open before adding a stamp.\n\n"
                                      "Would you like to open one now?",
                                      confirm="Open PDF…", kind="info"):
                return
            if not self._open_and_wait():
                return
        path = filedialog.askopenfilename(
            parent=self.root, title="Choose a logo or stamp image",
            initialdir=self.config.get("last_logo_folder") or None,
            filetypes=image_service.FILE_TYPES)
        if path:
            self._add_stamp_from_path(path)

    def _open_and_wait(self):
        self.open_pdf()
        return self.document is not None

    def _add_stamp_from_path(self, path):
        if not self.document:
            self.status.set_message("Open a PDF before adding a stamp", "warning")
            return
        try:
            natural = self.store.natural_size(path)
        except AppError as exc:
            dialogs.show_error(self.root, exc, "Cannot use this image")
            return

        page_size = self.document.page_size(self.canvas.page_index)
        # Sensible default: a quarter of the page width, aspect preserved.
        target_width = min(page_size[0] * 0.25,
                           float(self.config.get("stamp_width", 160.0)) * 1.5)
        width, height = geo.fit_size(natural, (target_width,
                                              target_width * natural[1] / natural[0]),
                                    True)
        stamp = Stamp(image_path=path, natural_size=natural, width=width,
                      height=height, keep_ratio=True,
                      opacity=int(self.config.get("stamp_opacity", 100)),
                      anchor=self.config.get("stamp_anchor", "bottom-right"),
                      margin_x=float(self.config.get("stamp_margin_x", 24.0)),
                      margin_y=float(self.config.get("stamp_margin_y", 24.0)),
                      pages=PageSelection(self.page_mode.get(), self.range_var.get()))
        self.layer.add(stamp)
        self.config.set("last_logo_folder", os.path.dirname(path))
        self.config.add_recent("recent_logos", path)
        self.config.save()
        self._commit_change(f"Added {stamp.name}")
        self.canvas.canvas.focus_set()

    def replace_stamp_image(self):
        stamp = self.layer.selected
        if stamp is None:
            return
        path = filedialog.askopenfilename(
            parent=self.root, title="Choose a different image",
            initialdir=os.path.dirname(stamp.image_path) or None,
            filetypes=image_service.FILE_TYPES)
        if not path:
            return
        try:
            natural = self.store.natural_size(path)
        except AppError as exc:
            dialogs.show_error(self.root, exc, "Cannot use this image")
            return
        stamp.image_path = path
        stamp.natural_size = natural
        self._commit_change("Replaced the stamp image")

    def duplicate_stamp(self):
        stamp = self.layer.selected
        if stamp is None:
            return
        self.layer.duplicate(stamp)
        self._commit_change("Duplicated the stamp")

    def delete_stamp(self):
        stamp = self.layer.selected
        if stamp is None:
            self.status.set_message("Select a stamp to delete", "warning")
            return
        name = stamp.name
        self.layer.remove(stamp)
        self._commit_change(f"Deleted {name}")

    def bring_forward(self):
        stamp = self.layer.selected
        if stamp is not None and self.layer.raise_stamp(stamp):
            self._commit_change("Brought the stamp forward")

    def send_backward(self):
        stamp = self.layer.selected
        if stamp is not None and self.layer.lower_stamp(stamp):
            self._commit_change("Sent the stamp backward")

    def centre_stamp(self):
        stamp = self.layer.selected
        if stamp is None or not self.document:
            return
        stamp.anchor = "mid-center"
        self._commit_change("Centred the stamp")

    def reset_stamp_size(self):
        stamp = self.layer.selected
        if stamp is None or not self.document:
            return
        page_size = self.document.page_size(self.canvas.page_index)
        natural = stamp.natural_size
        width = min(natural[0], page_size[0] * 0.5)
        stamp.width = width
        stamp.height = width * natural[1] / natural[0]
        self._commit_change("Reset the stamp size")

    def set_rotation(self, angle):
        stamp = self.layer.selected
        if stamp is None:
            return
        stamp.set_values({"rotation": float(angle) % 360}, self._edit_page(stamp))
        self._commit_change(f"Rotation set to {int(stamp.rotation)}°")

    def toggle_skip_page(self):
        """Skip (or un-skip) the stamp on the page being viewed."""
        stamp = self.layer.selected
        if stamp is None or not self.document:
            self.status.set_message("Select a stamp first", "warning")
            return
        page = self.canvas.page_index
        skipped = stamp.pages.toggle_skipped(page, self.document.page_count)
        self._commit_change(
            f"{stamp.name} {'skipped on' if skipped else 'restored on'} "
            f"page {page + 1}")

    def toggle_customise_page(self):
        """Give this page its own settings, or return it to the shared ones."""
        stamp = self.layer.selected
        if stamp is None or not self.document:
            self.status.set_message("Select a stamp first", "warning")
            return
        page = self.canvas.page_index
        if stamp.has_override(page):
            stamp.clear_override(page)
            self._commit_change(f"Page {page + 1} follows the shared settings again")
        else:
            stamp.customise(page, self.document.page_size(page))
            self._commit_change(f"Page {page + 1} now has its own settings")

    def replace_page_image(self):
        """Use a different logo on this page only."""
        stamp = self.layer.selected
        if stamp is None or not self.document:
            self.status.set_message("Select a stamp first", "warning")
            return
        page = self.canvas.page_index
        path = filedialog.askopenfilename(
            parent=self.root, title=f"Choose the image for page {page + 1}",
            initialdir=self.config.get("last_logo_folder") or None,
            filetypes=image_service.FILE_TYPES)
        if not path:
            return
        try:
            natural = self.store.natural_size(path)
        except AppError as exc:
            dialogs.show_error(self.root, exc, "Cannot use this image")
            return
        stamp.customise(page, self.document.page_size(page))
        stamp.set_values({"image_path": path, "natural_size": natural}, page)
        self._commit_change(f"Page {page + 1} uses {os.path.basename(path)}")

    def apply_preset(self, anchor):
        stamp = self.layer.selected
        if stamp is None:
            self.config.set("stamp_anchor", anchor)
            self.status.set_message("Preset saved as the default for new stamps")
            self._paint_preset_buttons(anchor)
            return
        stamp.anchor = anchor
        stamp.margin_x = self.margin_x_field.get() or 0.0
        stamp.margin_y = self.margin_y_field.get() or 0.0
        self._commit_change(f"Moved to {anchor.replace('-', ' ')}")

    # ==================================================================
    # field handlers
    # ==================================================================
    def _edit_page(self, stamp):
        """The page whose override should receive edits, or None for shared."""
        page = self.canvas.page_index
        if stamp is not None and stamp.has_override(page):
            return page
        return None

    def _on_position_field(self, _value=None):
        stamp = self.layer.selected
        if stamp is None or self._suspend_fields:
            return
        x, y = self.x_field.get(), self.y_field.get()
        if x is None or y is None:
            return
        stamp.move_to(x, y, self._edit_page(stamp))
        self.canvas.redraw()
        self._schedule_history("Moved the stamp")

    def _on_size_field(self, _value=None):
        stamp = self.layer.selected
        if stamp is None or self._suspend_fields:
            return
        width, height = self.width_field.get(), self.height_field.get()
        if width is None or height is None:
            return
        page = self._edit_page(stamp)
        natural = stamp.natural_for(page)
        if stamp.keep_ratio and natural[0] and natural[1]:
            ratio = natural[1] / natural[0]
            if abs(width - stamp.value_for("width", page)) > 1e-6:  # width edited
                height = width * ratio
            else:
                width = height / ratio
            self._suspend_fields = True
            self.width_field.set(width)
            self.height_field.set(height)
            self._suspend_fields = False
        stamp.set_values({"width": width, "height": height}, page)
        self.canvas.redraw()
        self._schedule_history("Resized the stamp")

    def _on_keep_ratio(self):
        stamp = self.layer.selected
        if stamp is None:
            self.config.set("keep_aspect_ratio", bool(self.keep_ratio_var.get()))
            return
        stamp.keep_ratio = bool(self.keep_ratio_var.get())
        if stamp.keep_ratio:
            box = stamp.box_on(self.canvas.page_size())
            stamp.width, stamp.height = box[2], box[3]
        self._commit_change("Aspect ratio " +
                            ("locked" if stamp.keep_ratio else "unlocked"))

    def _on_rotation_field(self, _value=None):
        stamp = self.layer.selected
        if stamp is None or self._suspend_fields:
            return
        angle = self.rotation_field.get()
        if angle is None:
            return
        stamp.set_values({"rotation": float(angle) % 360}, self._edit_page(stamp))
        self.canvas.redraw()
        self._schedule_history("Rotated the stamp")

    def _on_opacity_slider(self, _value=None):
        stamp = self.layer.selected
        percent = int(self.opacity_var.get())
        self.opacity_label.configure(text=f"{percent}%")
        if stamp is None or self._suspend_fields:
            self.config.set("stamp_opacity", percent)
            return
        stamp.set_values({"opacity": percent}, self._edit_page(stamp))
        self.canvas.redraw()
        self._schedule_history("Changed the opacity")

    def _on_margin(self, _value=None):
        stamp = self.layer.selected
        margin_x = self.margin_x_field.get()
        margin_y = self.margin_y_field.get()
        if margin_x is None or margin_y is None:
            return
        self.config.set("stamp_margin_x", float(margin_x))
        self.config.set("stamp_margin_y", float(margin_y))
        if stamp is None or self._suspend_fields:
            return
        if stamp.anchor in geo.ANCHOR_KEYS:
            stamp.margin_x, stamp.margin_y = float(margin_x), float(margin_y)
            self.canvas.redraw()
            self._schedule_history("Changed the margins")

    def _on_skip_field(self):
        """The "skip these pages" box edits the selected stamp's skip list."""
        stamp = self.layer.selected
        if stamp is None or self._suspend_fields:
            return
        stamp.pages.skip = self.skip_var.get()
        self.canvas.redraw()
        self._refresh_stamp_tree()
        self._refresh_pages_summary()
        self._refresh_page_state()
        self._schedule_history("Changed the skipped pages")

    def _on_page_mode(self):
        mode = self.page_mode.get()
        state = "normal" if mode == "range" else "disabled"
        self.range_entry.configure(state=state)
        self.config.set("page_selection_mode", mode)
        stamp = self.layer.selected
        if stamp is not None and not self._suspend_fields:
            stamp.pages = PageSelection(mode, self.range_var.get(),
                                        self.skip_var.get())
            self.canvas.redraw()
            self._refresh_stamp_tree()
            self._schedule_history("Changed the page selection")
        self._refresh_pages_summary()

    # ==================================================================
    # canvas callbacks
    # ==================================================================
    def _on_canvas_select(self, stamp):
        self._refresh_properties()
        self._refresh_stamp_tree()
        self._refresh_status()

    def _on_canvas_live_change(self, stamp):
        self._refresh_properties(values_only=True)
        self._refresh_status()

    def _on_canvas_commit(self, stamp, mode):
        labels = {"move": "Moved the stamp", "resize": "Resized the stamp",
                  "rotate": "Rotated the stamp", "nudge": "Moved the stamp"}
        self._commit_change(labels.get(mode, "Edited the stamp"), redraw=False)

    def _on_canvas_double_click(self, stamp):
        if stamp is None:
            self.add_stamp()

    def _on_pointer_move(self, page_point):
        if page_point is None:
            self.status.set_selection(self._selection_text())
            return
        self.status.set_selection(f"x {page_point[0]:.0f}, y {page_point[1]:.0f} pt")

    def _on_canvas_page_change(self, index):
        """The user scrolled (or clicked) onto another page."""
        self._refresh_properties()      # the panel shows this page's values
        self._refresh_page_controls()
        self._refresh_stamp_tree()
        self._refresh_pages_summary()
        self._refresh_status()

    def _on_zoom_change(self, zoom, mode):
        label = {"fit-page": "Fit page", "fit-width": "Fit width"}.get(mode, "")
        self.status.set_zoom(f"{zoom * 100:.0f}%" + (f"  {label}" if label else ""))

    def _show_context_menu(self, event, stamp):
        menu = self.context_menu if stamp is not None else self.empty_menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_tree_select(self, _event):
        selection = self.stamp_tree.selection()
        if not selection:
            return
        stamp_id = int(selection[0])
        for stamp in self.layer.stamps:
            if stamp.stamp_id == stamp_id and stamp.stamp_id != self.layer.selected_id:
                self.canvas.select_stamp(stamp)
                break

    # ==================================================================
    # history
    # ==================================================================
    def _commit_change(self, message="", redraw=True):
        self.dirty = True
        self.history.push(self.layer.snapshot())
        if redraw:
            self.canvas.redraw()
        if message:
            self.status.set_message(message)
        self._refresh_all()

    def _schedule_history(self, message=""):
        """Coalesce rapid edits (typing, dragging a slider) into one undo step."""
        self.dirty = True
        if self._history_job:
            self.root.after_cancel(self._history_job)
        self._history_job = self.root.after(
            450, lambda: self._flush_history(message))
        self._refresh_stamp_tree()
        self._refresh_toolbar_state()

    def _flush_history(self, message=""):
        self._history_job = None
        self.history.push(self.layer.snapshot())
        if message:
            self.status.set_message(message)
        self._refresh_toolbar_state()

    def undo(self):
        if self._history_job:
            self.root.after_cancel(self._history_job)
            self._history_job = None
            self.history.push(self.layer.snapshot())
        snapshot = self.history.undo()
        if snapshot is None:
            self.status.set_message("Nothing to undo")
            return
        self.layer.restore(snapshot)
        self.canvas.redraw()
        self.status.set_message("Undone")
        self._refresh_all()

    def redo(self):
        snapshot = self.history.redo()
        if snapshot is None:
            self.status.set_message("Nothing to redo")
            return
        self.layer.restore(snapshot)
        self.canvas.redraw()
        self.status.set_message("Redone")
        self._refresh_all()

    # ==================================================================
    # saving
    # ==================================================================
    def save(self):
        if not self._ready_to_save():
            return
        if not self.output_path:
            return self.save_as()
        self._export(self.output_path)

    def save_as(self):
        if not self._ready_to_save():
            return
        initial = self.output_path or self._suggested_output(self.pdf_path)
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save stamped PDF",
            defaultextension=".pdf", filetypes=pdf_service.PDF_FILE_TYPES,
            initialdir=os.path.dirname(initial),
            initialfile=os.path.basename(initial))
        if path:
            self.output_path = path
            self._export(path)

    def _ready_to_save(self):
        if not self.document:
            self.status.set_message("Open a PDF first", "warning")
            return False
        if not self.layer.stamps:
            dialogs.show_info(self.root, "Nothing to save",
                              "Add at least one stamp before saving.",
                              kind="warning")
            return False
        return True

    def _export(self, path):
        same_file = os.path.exists(path) and self.pdf_path and \
            os.path.normcase(os.path.abspath(path)) == \
            os.path.normcase(os.path.abspath(self.pdf_path))
        if same_file:
            if not dialogs.ask_yes_no(
                    self.root, "Replace the original?",
                    "This will write the stamps into the original PDF and replace "
                    "it.\n\nThe original file cannot be recovered afterwards.",
                    confirm="Replace original", cancel="Cancel"):
                return
        elif os.path.exists(path) and self.config.get("confirm_overwrite", True):
            if not dialogs.ask_yes_no(
                    self.root, "File already exists",
                    f"{os.path.basename(path)} already exists in that folder.\n\n"
                    "Do you want to replace it?",
                    confirm="Replace", cancel="Cancel"):
                return

        stamps = list(self.layer.stamps)
        source = self.pdf_path
        current_page = self.canvas.page_index
        dpi = int(self.config.get("export_dpi", 300))
        # Windows cannot replace a file that is still open, so release the preview.
        if same_file:
            self.document.close()
            self.document = None

        def work(progress, cancelled):
            return pdf_service.export_stamped_pdf(
                source, path, stamps, store=self.store, dpi=dpi,
                current_page=current_page,
                progress=lambda done, total, page: progress(
                    done, total, f"Stamping page {page + 1}"),
                cancelled=cancelled)

        try:
            summary = dialogs.ProgressDialog(
                self.root, "Saving PDF",
                f"Writing {os.path.basename(path)}", work).run()
        except AppError as exc:
            if same_file:
                self._reopen(source, current_page)
            dialogs.show_error(self.root, exc, "The PDF could not be saved")
            return
        except Exception as exc:                       # noqa: BLE001
            if same_file:
                self._reopen(source, current_page)
            dialogs.show_error(self.root, exc, "The PDF could not be saved")
            return

        if summary is None:                            # cancelled
            if same_file:
                self._reopen(source, current_page)
            self.status.set_message("Saving cancelled", "warning")
            return

        self.dirty = False
        self.output_path = path
        if same_file:
            self._reopen(path, current_page)
        self.status.set_message(
            f"Saved {os.path.basename(path)} — {summary['placements']} stamp(s) on "
            f"{summary['pages']} page(s)", "success")
        if dialogs.MessageDialog(
                self.root, "PDF saved",
                f"{summary['placements']} stamp(s) were written to "
                f"{summary['pages']} page(s).\n\n{path}",
                kind="success", buttons=("Close", "Open folder"),
                default="Close").show() == "Open folder":
            try:
                os.startfile(os.path.dirname(path))    # noqa: S606
            except OSError as exc:
                log.warning("Could not open folder: %s", exc)

    def _reopen(self, path, page_index=0):
        try:
            self.document = pdf_service.PdfDocument(path)
            self.pdf_path = self.document.path
            self.canvas.set_document(self.document, self.layer)
            self.canvas.set_page(page_index)
        except AppError as exc:
            dialogs.show_error(self.root, exc, "Cannot reopen the document")
        self._refresh_all()

    # ==================================================================
    # tools
    # ==================================================================
    def run_batch(self):
        if not self.layer.stamps:
            dialogs.show_info(self.root, "Add a stamp first",
                              "Batch stamping applies the stamps you have set up "
                              "here to every PDF in a folder.\n\n"
                              "Open a PDF, add and position a stamp, then run the "
                              "batch.", kind="info")
            return
        summary = ", ".join(f"{stamp.name} ({stamp.pages.describe(1, 0)})"
                            for stamp in self.layer.stamps)
        options = dialogs.BatchDialog(
            self.root, f"Stamps: {summary}", self.config,
            lambda label, initial: filedialog.askdirectory(
                parent=self.root, title=label, initialdir=initial or None)).show()
        if not options:
            return
        self.config.set("last_batch_input", options["input"])
        self.config.set("last_batch_output", options["output"])
        self.config.save()

        stamps = list(self.layer.stamps)
        dpi = int(self.config.get("export_dpi", 300))

        def work(progress, cancelled):
            return batch_service.process_folder(
                options["input"], options["output"], stamps, store=self.store,
                suffix=options["suffix"], recursive=options["recursive"], dpi=dpi,
                progress=lambda done, total, name: progress(done, total, name),
                cancelled=cancelled)

        try:
            results = dialogs.ProgressDialog(self.root, "Batch stamping",
                                             "Processing PDF files", work).run()
        except AppError as exc:
            dialogs.show_error(self.root, exc, "Batch stamping failed")
            return
        if not results:
            self.status.set_message("Batch stamping cancelled", "warning")
            return
        dialogs.BatchResultsDialog(self.root, results).show()
        succeeded = sum(1 for result in results if result.ok)
        self.status.set_message(f"Batch finished: {succeeded} of {len(results)} "
                                f"file(s) stamped", "success")

    def remove_existing_stamps(self):
        if not self.document:
            self.status.set_message("Open a stamped PDF first", "warning")
            return
        answer = dialogs.RemoveStampsDialog(self.root, self.document.page_count,
                                           self.canvas.page_index).show()
        if not answer:
            return
        spec, tagged_only = answer
        try:
            pages = parse_page_spec(spec, self.document.page_count)
        except AppError as exc:
            dialogs.show_error(self.root, exc, "Check the page numbers")
            return

        source = self.pdf_path
        base, extension = os.path.splitext(source)
        output = filedialog.asksaveasfilename(
            parent=self.root, title="Save the PDF without stamps",
            defaultextension=".pdf", filetypes=pdf_service.PDF_FILE_TYPES,
            initialdir=os.path.dirname(source),
            initialfile=os.path.basename(f"{base}_unstamped{extension}"))
        if not output:
            return
        try:
            touched, total = pdf_service.remove_stamps(source, output, pages,
                                                       tagged_only=tagged_only)
        except AppError as exc:
            dialogs.show_error(self.root, exc, "Stamps could not be removed")
            return

        if not total:
            dialogs.show_info(
                self.root, "No stamps found",
                "No stamp added by this app was found on the pages you chose.\n\n"
                "If the stamp came from another program, try again and tick "
                "'Also remove stamps added by other tools'.", kind="warning")
            return
        dialogs.show_info(self.root, "Stamps removed",
                          f"Removed {total} stamp(s) from {touched} page(s).\n\n"
                          f"{output}", kind="success")
        self.load_pdf(output)

    # ==================================================================
    # refresh
    # ==================================================================
    def _refresh_all(self):
        self._refresh_document_section()
        self._refresh_page_controls()
        self._refresh_stamp_tree()
        self._refresh_properties()
        self._refresh_toolbar_state()
        self._refresh_pages_summary()
        self._refresh_status()

    def _refresh_document_section(self):
        if not self.document:
            self.doc_name.configure(text="No PDF open")
            self.doc_meta.configure(text="Open a PDF to begin")
            self.page_stamp_hint.configure(text="")
            return
        self.doc_name.configure(text=self.document.name)
        index = self.canvas.page_index
        self.doc_meta.configure(
            text=f"{self.document.page_count} page(s) · "
                 f"{self.document.page_label(index)}"
                 + (f" · rotated {self.document.page_rotation(index)}°"
                    if self.document.page_rotation(index) else ""))
        try:
            existing = self.document.has_stamps(index)
        except AppError:
            existing = False
        self.page_stamp_hint.configure(
            text="This page already contains a stamp from an earlier save."
            if existing else "")

    def _refresh_page_controls(self):
        enabled = self.document is not None
        count = self.document.page_count if enabled else 1
        index = self.canvas.page_index if enabled else 0
        self.page_spin.configure(to=count,
                                 state="normal" if enabled else "disabled")
        self.page_var.set(str(index + 1))
        self.page_total.configure(text=f"of {count}")
        self.prev_button.set_enabled(enabled and index > 0)
        self.next_button.set_enabled(enabled and index < count - 1)
        self._refresh_document_section()

    def _refresh_stamp_tree(self):
        selected = self.layer.selected_id
        self.stamp_tree.delete(*self.stamp_tree.get_children())
        count = self.document.page_count if self.document else 1
        page = self.canvas.page_index if self.document else 0
        for stamp in reversed(self.layer.stamps):      # topmost first
            scope = stamp.pages.describe(count, page)
            if stamp.overrides:
                scope += f" (+{len(stamp.overrides)} custom)"
            self.stamp_tree.insert("", "end", iid=str(stamp.stamp_id),
                                   text=stamp.name, values=(scope,))
        if selected is not None and self.stamp_tree.exists(str(selected)):
            self.stamp_tree.selection_set(str(selected))

    def _refresh_properties(self, values_only=False):
        stamp = self.layer.selected
        fields = (self.x_field, self.y_field, self.width_field, self.height_field,
                  self.rotation_field)
        if stamp is None:
            for field in fields:
                field.set_enabled(False)
            self.opacity_scale.state(["disabled"])
            self.properties_hint.configure(
                text="Select a stamp on the page to edit it."
                if self.layer.stamps else
                "Add a stamp image to place it on the page.")
            self.stamp_image_label.configure(text="—")
            self.transparency_label.configure(text="")
            self.forward_button.set_enabled(False)
            self.backward_button.set_enabled(False)
            self.duplicate_button.state(["disabled"])
            self._refresh_page_state()      # greys out the per-page buttons too
            return

        for field in fields:
            field.set_enabled(True)
        self.opacity_scale.state(["!disabled"])
        self.duplicate_button.state(["!disabled"])
        index = self.layer.index_of(stamp)
        self.forward_button.set_enabled(index < len(self.layer.stamps) - 1)
        self.backward_button.set_enabled(index > 0)

        page = self.canvas.page_index
        box = stamp.box_on(self.canvas.page_size(), page)
        opacity = int(stamp.value_for("opacity", page))
        self._suspend_fields = True
        try:
            self.x_field.set(box[0])
            self.y_field.set(box[1])
            self.width_field.set(box[2])
            self.height_field.set(box[3])
            self.rotation_field.set(stamp.value_for("rotation", page))
            self.opacity_var.set(opacity)
            self.opacity_label.configure(text=f"{opacity}%")
            self.keep_ratio_var.set(bool(stamp.keep_ratio))
            self.margin_x_field.set(stamp.value_for("margin_x", page))
            self.margin_y_field.set(stamp.value_for("margin_y", page))
            self.page_mode.set(stamp.pages.mode)
            self.skip_var.set(stamp.pages.skip)
            if stamp.pages.mode == "range":
                self.range_var.set(stamp.pages.spec)
            self.range_entry.configure(
                state="normal" if stamp.pages.mode == "range" else "disabled")
        finally:
            self._suspend_fields = False

        self._refresh_page_state()
        if values_only:
            return
        scope = f"page {page + 1} only" if stamp.has_override(page) else "all pages"
        self.properties_hint.configure(
            text=f"Editing “{stamp.name_for(page)}” ({scope}) — drag it on the "
                 f"page, or use the handles to resize and rotate.")
        self.stamp_image_label.configure(text=stamp.name_for(page))
        try:
            image = self.store.load(stamp.image_for(page))
            transparent = image_service.has_transparency(image)
            self.transparency_label.configure(
                text=f"{image.width} × {image.height} px · "
                     f"{'transparent background' if transparent else 'opaque'}")
        except AppError:
            self.transparency_label.configure(text="image unavailable")
        self._paint_preset_buttons(stamp.value_for("anchor", page))

    def _refresh_page_state(self):
        """Update the "This page" section for the selected stamp."""
        stamp = self.layer.selected
        page = self.canvas.page_index
        widgets = (self.skip_page_button, self.customise_button,
                   self.page_image_button)
        if stamp is None or not self.document:
            for widget in widgets:
                widget.state(["disabled"])
            self.page_state_label.configure(
                text="Select a stamp to change how it behaves on one page.",
                style="Muted.TLabel")
            return
        for widget in widgets:
            widget.state(["!disabled"])

        count = self.document.page_count
        skipped = stamp.pages.is_skipped(page, count)
        custom = stamp.has_override(page)
        applies = page in stamp.pages.resolve_or_empty(count, page)

        self.skip_page_button.configure(
            text=f"Stamp page {page + 1} again" if skipped
            else f"Skip page {page + 1}")
        self.customise_button.configure(
            text="Use the shared settings again" if custom
            else f"Customise for page {page + 1}")
        self.page_image_button.configure(
            text=f"Different image on page {page + 1}…")

        if skipped:
            text = f"Page {page + 1} is skipped - this stamp is not applied here."
            style = "Danger.TLabel"
        elif custom:
            others = [index + 1 for index in stamp.custom_pages if index != page]
            extra = f"  Also custom: {', '.join(map(str, others))}." if others else ""
            text = (f"Page {page + 1} has its own position, size, angle, opacity "
                    f"and image. Edits here do not affect the other pages.{extra}")
            style = "Success.TLabel"
        elif not applies:
            text = f"This stamp is not applied to page {page + 1}."
            style = "Muted.TLabel"
        else:
            text = "Shared with every page this stamp applies to."
            style = "Muted.TLabel"
        self.page_state_label.configure(text=text, style=style)

    def _paint_preset_buttons(self, active=None):
        for key, button in self.preset_buttons.items():
            is_active = key == active
            button.configure(style="Primary.TButton" if is_active
                             else "Secondary.TButton",
                             image=self._preset_icons[key][1 if is_active else 0])

    def _refresh_toolbar_state(self):
        has_document = self.document is not None
        has_stamp = self.layer.selected is not None
        for key in ("add_stamp", "zoom_in", "zoom_out", "fit"):
            self.buttons[key].set_enabled(has_document)
        self.buttons["delete_stamp"].set_enabled(has_stamp)
        self.buttons["undo"].set_enabled(self.history.can_undo)
        self.buttons["redo"].set_enabled(self.history.can_redo)
        self.buttons["batch"].set_enabled(bool(self.layer.stamps))
        state = ["!disabled"] if has_document and self.layer.stamps else ["disabled"]
        self.save_button.state(state)
        self.save_as_button.state(state)
        self.edit_menu.entryconfigure(
            "Undo", state="normal" if self.history.can_undo else "disabled")
        self.edit_menu.entryconfigure(
            "Redo", state="normal" if self.history.can_redo else "disabled")

    def _refresh_pages_summary(self):
        if not self.document:
            self.pages_summary.configure(text="")
            return
        count = self.document.page_count
        try:
            selection = PageSelection(self.page_mode.get(), self.range_var.get(),
                                      self.skip_var.get())
            pages = selection.resolve(count, self.canvas.page_index)
            skipped = selection.skipped_pages(count) & \
                selection.base_pages(count, self.canvas.page_index)
            text = f"{len(pages)} of {count} page(s): " \
                   f"{format_page_spec(pages) or 'none'}"
            if skipped:
                text += f"\nSkipping {format_page_spec(skipped)}"
            self.pages_summary.configure(text=text, style="Muted.TLabel")
        except AppError as exc:
            self.pages_summary.configure(text=exc.message.splitlines()[0],
                                         style="Danger.TLabel")

    def _selection_text(self):
        stamp = self.layer.selected
        if stamp is None:
            return f"{len(self.layer.stamps)} stamp(s)" if self.layer.stamps else ""
        return f"{stamp.name} selected"

    def _refresh_status(self):
        if self.document:
            self.status.set_page(f"Page {self.canvas.page_index + 1} of "
                                 f"{self.document.page_count}")
        else:
            self.status.set_page("")
        self.status.set_selection(self._selection_text())
        if self.document:
            self._on_zoom_change(self.canvas.zoom, self.canvas.zoom_mode)
        else:
            self.status.set_zoom("")      # a zoom level means nothing with no page

    def _refresh_recent_menu(self):
        self.recent_menu.delete(0, "end")
        recent = self.config.existing_recent("recent_files")
        if not recent:
            self.recent_menu.add_command(label="(none yet)", state="disabled")
            return
        for path in recent:
            self.recent_menu.add_command(
                label=os.path.basename(path),
                command=lambda p=path: self.load_pdf(p))

    # ==================================================================
    # shutdown
    # ==================================================================
    def quit(self):
        if not self._confirm_discard():
            return
        if self._history_job:          # a queued timer must not outlive the window
            try:
                self.root.after_cancel(self._history_job)
            except Exception:          # noqa: BLE001
                pass
            self._history_job = None
        try:
            self.config.set("window_geometry", self.root.winfo_geometry())
            self.config.set("zoom_mode", self.canvas.zoom_mode)
            self.config.save()
        except Exception as exc:                       # noqa: BLE001
            log.warning("Could not persist settings: %s", exc)
        if self.document:
            self.document.close()
        self.root.destroy()


def create_root():
    """Create the Tk root, enabling file drag-and-drop when tkdnd is installed."""
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk(), True
    except Exception:                                  # noqa: BLE001
        return tk.Tk(), False


def run():
    """Entry point used by main.py."""
    root, dnd = create_root()
    window = MainWindow(root, dnd_available=dnd)
    log.info("%s %s started (dnd=%s)", APP_NAME, __version__, dnd)

    def report_exception(exc_type, value, traceback_object):
        log.error("Unhandled UI exception", exc_info=(exc_type, value,
                                                     traceback_object))
        dialogs.show_error(root, value if isinstance(value, Exception)
                           else Exception(str(value)))
    root.report_callback_exception = report_exception
    root.mainloop()
    return window
