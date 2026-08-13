"""Dialogs: friendly errors, progress, confirmation, batch, stamp removal, about.

Users see plain language; the technical detail is one click away and always in the
log file. No dialog ever shows a traceback by default.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

from .. import APP_NAME, __version__
from ..errors import AppError
from ..logging_setup import get_logger, log_file
from . import theme
from .widgets import Section, Tooltip

log = get_logger(__name__)


class ModalDialog:
    """Base modal: centred on the parent, Esc closes, focus trapped."""

    def __init__(self, parent, title, width=None, height=None):
        self.parent = parent
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.transient(parent)
        self.top.configure(background=theme.BG_PANEL)
        self.top.resizable(False, False)
        theme.set_window_icon(self.top)
        self.body = ttk.Frame(self.top, style="Panel.TFrame", padding=theme.GAP_XL)
        self.body.pack(fill="both", expand=True)
        self.top.bind("<Escape>", lambda e: self.close())
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self._size = (width, height)

    def show(self):
        self.top.update_idletasks()
        width = self._size[0] or self.top.winfo_reqwidth()
        height = self._size[1] or self.top.winfo_reqheight()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - width) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - height) // 3
        self.top.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        self.top.grab_set()
        self.top.focus_set()
        self.parent.wait_window(self.top)
        return self.result

    def close(self):
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        self.top.destroy()

    def button_row(self):
        row = ttk.Frame(self.body, style="Panel.TFrame")
        row.pack(fill="x", pady=(theme.GAP_LG, 0))
        return row


class MessageDialog(ModalDialog):
    """Information / warning / error with optional technical detail."""

    ICONS = {"error": ("!", theme.DANGER, theme.DANGER_SOFT),
             "warning": ("!", theme.WARNING, "#FEF6E7"),
             "info": ("i", theme.ACCENT, theme.ACCENT_SOFT),
             "success": ("✓", theme.SUCCESS, "#EEF7F0")}

    def __init__(self, parent, title, message, detail="", kind="error",
                 buttons=("OK",), default="OK"):
        super().__init__(parent, title)
        self.buttons = buttons
        self.detail = detail or ""
        self._detail_shown = False

        head = ttk.Frame(self.body, style="Panel.TFrame")
        head.pack(fill="x")
        glyph, colour, background = self.ICONS.get(kind, self.ICONS["info"])
        badge = tk.Label(head, text=glyph, background=background, foreground=colour,
                         font=theme.fonts()["title"], width=3, height=1)
        badge.pack(side="left", padx=(0, theme.GAP_MD), anchor="n")
        text_column = ttk.Frame(head, style="Panel.TFrame")
        text_column.pack(side="left", fill="both", expand=True)
        first, _, rest = message.partition("\n\n")
        ttk.Label(text_column, text=first, style="Panel.TLabel",
                  font=theme.fonts()["subtitle"], wraplength=380,
                  justify="left").pack(anchor="w")
        if rest:
            ttk.Label(text_column, text=rest.strip(), style="Muted.TLabel",
                      wraplength=380, justify="left").pack(anchor="w",
                                                           pady=(theme.GAP_SM, 0))

        self.detail_frame = None
        if self.detail:
            links = ttk.Frame(self.body, style="Panel.TFrame")
            links.pack(fill="x", pady=(theme.GAP_MD, 0))
            self.detail_button = ttk.Button(links, text="Show technical details",
                                           style="Link.TButton",
                                           command=self._toggle_detail)
            self.detail_button.pack(side="left")
            ttk.Button(links, text="Open log folder", style="Link.TButton",
                       command=self._open_log).pack(side="left", padx=(theme.GAP_MD, 0))

        row = self.button_row()
        for index, label in enumerate(reversed(buttons)):
            style = "Primary.TButton" if label == default else "Secondary.TButton"
            button = ttk.Button(row, text=label, style=style,
                                command=lambda value=label: self._choose(value))
            button.pack(side="right", padx=(theme.GAP_SM, 0))
            if label == default:
                button.focus_set()
                self.top.bind("<Return>", lambda e, value=label: self._choose(value))
            del index

    def _choose(self, value):
        self.result = value
        self.close()

    def _toggle_detail(self):
        if self._detail_shown:
            self.detail_frame.destroy()
            self.detail_frame = None
            self._detail_shown = False
            self.detail_button.configure(text="Show technical details")
            return
        self.detail_frame = ttk.Frame(self.body, style="Panel.TFrame")
        self.detail_frame.pack(fill="both", expand=True, pady=(theme.GAP_SM, 0))
        text = tk.Text(self.detail_frame, height=6, width=54, wrap="word",
                       font=theme.fonts()["mono"], background=theme.BG_SUBTLE,
                       foreground=theme.TEXT_MUTED, relief="flat",
                       highlightthickness=1, highlightbackground=theme.BORDER)
        text.insert("1.0", f"{self.detail}\n\nLog file: {log_file()}")
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        self._detail_shown = True
        self.detail_button.configure(text="Hide technical details")
        self.top.geometry("")

    def _open_log(self):
        folder = os.path.dirname(log_file())
        try:
            os.startfile(folder)                      # noqa: S606 - Explorer only
        except OSError as exc:
            log.warning("Could not open log folder: %s", exc)


def show_error(parent, exc, title="Something went wrong"):
    """Show an AppError (or any exception) in plain language."""
    if isinstance(exc, AppError):
        message, detail = exc.message, exc.detail
    else:
        message = ("An unexpected problem occurred.\n\n"
                   "The action was not completed. Technical details have been "
                   "written to the log file.")
        detail = f"{type(exc).__name__}: {exc}"
    log.warning("Dialog error: %s | %s", message.splitlines()[0], detail)
    MessageDialog(parent, title, message, detail, kind="error").show()


def show_info(parent, title, message, detail="", kind="info"):
    MessageDialog(parent, title, message, detail, kind=kind).show()


def ask_yes_no(parent, title, message, confirm="Yes", cancel="Cancel",
               kind="warning"):
    answer = MessageDialog(parent, title, message, kind=kind,
                           buttons=(cancel, confirm), default=confirm).show()
    return answer == confirm


class ProgressDialog(ModalDialog):
    """Runs a blocking job on a worker thread with progress and cancellation."""

    def __init__(self, parent, title, description, work, cancellable=True):
        super().__init__(parent, title, width=420)
        self.work = work
        self._queue = queue.Queue()
        self._cancel = threading.Event()
        self.error = None

        ttk.Label(self.body, text=description, style="Panel.TLabel",
                  font=theme.fonts()["subtitle"]).pack(anchor="w")
        self.detail_label = ttk.Label(self.body, text="Starting…",
                                      style="Muted.TLabel")
        self.detail_label.pack(anchor="w", pady=(theme.GAP_SM, theme.GAP_MD))
        self.bar = ttk.Progressbar(self.body, mode="determinate", maximum=100)
        self.bar.pack(fill="x")
        row = self.button_row()
        self.cancel_button = ttk.Button(row, text="Cancel", style="Secondary.TButton",
                                       command=self._request_cancel)
        self.cancel_button.pack(side="right")
        if not cancellable:
            self.cancel_button.state(["disabled"])
        self.top.protocol("WM_DELETE_WINDOW", self._request_cancel)
        self.top.bind("<Escape>", lambda e: self._request_cancel())

    def _request_cancel(self):
        self._cancel.set()
        self.detail_label.configure(text="Cancelling…")
        self.cancel_button.state(["disabled"])

    def run(self):
        """Show the dialog, run the job, return its result (None if cancelled)."""
        thread = threading.Thread(target=self._worker, daemon=True)
        thread.start()
        self.top.after(60, self._poll)
        super().show()
        if self.error:
            raise self.error
        return self.result

    def _worker(self):
        def progress(done, total, label=""):
            self._queue.put(("progress", done, total, label))
        try:
            value = self.work(progress, self._cancel.is_set)
            self._queue.put(("done", value))
        except AppError as exc:
            self._queue.put(("error", exc))
        except Exception as exc:                       # noqa: BLE001
            log.exception("Background job failed")
            self._queue.put(("error", exc))

    def _poll(self):
        try:
            while True:
                message = self._queue.get_nowait()
                if message[0] == "progress":
                    _, done, total, label = message
                    percent = (done / total * 100) if total else 0
                    self.bar.configure(value=percent)
                    self.detail_label.configure(
                        text=f"{label or 'Working'} — {done} of {total}")
                elif message[0] == "done":
                    self.result = message[1]
                    self.close()
                    return
                else:
                    self.error = message[1]
                    self.close()
                    return
        except queue.Empty:
            pass
        if self.top.winfo_exists():
            self.top.after(60, self._poll)


class RemoveStampsDialog(ModalDialog):
    """Ask which pages to strip previously-applied stamps from."""

    def __init__(self, parent, page_count, current_page=0):
        super().__init__(parent, "Remove stamps from a saved PDF", width=430)
        ttk.Label(self.body, text="Remove stamps this app applied earlier",
                  font=theme.fonts()["subtitle"], style="Panel.TLabel") \
            .pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", wraplength=370, justify="left",
                  text="Page text and graphics are never touched — only stamp "
                       "images are removed.").pack(anchor="w",
                                                   pady=(theme.GAP_SM, theme.GAP_LG))

        ttk.Label(self.body, text=f"Pages (1-{page_count}, blank means all)",
                  style="Muted.TLabel").pack(anchor="w")
        self.spec = tk.StringVar(value=str(current_page + 1))
        entry = ttk.Entry(self.body, textvariable=self.spec, width=36)
        entry.pack(fill="x", pady=(2, theme.GAP_MD))
        entry.focus_set()
        entry.select_range(0, "end")

        self.untagged = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.body, variable=self.untagged,
                        text="Also remove stamps added by other tools") \
            .pack(anchor="w")
        ttk.Label(self.body, style="Faint.TLabel", wraplength=370, justify="left",
                  text="Use this for files stamped by an older version or a "
                       "different program.").pack(anchor="w", pady=(2, 0))

        row = self.button_row()
        ttk.Button(row, text="Remove stamps", style="Primary.TButton",
                   command=self._confirm).pack(side="right")
        ttk.Button(row, text="Cancel", style="Secondary.TButton",
                   command=self.close).pack(side="right", padx=(0, theme.GAP_SM))
        self.top.bind("<Return>", lambda e: self._confirm())

    def _confirm(self):
        self.result = (self.spec.get(), not self.untagged.get())
        self.close()


class BatchDialog(ModalDialog):
    """Folder-in / folder-out batch stamping using the current stamp setup."""

    def __init__(self, parent, stamp_summary, config, pick_folder):
        super().__init__(parent, "Batch stamp a folder", width=520)
        self.pick_folder = pick_folder
        self.input_var = tk.StringVar(value=config.get("last_batch_input", ""))
        self.output_var = tk.StringVar(value=config.get("last_batch_output", ""))
        self.suffix_var = tk.StringVar(value=config.get("output_suffix", "_stamped"))
        self.recursive_var = tk.BooleanVar(value=False)

        ttk.Label(self.body, text="Apply the current stamps to every PDF in a folder",
                  font=theme.fonts()["subtitle"], style="Panel.TLabel") \
            .pack(anchor="w")
        ttk.Label(self.body, text=stamp_summary, style="Muted.TLabel",
                  wraplength=460, justify="left").pack(anchor="w",
                                                       pady=(theme.GAP_SM,
                                                             theme.GAP_LG))

        self._folder_row("Input folder", self.input_var)
        self._folder_row("Output folder", self.output_var)

        options = ttk.Frame(self.body, style="Panel.TFrame")
        options.pack(fill="x", pady=(theme.GAP_MD, 0))
        ttk.Label(options, text="Add to file name", style="Muted.TLabel") \
            .pack(side="left")
        ttk.Entry(options, textvariable=self.suffix_var, width=14) \
            .pack(side="left", padx=theme.GAP_SM)
        ttk.Checkbutton(options, text="Include sub-folders",
                        variable=self.recursive_var).pack(side="left",
                                                          padx=theme.GAP_LG)

        ttk.Label(self.body, style="Faint.TLabel", wraplength=460, justify="left",
                  text="Original files are never modified. Existing output files "
                       "are kept — a numbered name is used instead.") \
            .pack(anchor="w", pady=(theme.GAP_MD, 0))

        row = self.button_row()
        ttk.Button(row, text="Start", style="Primary.TButton",
                   command=self._confirm).pack(side="right")
        ttk.Button(row, text="Cancel", style="Secondary.TButton",
                   command=self.close).pack(side="right", padx=(0, theme.GAP_SM))

    def _folder_row(self, label, variable):
        ttk.Label(self.body, text=label, style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(self.body, style="Panel.TFrame")
        row.pack(fill="x", pady=(2, theme.GAP_SM))
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x",
                                                   expand=True)
        button = ttk.Button(row, text="Browse…", style="Secondary.TButton",
                            command=lambda: self._browse(variable, label))
        button.pack(side="left", padx=(theme.GAP_SM, 0))
        Tooltip(button, f"Choose the {label.lower()}")

    def _browse(self, variable, label):
        folder = self.pick_folder(label, variable.get())
        if folder:
            variable.set(folder)

    def _confirm(self):
        if not self.input_var.get().strip() or not self.output_var.get().strip():
            MessageDialog(self.top, "Folders required",
                          "Choose both an input folder and an output folder.",
                          kind="warning").show()
            return
        self.result = {"input": self.input_var.get().strip(),
                       "output": self.output_var.get().strip(),
                       "suffix": self.suffix_var.get().strip() or "_stamped",
                       "recursive": bool(self.recursive_var.get())}
        self.close()


class BatchResultsDialog(ModalDialog):
    """Per-file outcome of a batch run."""

    def __init__(self, parent, results):
        super().__init__(parent, "Batch results", width=560, height=420)
        ok = [result for result in results if result.ok]
        failed = [result for result in results if not result.ok]
        ttk.Label(self.body, style="Panel.TLabel", font=theme.fonts()["subtitle"],
                  text=f"{len(ok)} file(s) stamped, {len(failed)} failed") \
            .pack(anchor="w", pady=(0, theme.GAP_MD))

        table = ttk.Treeview(self.body, columns=("file", "status"), show="headings",
                             height=12)
        table.heading("file", text="File")
        table.heading("status", text="Result")
        table.column("file", width=300, anchor="w")
        table.column("status", width=200, anchor="w")
        for result in results:
            table.insert("", "end", values=(os.path.basename(result.source_path),
                                            ("OK — " if result.ok else "Failed — ")
                                            + result.message))
        table.pack(fill="both", expand=True)

        row = self.button_row()
        ttk.Button(row, text="Close", style="Primary.TButton",
                   command=self.close).pack(side="right")
        if ok:
            ttk.Button(row, text="Open output folder", style="Secondary.TButton",
                       command=lambda: self._open(os.path.dirname(
                           ok[0].output_path))).pack(side="right",
                                                     padx=(0, theme.GAP_SM))

    def _open(self, folder):
        try:
            os.startfile(folder)                      # noqa: S606
        except OSError as exc:
            log.warning("Could not open folder %s: %s", folder, exc)


class AboutDialog(ModalDialog):
    def __init__(self, parent):
        super().__init__(parent, f"About {APP_NAME}", width=420)
        ttk.Label(self.body, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.body, text=f"Version {__version__}", style="Muted.TLabel") \
            .pack(anchor="w", pady=(2, theme.GAP_MD))
        ttk.Label(self.body, style="Panel.TLabel", justify="left", wraplength=360,
                  text="Place a logo or stamp on PDF pages exactly where you want "
                       "it: drag it on the page, resize with the handles, rotate, "
                       "set opacity, and apply it to any pages you choose.") \
            .pack(anchor="w")
        info = Section(self.body, "Details", first=True)
        info.pack(fill="x", pady=(theme.GAP_LG, 0))
        for label, value in (("Author", "Roshan Kumar Thapa"),
                             ("Engine", "PyMuPDF + Pillow"),
                             ("Log file", log_file())):
            row = ttk.Frame(info.body, style="Panel.TFrame")
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label, style="Muted.TLabel", width=10) \
                .pack(side="left")
            ttk.Label(row, text=value, style="Panel.TLabel", wraplength=250,
                      justify="left").pack(side="left")
        row = self.button_row()
        ttk.Button(row, text="Close", style="Primary.TButton",
                   command=self.close).pack(side="right")


class ShortcutsDialog(ModalDialog):
    SHORTCUTS = (
        ("Ctrl + O", "Open PDF"),
        ("Ctrl + L", "Add stamp image"),
        ("Ctrl + S", "Save (export stamped PDF)"),
        ("Ctrl + Shift + S", "Save as…"),
        ("Ctrl + Z / Ctrl + Y", "Undo / Redo"),
        ("Delete", "Delete selected stamp"),
        ("Ctrl + D", "Duplicate selected stamp"),
        ("Arrow keys", "Nudge stamp by 1 pt (Shift: 10 pt)"),
        ("Ctrl + + / Ctrl + -", "Zoom in / out"),
        ("Ctrl + 0", "Fit page"),
        ("Ctrl + 1", "Fit width"),
        ("Page Down / Page Up", "Next / previous page"),
        ("Home / End", "First / last page"),
        ("Mouse wheel", "Scroll through every page"),
        ("Ctrl + wheel", "Zoom at the pointer"),
        ("Middle-drag", "Pan the page"),
        ("Shift while dragging", "Constrain to one axis"),
        ("Shift while resizing", "Keep aspect ratio"),
        ("Shift while rotating", "Snap to 15°"),
    )

    def __init__(self, parent):
        super().__init__(parent, "Keyboard shortcuts", width=420)
        ttk.Label(self.body, text="Keyboard shortcuts", style="Title.TLabel") \
            .pack(anchor="w", pady=(0, theme.GAP_MD))
        for keys, description in self.SHORTCUTS:
            row = ttk.Frame(self.body, style="Panel.TFrame")
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=keys, style="Muted.TLabel", width=20) \
                .pack(side="left")
            ttk.Label(row, text=description, style="Panel.TLabel").pack(side="left")
        row = self.button_row()
        ttk.Button(row, text="Close", style="Primary.TButton",
                   command=self.close).pack(side="right")
