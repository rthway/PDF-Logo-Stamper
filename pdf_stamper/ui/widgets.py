"""Reusable UI building blocks: tooltips, toolbar buttons, sections, fields.

Each widget carries its own accessibility basics - a text label or tooltip, a
visible focus ring, and a hit area big enough to click comfortably.
"""

import tkinter as tk
from tkinter import ttk

from . import theme


class Tooltip:
    """Delayed hover tooltip; also shown on keyboard focus for accessibility."""

    def __init__(self, widget, text, delay=450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<FocusIn>", self._schedule, add="+")
        widget.bind("<FocusOut>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def update_text(self, text):
        self.text = text

    def _schedule(self, _event=None):
        self._cancel()
        if self.text:
            self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self):
        if self._window or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        self._window.configure(background=theme.BORDER_STRONG)
        label = tk.Label(self._window, text=self.text, background="#2F343A",
                         foreground="#FFFFFF", font=theme.fonts()["small"],
                         padx=8, pady=4, justify="left")
        label.pack(padx=1, pady=1)
        self._window.update_idletasks()
        width = self._window.winfo_width()
        self._window.wm_geometry(f"+{max(x - width // 2, 4)}+{y}")

    def _hide(self, _event=None):
        self._cancel()
        if self._window:
            self._window.destroy()
            self._window = None


class ToolButton(ttk.Frame):
    """Flat icon (+ optional label) button with hover, disabled and focus states."""

    def __init__(self, master, icon_name, text=None, command=None, tooltip=None,
                 accent=False, compact=False):
        super().__init__(master, style="Toolbar.TFrame")
        self.command = command
        self._enabled = True
        self._accent = accent
        self._icon_name = icon_name

        self.button = tk.Frame(self, background=theme.BG_PANEL, cursor="hand2",
                               highlightthickness=1,
                               highlightbackground=theme.BG_PANEL,
                               highlightcolor=theme.ACCENT)
        self.button.pack()
        padding_x = 6 if compact else 8
        self._icon_normal = theme.icon(icon_name, color=theme.TEXT)
        self._icon_disabled = theme.icon(icon_name, color=theme.TEXT_FAINT)
        self._icon_accent = theme.icon(icon_name, color=theme.ACCENT)
        self.icon_label = tk.Label(self.button, image=self._icon_normal,
                                   background=theme.BG_PANEL)
        self.icon_label.pack(side="left", padx=(padding_x, 2 if text else padding_x),
                             pady=6)
        self.text_label = None
        if text:
            self.text_label = tk.Label(self.button, text=text,
                                       background=theme.BG_PANEL,
                                       foreground=theme.TEXT,
                                       font=theme.fonts()["body"])
            self.text_label.pack(side="left", padx=(0, padding_x + 2), pady=6)

        self.button.configure(takefocus=True)
        for widget in self._parts():
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
        self.button.bind("<FocusIn>", lambda e: self._paint(hover=True))
        self.button.bind("<FocusOut>", lambda e: self._paint())
        self.button.bind("<Return>", self._on_click)
        self.button.bind("<space>", self._on_click)
        if tooltip or text:
            Tooltip(self.button, tooltip or text)
        self._paint()

    def _parts(self):
        parts = [self.button, self.icon_label]
        if self.text_label:
            parts.append(self.text_label)
        return parts

    def _on_click(self, _event=None):
        if self._enabled and self.command:
            self.command()

    def _on_enter(self, _event=None):
        if self._enabled:
            self._paint(hover=True)

    def _on_leave(self, _event=None):
        self._paint()

    def _paint(self, hover=False):
        if not self._enabled:
            background, foreground, image = theme.BG_PANEL, theme.TEXT_FAINT, \
                self._icon_disabled
        elif hover:
            background, foreground, image = theme.ACCENT_SOFT, theme.ACCENT, \
                self._icon_accent
        elif self._accent:
            background, foreground, image = theme.BG_PANEL, theme.ACCENT, \
                self._icon_accent
        else:
            background, foreground, image = theme.BG_PANEL, theme.TEXT, \
                self._icon_normal
        self.button.configure(background=background,
                              cursor="hand2" if self._enabled else "arrow")
        self.icon_label.configure(background=background, image=image)
        if self.text_label:
            self.text_label.configure(background=background, foreground=foreground)

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.button.configure(takefocus=self._enabled)
        self._paint()


class ToolbarSeparator(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Toolbar.TFrame")
        tk.Frame(self, background=theme.BORDER, width=1, height=24) \
            .pack(padx=theme.GAP_SM, pady=theme.GAP_MD)


class Section(ttk.Frame):
    """A titled group of controls inside a sidebar."""

    def __init__(self, master, title, first=False):
        super().__init__(master, style="Panel.TFrame")
        if not first:
            ttk.Frame(self, style="Divider.TFrame", height=1) \
                .pack(fill="x", pady=(0, theme.GAP_MD))
        header = ttk.Frame(self, style="Panel.TFrame")
        header.pack(fill="x", padx=theme.GAP_LG)
        ttk.Label(header, text=title.upper(), style="Section.TLabel").pack(side="left")
        self.header = header
        self.body = ttk.Frame(self, style="Panel.TFrame")
        self.body.pack(fill="x", padx=theme.GAP_LG, pady=(theme.GAP_SM,
                                                         theme.GAP_MD))


class NumberField(ttk.Frame):
    """Labelled numeric field that reports edits as they happen.

    Invalid text is rejected visibly (red border) instead of being silently
    replaced by a default, which is what the old app did.
    """

    def __init__(self, master, label, value=0.0, minimum=None, maximum=None,
                 step=1.0, on_change=None, width=7, suffix="", integer=False,
                 tooltip=None):
        super().__init__(master, style="Panel.TFrame")
        self.on_change = on_change
        self.minimum, self.maximum = minimum, maximum
        self.integer = integer
        self._suspend = False

        ttk.Label(self, text=label, style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(self, style="Panel.TFrame")
        row.pack(fill="x", pady=(2, 0))
        self.var = tk.StringVar(value=self._format(value))
        self.spin = ttk.Spinbox(row, textvariable=self.var, width=width,
                                increment=step,
                                from_=minimum if minimum is not None else -100000,
                                to=maximum if maximum is not None else 100000,
                                command=self._commit)
        self.spin.pack(side="left")
        if suffix:
            ttk.Label(row, text=suffix, style="Faint.TLabel").pack(side="left",
                                                                  padx=(4, 0))
        self.var.trace_add("write", lambda *_: self._commit())
        self.spin.bind("<Return>", lambda e: self._commit())
        self.spin.bind("<FocusOut>", lambda e: self._commit(force=True))
        if tooltip:
            Tooltip(self.spin, tooltip)

    def _format(self, value):
        if self.integer:
            return str(int(round(float(value))))
        text = f"{float(value):.1f}"
        return text[:-2] if text.endswith(".0") else text

    def get(self):
        try:
            value = float(self.var.get())
        except (TypeError, ValueError):
            return None
        if self.minimum is not None:
            value = max(self.minimum, value)
        if self.maximum is not None:
            value = min(self.maximum, value)
        return int(round(value)) if self.integer else value

    def set(self, value):
        self._suspend = True
        try:
            self.var.set(self._format(value))
            self._mark_valid(True)
        finally:
            self._suspend = False

    def _mark_valid(self, valid):
        self.spin.configure(foreground=theme.TEXT if valid else theme.DANGER)

    def _commit(self, force=False):
        if self._suspend:
            return
        text = self.var.get().strip()
        if text in ("", "-", "+", "."):
            self._mark_valid(False)
            return
        try:
            float(text)
        except ValueError:
            self._mark_valid(False)
            return
        self._mark_valid(True)
        if self.on_change:
            self.on_change(self.get())
        if force:
            self.set(self.get())

    def set_enabled(self, enabled):
        self.spin.configure(state="normal" if enabled else "disabled")


class StatusBar(ttk.Frame):
    """Bottom status line: message, page, zoom, selection."""

    def __init__(self, master):
        super().__init__(master, style="Panel.TFrame")
        ttk.Frame(self, style="Divider.TFrame", height=1).pack(fill="x")
        row = ttk.Frame(self, style="Panel.TFrame")
        row.pack(fill="x", padx=theme.GAP_LG, pady=5)
        self.message = ttk.Label(row, text="Ready", style="Status.TLabel")
        self.message.pack(side="left")
        self.selection = ttk.Label(row, text="", style="Status.TLabel")
        self.selection.pack(side="right")
        self._sep(row)
        self.zoom = ttk.Label(row, text="", style="Status.TLabel", width=12,
                              anchor="e")
        self.zoom.pack(side="right")
        self._sep(row)
        self.page = ttk.Label(row, text="", style="Status.TLabel", anchor="e")
        self.page.pack(side="right")

    def _sep(self, row):
        ttk.Label(row, text="|", style="Status.TLabel",
                  foreground=theme.BORDER_STRONG).pack(side="right",
                                                       padx=theme.GAP_MD)

    def set_message(self, text, kind="info"):
        colors = {"info": theme.TEXT_MUTED, "error": theme.DANGER,
                  "success": theme.SUCCESS, "warning": theme.WARNING}
        self.message.configure(text=text, foreground=colors.get(kind,
                                                               theme.TEXT_MUTED))

    def set_page(self, text):
        self.page.configure(text=text)

    def set_zoom(self, text):
        self.zoom.configure(text=text)

    def set_selection(self, text):
        self.selection.configure(text=text)


class ScrollableColumn(ttk.Frame):
    """A fixed-width panel whose content scrolls when it is taller than the window.

    Side panels grow as features are added; on a shorter screen the bottom
    controls would simply be unreachable. The scrollbar only appears when it is
    actually needed, so nothing changes visually on a tall window.
    """

    def __init__(self, master, width):
        super().__init__(master, style="Panel.TFrame", width=width)
        self.pack_propagate(False)
        self._width = width
        self.canvas = tk.Canvas(self, background=theme.BG_PANEL,
                                highlightthickness=0, borderwidth=0,
                                yscrollincrement=1, takefocus=False)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical",
                                       command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_yview)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.body = ttk.Frame(self.canvas, style="Panel.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.body,
                                                 anchor="nw")
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        for widget in (self.canvas, self.body):
            widget.bind("<MouseWheel>", self._on_wheel)
        self._scrollbar_shown = False

    # -- geometry --------------------------------------------------------
    def _on_body_configure(self, _event=None):
        height = self.body.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, 1, height))
        self._sync_scrollbar(height)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)
        self._sync_scrollbar(self.body.winfo_reqheight())

    def _sync_scrollbar(self, content_height):
        needed = content_height > self.canvas.winfo_height() + 1
        if needed and not self._scrollbar_shown:
            self.scrollbar.pack(side="right", fill="y")
            self._scrollbar_shown = True
        elif not needed and self._scrollbar_shown:
            self.scrollbar.pack_forget()
            self._scrollbar_shown = False
            self.canvas.yview_moveto(0.0)

    def _on_yview(self, first, last):
        self.scrollbar.set(first, last)

    def _on_wheel(self, event):
        if self._scrollbar_shown:
            self.canvas.yview_scroll(-int(event.delta / 4), "units")
            return "break"
        return None

    def scroll_into_view(self, widget):
        """Scroll so `widget` is visible (used when focus moves off-screen)."""
        if not self._scrollbar_shown:
            return
        try:
            top = widget.winfo_rooty() - self.body.winfo_rooty()
            height = max(self.body.winfo_reqheight(), 1)
            view_height = max(self.canvas.winfo_height(), 1)
            current = self.canvas.canvasy(0)
            if top < current:
                self.canvas.yview_moveto(max(top - 8, 0) / height)
            elif top + widget.winfo_height() > current + view_height:
                target = top + widget.winfo_height() - view_height + 8
                self.canvas.yview_moveto(min(max(target, 0), height) / height)
        except tk.TclError:
            pass


class DropTarget(ttk.Frame):
    """Full-window drag-and-drop hint overlay (shown while dragging files)."""

    def __init__(self, master, text="Drop a PDF or logo image here"):
        super().__init__(master, style="Panel.TFrame")
        inner = tk.Frame(self, background=theme.ACCENT_SOFT,
                         highlightthickness=2, highlightbackground=theme.ACCENT)
        inner.pack(fill="both", expand=True, padx=theme.GAP_LG, pady=theme.GAP_LG)
        tk.Label(inner, text=text, background=theme.ACCENT_SOFT,
                 foreground=theme.ACCENT, font=theme.fonts()["subtitle"]) \
            .place(relx=0.5, rely=0.5, anchor="center")
