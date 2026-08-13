"""Visual language: palette, type scale, ttk styles and vector icons.

One place defines every colour, font and spacing step, so the app stays visually
consistent. Icons are drawn with Pillow at 4x and downsampled, which keeps the
build free of binary image assets while still looking crisp.
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

# -- palette ---------------------------------------------------------------
BG_APP = "#F4F5F7"          # window background
BG_PANEL = "#FFFFFF"        # sidebars, toolbar, cards
BG_SUBTLE = "#F8F9FB"       # nested groups, hovered rows
BG_WORKSPACE = "#6F7378"    # area around the page
BORDER = "#E2E5EA"
BORDER_STRONG = "#CBD0D7"
TEXT = "#1F2328"
TEXT_MUTED = "#6B7280"
TEXT_FAINT = "#9AA1AC"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#EFF4FE"
DANGER = "#DC2626"
DANGER_SOFT = "#FEF2F2"
SUCCESS = "#15803D"
WARNING = "#B45309"
PAGE_SHADOW = "#4B4F54"
SELECTION = ACCENT
GUIDE = "#F59E0B"

# -- spacing scale (px) ----------------------------------------------------
GAP_XS, GAP_SM, GAP_MD, GAP_LG, GAP_XL = 4, 8, 12, 16, 24
SIDEBAR_WIDTH = 268
PROPERTIES_WIDTH = 264
TOOLBAR_HEIGHT = 52
ICON_SIZE = 20
HANDLE_SIZE = 9

_font_cache = {}
_icon_cache = {}
_cache_owner = None      # the Tk root the cached fonts/images belong to


def _bind_caches_to(root):
    """Tk fonts and images belong to one interpreter.

    If a new root is created (a reopened window, or a test suite building several),
    the cached objects from the previous root are dead and must be rebuilt.
    """
    global _cache_owner
    if _cache_owner is not root:
        _font_cache.clear()
        _icon_cache.clear()
        _cache_owner = root


def fonts():
    """Named fonts, created once per interpreter."""
    if _font_cache:
        return _font_cache
    family = "Segoe UI"
    available = set(tkfont.families())
    if family not in available:
        family = "Helvetica" if "Helvetica" in available else "TkDefaultFont"
    _font_cache.update({
        "body": tkfont.Font(family=family, size=9),
        "body_bold": tkfont.Font(family=family, size=9, weight="bold"),
        "small": tkfont.Font(family=family, size=8),
        "section": tkfont.Font(family=family, size=8, weight="bold"),
        "title": tkfont.Font(family=family, size=12, weight="bold"),
        "subtitle": tkfont.Font(family=family, size=10),
        "mono": tkfont.Font(family="Consolas" if "Consolas" in available else family,
                            size=9),
    })
    return _font_cache


def apply_theme(root):
    """Install the ttk styles. Returns the style object."""
    _bind_caches_to(root.nametowidget(".") if hasattr(root, "nametowidget") else root)
    text_fonts = fonts()
    root.configure(background=BG_APP)
    style = ttk.Style(root)
    style.theme_use("clam")          # the only built-in theme that recolours fully

    style.configure(".", background=BG_PANEL, foreground=TEXT,
                    font=text_fonts["body"], borderwidth=0, focuscolor=ACCENT)

    style.configure("App.TFrame", background=BG_APP)
    style.configure("Panel.TFrame", background=BG_PANEL)
    style.configure("Subtle.TFrame", background=BG_SUBTLE)
    style.configure("Toolbar.TFrame", background=BG_PANEL)
    style.configure("Divider.TFrame", background=BORDER)

    style.configure("TLabel", background=BG_PANEL, foreground=TEXT)
    style.configure("Panel.TLabel", background=BG_PANEL, foreground=TEXT)
    style.configure("Subtle.TLabel", background=BG_SUBTLE, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG_PANEL, foreground=TEXT_MUTED)
    style.configure("MutedSubtle.TLabel", background=BG_SUBTLE,
                    foreground=TEXT_MUTED)
    style.configure("Faint.TLabel", background=BG_PANEL, foreground=TEXT_FAINT,
                    font=text_fonts["small"])
    style.configure("Section.TLabel", background=BG_PANEL, foreground=TEXT_MUTED,
                    font=text_fonts["section"])
    style.configure("Title.TLabel", background=BG_PANEL, foreground=TEXT,
                    font=text_fonts["title"])
    style.configure("Status.TLabel", background=BG_PANEL, foreground=TEXT_MUTED,
                    font=text_fonts["small"])
    style.configure("Danger.TLabel", background=BG_PANEL, foreground=DANGER)
    style.configure("Success.TLabel", background=BG_PANEL, foreground=SUCCESS)

    # Buttons: flat, generous hit area, accent hover.
    style.configure("TButton", background=BG_PANEL, foreground=TEXT,
                    padding=(10, 6), relief="flat", anchor="center")
    style.map("TButton",
              background=[("disabled", BG_PANEL), ("pressed", ACCENT_SOFT),
                          ("active", BG_SUBTLE)],
              foreground=[("disabled", TEXT_FAINT)])

    style.configure("Primary.TButton", background=ACCENT, foreground="#FFFFFF",
                    padding=(14, 8), font=text_fonts["body_bold"])
    style.map("Primary.TButton",
              background=[("disabled", "#A9C0F5"), ("pressed", ACCENT_HOVER),
                          ("active", ACCENT_HOVER)],
              foreground=[("disabled", "#F2F5FC")])

    style.configure("Secondary.TButton", background=BG_SUBTLE, foreground=TEXT,
                    padding=(12, 7))
    style.map("Secondary.TButton",
              background=[("disabled", BG_SUBTLE), ("pressed", BORDER),
                          ("active", "#EDEFF3")],
              foreground=[("disabled", TEXT_FAINT)])

    style.configure("Danger.TButton", background=DANGER_SOFT, foreground=DANGER,
                    padding=(12, 7))
    style.map("Danger.TButton",
              background=[("disabled", BG_SUBTLE), ("active", "#FDE7E7")],
              foreground=[("disabled", TEXT_FAINT)])

    style.configure("Link.TButton", background=BG_PANEL, foreground=ACCENT,
                    padding=(2, 2), font=text_fonts["small"])
    style.map("Link.TButton", background=[("active", BG_PANEL)],
              foreground=[("active", ACCENT_HOVER), ("disabled", TEXT_FAINT)])

    # Inputs
    style.configure("TEntry", fieldbackground="#FFFFFF", background="#FFFFFF",
                    foreground=TEXT, bordercolor=BORDER_STRONG, lightcolor=BORDER,
                    darkcolor=BORDER, borderwidth=1, relief="solid",
                    padding=(6, 4), insertcolor=TEXT)
    style.map("TEntry", bordercolor=[("focus", ACCENT), ("disabled", BORDER)],
              foreground=[("disabled", TEXT_FAINT)])
    style.configure("TSpinbox", fieldbackground="#FFFFFF", background=BG_SUBTLE,
                    foreground=TEXT, bordercolor=BORDER_STRONG, borderwidth=1,
                    relief="solid", padding=(5, 3), arrowsize=11,
                    arrowcolor=TEXT_MUTED, insertcolor=TEXT)
    style.map("TSpinbox", bordercolor=[("focus", ACCENT)],
              foreground=[("disabled", TEXT_FAINT)],
              arrowcolor=[("disabled", TEXT_FAINT)])
    style.configure("TCombobox", fieldbackground="#FFFFFF", background=BG_SUBTLE,
                    foreground=TEXT, bordercolor=BORDER_STRONG, borderwidth=1,
                    relief="solid", padding=(5, 3), arrowcolor=TEXT_MUTED)
    style.map("TCombobox", bordercolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", "#FFFFFF")])

    style.configure("TCheckbutton", background=BG_PANEL, foreground=TEXT,
                    indicatorcolor="#FFFFFF", indicatorbackground="#FFFFFF",
                    padding=(0, 3), focuscolor=BG_PANEL)
    style.map("TCheckbutton", background=[("active", BG_PANEL)],
              indicatorcolor=[("selected", ACCENT), ("pressed", ACCENT_SOFT)])
    style.configure("Subtle.TCheckbutton", background=BG_SUBTLE, foreground=TEXT,
                    focuscolor=BG_SUBTLE)
    style.map("Subtle.TCheckbutton", background=[("active", BG_SUBTLE)],
              indicatorcolor=[("selected", ACCENT)])

    style.configure("TRadiobutton", background=BG_PANEL, foreground=TEXT,
                    padding=(0, 3), focuscolor=BG_PANEL)
    style.map("TRadiobutton", background=[("active", BG_PANEL)],
              indicatorcolor=[("selected", ACCENT)])

    style.configure("TScale", background=BG_PANEL, troughcolor=BORDER,
                    bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)

    style.configure("TProgressbar", background=ACCENT, troughcolor=BORDER,
                    bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT,
                    thickness=6)

    style.configure("Vertical.TScrollbar", background=BG_SUBTLE,
                    troughcolor=BG_APP, bordercolor=BG_APP,
                    arrowcolor=TEXT_MUTED, darkcolor=BORDER_STRONG,
                    lightcolor=BORDER_STRONG)
    style.configure("Horizontal.TScrollbar", background=BG_SUBTLE,
                    troughcolor=BG_APP, bordercolor=BG_APP,
                    arrowcolor=TEXT_MUTED, darkcolor=BORDER_STRONG,
                    lightcolor=BORDER_STRONG)

    style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF",
                    foreground=TEXT, borderwidth=0, rowheight=24)
    style.map("Treeview", background=[("selected", ACCENT_SOFT)],
              foreground=[("selected", TEXT)])
    style.configure("Treeview.Heading", background=BG_SUBTLE, foreground=TEXT_MUTED,
                    font=text_fonts["section"], relief="flat", padding=(6, 4))

    style.configure("TNotebook", background=BG_PANEL, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG_SUBTLE, foreground=TEXT_MUTED,
                    padding=(14, 7))
    style.map("TNotebook.Tab", background=[("selected", BG_PANEL)],
              foreground=[("selected", TEXT)])

    style.configure("TSeparator", background=BORDER)
    return style


# -- icons -----------------------------------------------------------------

def icon(name, size=ICON_SIZE, color=TEXT):
    """A cached PhotoImage of a simple monochrome glyph."""
    key = (name, size, color)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    scale = 4
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    _draw_glyph(draw, name, size * scale, color, scale)
    photo = ImageTk.PhotoImage(canvas.resize((size, size), Image.LANCZOS))
    _icon_cache[key] = photo
    return photo


def _draw_glyph(draw, name, box, color, scale):
    """Draw `name` inside a square of `box` pixels."""
    stroke = max(int(1.6 * scale), 2)
    pad = box * 0.14
    left, top, right, bottom = pad, pad, box - pad, box - pad
    mid_x, mid_y = box / 2, box / 2

    def line(points, width=stroke):
        draw.line(points, fill=color, width=width, joint="curve")

    def rect(x0, y0, x1, y1, radius=None, width=stroke):
        if radius:
            draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=color,
                                   width=width)
        else:
            draw.rectangle([x0, y0, x1, y1], outline=color, width=width)

    if name == "open":
        rect(left, top + box * 0.12, right, bottom, radius=box * 0.08)
        line([left, top + box * 0.26, mid_x - box * 0.02, top + box * 0.26,
              mid_x + box * 0.06, top + box * 0.12])
    elif name == "add-stamp":
        rect(left, top, right - box * 0.16, bottom - box * 0.16, radius=box * 0.08)
        draw.ellipse([left + box * 0.12, top + box * 0.12, left + box * 0.28,
                      top + box * 0.28], outline=color, width=stroke)
        line([left + box * 0.06, bottom - box * 0.3, mid_x, mid_y - box * 0.04,
              right - box * 0.22, bottom - box * 0.16])
        line([right - box * 0.24, bottom - box * 0.02, right, bottom - box * 0.02])
        line([right - box * 0.12, bottom - box * 0.14, right - box * 0.12, bottom + box * 0.1])
    elif name == "trash":
        line([left + box * 0.06, top + box * 0.16, right - box * 0.06, top + box * 0.16])
        rect(left + box * 0.16, top + box * 0.16, right - box * 0.16, bottom,
             radius=box * 0.06)
        line([mid_x - box * 0.12, top + box * 0.06, mid_x + box * 0.12, top + box * 0.06])
        line([mid_x - box * 0.06, top + box * 0.3, mid_x - box * 0.06, bottom - box * 0.12])
        line([mid_x + box * 0.06, top + box * 0.3, mid_x + box * 0.06, bottom - box * 0.12])
    elif name in ("undo", "redo"):
        # Three-quarter arc with a solid arrowhead on the leading end.
        draw.arc([left, top + box * 0.1, right, bottom + box * 0.02],
                 start=170 if name == "undo" else 10,
                 end=350 if name == "undo" else 190, fill=color, width=stroke)
        head = box * 0.17
        if name == "undo":
            tip = (left, mid_y + box * 0.02)
            draw.polygon([(tip[0], tip[1] - head), (tip[0] + head * 1.1, tip[1]),
                          (tip[0] - head * 0.2, tip[1] + head * 0.5)], fill=color)
        else:
            tip = (right, mid_y + box * 0.02)
            draw.polygon([(tip[0], tip[1] - head), (tip[0] - head * 1.1, tip[1]),
                          (tip[0] + head * 0.2, tip[1] + head * 0.5)], fill=color)
    elif name in ("zoom-in", "zoom-out"):
        radius = box * 0.30
        draw.ellipse([left, top, left + radius * 2, top + radius * 2],
                     outline=color, width=stroke)
        centre = (left + radius, top + radius)
        line([centre[0] + radius * 0.72, centre[1] + radius * 0.72,
              right - box * 0.02, bottom - box * 0.02], width=stroke + scale // 2)
        line([centre[0] - radius * 0.44, centre[1], centre[0] + radius * 0.44, centre[1]])
        if name == "zoom-in":
            line([centre[0], centre[1] - radius * 0.44, centre[0],
                  centre[1] + radius * 0.44])
    elif name == "fit-page":
        rect(left, top, right, bottom, radius=box * 0.06)
        inset = box * 0.16
        line([left + inset, top + inset * 1.6, left + inset, top + inset,
              left + inset * 1.6, top + inset])
        line([right - inset * 1.6, bottom - inset, right - inset, bottom - inset,
              right - inset, bottom - inset * 1.6])
    elif name == "save":
        rect(left, top, right, bottom, radius=box * 0.08)
        line([mid_x, top + box * 0.14, mid_x, mid_y + box * 0.16])
        line([mid_x - box * 0.14, mid_y, mid_x, mid_y + box * 0.18,
              mid_x + box * 0.14, mid_y])
        line([left + box * 0.12, bottom - box * 0.12, right - box * 0.12,
              bottom - box * 0.12])
    elif name == "export":
        line([left + box * 0.04, bottom - box * 0.08, right - box * 0.04,
              bottom - box * 0.08])
        line([left + box * 0.04, bottom - box * 0.28, left + box * 0.04,
              bottom - box * 0.08])
        line([right - box * 0.04, bottom - box * 0.28, right - box * 0.04,
              bottom - box * 0.08])
        line([mid_x, top, mid_x, mid_y + box * 0.2])
        line([mid_x - box * 0.16, top + box * 0.18, mid_x, top,
              mid_x + box * 0.16, top + box * 0.18])
    elif name == "batch":
        rect(left, top + box * 0.16, right - box * 0.16, bottom, radius=box * 0.06)
        line([left + box * 0.14, top + box * 0.04, right - box * 0.02, top + box * 0.04])
        line([right - box * 0.02, top + box * 0.04, right - box * 0.02,
              bottom - box * 0.16])
    elif name in ("prev", "next"):
        # A chevron pointing the way it navigates: '<' for prev, '>' for next.
        direction = 1 if name == "prev" else -1
        line([mid_x + direction * box * 0.09, top + box * 0.08,
              mid_x - direction * box * 0.09, mid_y,
              mid_x + direction * box * 0.09, bottom - box * 0.08])
    elif name in ("forward", "backward"):
        offset = box * 0.1
        first = [left, top + offset, right - offset * 2, bottom - offset]
        second = [left + offset * 2, top, right, bottom - offset * 2]
        front, back = (second, first) if name == "forward" else (first, second)
        draw.rounded_rectangle(back, radius=box * 0.06, outline=BORDER_STRONG,
                               width=stroke)
        draw.rounded_rectangle(front, radius=box * 0.06, outline=color,
                               fill=(255, 255, 255, 235), width=stroke)
    elif name == "rotate":
        draw.arc([left, top, right, bottom], start=30, end=320, fill=color,
                 width=stroke)
        line([right - box * 0.16, top + box * 0.02, right - box * 0.02,
              top + box * 0.16])
        line([right - box * 0.3, top + box * 0.16, right - box * 0.02,
              top + box * 0.16])
    elif name == "center":
        rect(left, top, right, bottom, radius=box * 0.06)
        line([mid_x, top + box * 0.1, mid_x, bottom - box * 0.1], width=max(stroke // 2, 2))
        line([left + box * 0.1, mid_y, right - box * 0.1, mid_y], width=max(stroke // 2, 2))
    elif name == "help":
        draw.ellipse([left, top, right, bottom], outline=color, width=stroke)
        draw.arc([mid_x - box * 0.14, top + box * 0.16, mid_x + box * 0.14,
                  mid_y + box * 0.02], start=160, end=20, fill=color, width=stroke)
        line([mid_x, mid_y + box * 0.02, mid_x, mid_y + box * 0.16])
        draw.ellipse([mid_x - stroke * 0.6, bottom - box * 0.16 - stroke * 0.6,
                      mid_x + stroke * 0.6, bottom - box * 0.16 + stroke * 0.6],
                     fill=color)
    else:  # generic dot, so a missing glyph never crashes the toolbar
        draw.ellipse([mid_x - box * 0.1, mid_y - box * 0.1, mid_x + box * 0.1,
                      mid_y + box * 0.1], fill=color)


def anchor_icon(anchor, size=20, active=False):
    """A page outline with a filled block at `anchor` - the position presets."""
    key = ("anchor", anchor, size, active)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    scale = 4
    box = size * scale
    image = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    outline = "#FFFFFF" if active else BORDER_STRONG
    mark = "#FFFFFF" if active else ACCENT
    pad = box * 0.14
    draw.rectangle([pad, pad * 0.7, box - pad, box - pad * 0.7], outline=outline,
                   width=max(int(1.2 * scale), 2))

    vertical, _, horizontal = str(anchor).partition("-")
    inner = box * 0.1
    width, height = box * 0.3, box * 0.18
    if horizontal == "left":
        x = pad + inner
    elif horizontal == "right":
        x = box - pad - inner - width
    else:
        x = (box - width) / 2
    if vertical == "top":
        y = pad * 0.7 + inner
    elif vertical == "bottom":
        y = box - pad * 0.7 - inner - height
    else:
        y = (box - height) / 2
    draw.rectangle([x, y, x + width, y + height], fill=mark)

    photo = ImageTk.PhotoImage(image.resize((size, size), Image.LANCZOS))
    _icon_cache[key] = photo
    return photo


def app_icon_image(size=64):
    """A simple stamp mark used as the window icon when no .ico is bundled."""
    scale = 4
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    box = size * scale
    draw.rounded_rectangle([box * 0.06, box * 0.06, box * 0.94, box * 0.94],
                           radius=box * 0.22, fill=ACCENT)
    draw.rounded_rectangle([box * 0.24, box * 0.56, box * 0.76, box * 0.7],
                           radius=box * 0.05, fill="#FFFFFF")
    draw.polygon([(box * 0.5, box * 0.2), (box * 0.66, box * 0.5),
                  (box * 0.34, box * 0.5)], fill="#FFFFFF")
    return image.resize((size, size), Image.LANCZOS)


def set_window_icon(window):
    """Attach the generated app icon to a Tk window (best effort)."""
    try:
        photo = ImageTk.PhotoImage(app_icon_image(64))
        window.iconphoto(True, photo)
        window._app_icon_ref = photo      # keep a reference alive
    except tk.TclError:
        pass
