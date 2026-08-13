# 📄 PDF Logo Stamper

**Place a logo or stamp on your PDF pages — by dragging it where you want it.**

Author: **Roshan Kumar Thapa** · Version **2.0.0** · Windows 10 / 11

Open a PDF, add your logo, drag it into position on the page, resize it with the
handles, rotate it, set the opacity, choose which pages it goes on, and save. What
you see in the preview is exactly where it lands in the saved file.

---

## Quick start

```powershell
python -m pip install -r requirements.txt
python main.py
```

Or build a single `.exe` that needs no Python: [`docs/BUILD.md`](docs/BUILD.md).

### Your first stamp in six clicks

1. **Open PDF** (or press `Ctrl+O`).
2. **Add Stamp** (`Ctrl+L`) and pick your logo — a transparent PNG works
   perfectly.
3. The logo appears on the page, already selected with editing handles.
4. **Drag** it where you want it. **Resize** with the corner handles, **rotate**
   with the round handle above it.
5. Choose **Apply stamp to**: current page, all pages, or a range like `1-3, 5, 9-`.
6. **Save PDF** (`Ctrl+S`).

Need one page to be different? Scroll to it and use the **This page** panel:
**Skip page N** leaves it unstamped, **Customise for page N** lets you move,
resize, rotate or re-image the stamp on that page alone.

---

## Features

| | |
| --- | --- |
| **Interactive editing** | Drag to move · 8 resize handles · free-rotation handle · click to select · Delete to remove |
| **Accurate placement** | Preview coordinates and exported coordinates always agree — verified by automated tests across A4, Letter, Legal, landscape, custom sizes and rotated pages |
| **PNG transparency** | RGBA end to end; a transparent logo never gets a white box behind it |
| **Any angle** | Free rotation, plus one-click 0° / 90° / 180° / 270° |
| **Opacity** | 5–100 %, previewed live |
| **Multiple stamps** | Several logos on one document, with bring-forward / send-backward |
| **Page selection** | Current page · all pages · ranges (`1-3, 5, 9-`), per stamp |
| **Skip individual pages** | Keep the stamp on the rest of the document but leave chosen pages alone — one click on the page you are viewing, or a `Skip these pages` list |
| **Per-page exceptions** | Give any single page its own position, size, angle, opacity — even a different logo — while every other page keeps the shared settings |
| **Position presets** | Nine anchors with margins — they re-anchor correctly on pages of different sizes |
| **Scroll through the whole document** | Every page is in one continuous strip — scroll (or wheel) straight from page 1 to the last page and adjust the stamp on any of them; the sidebar and status bar follow along |
| **Zoom & navigation** | Fit page, fit width, 5–400 %, `Ctrl`+wheel zoom, middle-drag pan, page field, Prev/Next, `Home`/`End` |
| **Undo / redo** | 60 steps over add, move, resize, rotate, delete, z-order and page-scope changes |
| **Snapping** | Snaps to page centre and edges with guide lines while dragging |
| **Batch** | Stamp every PDF in a folder with the same setup (Tools → Batch) |
| **Remove stamps** | Strip stamps this app applied earlier, from any pages you choose |
| **Safe saving** | Defaults to `<name>_stamped.pdf`; overwriting anything needs confirmation; saves are atomic |
| **Drag and drop** | Drop a PDF or a logo onto the window (needs the optional `tkinterdnd2` package) |
| **Remembers your setup** | Default size, opacity, anchor, margins, folders, recent files, window size |

## Keyboard shortcuts

| | | | |
| --- | --- | --- | --- |
| `Ctrl+O` | Open PDF | `Ctrl+Z` / `Ctrl+Y` | Undo / redo |
| `Ctrl+L` | Add stamp image | `Delete` | Delete selected stamp |
| `Ctrl+S` | Save stamped PDF | `Ctrl+D` | Duplicate stamp |
| `Ctrl+Shift+S` | Save as… | Arrow keys | Nudge 1 pt (`Shift`: 10 pt) |
| `Ctrl` `+` / `-` | Zoom in / out | `Page Down` / `Page Up` | Next / previous page |
| `Ctrl+0` / `Ctrl+1` | Fit page / fit width | `Home` / `End` | First / last page |
| | | `F1` | Shortcut list |

While dragging: `Shift` constrains to one axis · while resizing: `Shift` keeps the
aspect ratio · while rotating: `Shift` snaps to 15°.

---

## The window

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ File  Edit  View  Tools  Help                                                │
│ Open PDF │ Add Stamp │ 🗑 ‖ ↶ ↷ ‖ 🔍- 🔍+ ⤢ ‖ ▤        [Save As…] [Save PDF] │
├───────────────┬────────────────────────────────────┬─────────────────────────┤
│ DOCUMENT      │  ── Page 3 of 6 ──────────────     │ STAMP PROPERTIES        │
│  name, pages  │   the page you are working on,      │  image, X, Y            │
│  ‹ page 3/6 › │   with the stamp on it, handles     │  width, height          │
│ STAMPS        │   for resizing and rotating         │  aspect-ratio lock      │
│  list, add    │  ── Page 4 of 6 ──────────────     │  rotation, opacity      │
│ PRESETS       │   …scroll on through every page     │  forward / backward     │
│  3×3, margins │                                    │  centre, delete         │
│ APPLY TO      │                                    │                         │
│  page choice  │                                    │                         │
├───────────────┴────────────────────────────────────┴─────────────────────────┤
│ Ready │ Page 3 of 12 │ 85% │ logo.png selected                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## How placement stays accurate

Three coordinate spaces are involved, and exactly one module converts between
them ([`pdf_stamper/geometry.py`](pdf_stamper/geometry.py)):

1. **Screen pixels** — what the mouse reports, including zoom and scroll.
2. **Visual page points** — points (72 pt = 1 inch) from the visible top-left
   corner of the page. This is what the preview shows and what a stamp stores.
3. **Unrotated PDF points** — the page's own system, which differs whenever the
   page carries a `/Rotate` entry. Only the export step works here, via
   `page.derotation_matrix`.

Because the preview and the export share the same geometry code *and* the same
image renderer, they cannot drift apart. The test-suite proves it by exporting,
re-rendering the saved PDF, and measuring where the ink actually is — to within
1.5 pt, at five page sizes, three zoom levels, nine rotation angles and all four
page rotations. See [`docs/TESTING.md`](docs/TESTING.md).

## One stamp, page-by-page control

A stamp normally uses one set of shared settings for every page it applies to.
Two exceptions are available from the **This page** panel (or the right-click
menu) for whichever page you are looking at:

| Action | What it does |
| --- | --- |
| **Skip page N** | That page keeps no stamp; everything else is unaffected. The skipped pages are also listed as a `Skip these pages` box (`2, 5-6`), and the preview labels the page "skipped on this page". |
| **Customise for page N** | The page is frozen exactly as it looks, then becomes independent: drag, resize, rotate, change opacity or pick **Different image on page N** and only that page changes. Later edits to the shared settings leave it alone. |
| **Use the shared settings again** | Drops the exception, and the page follows the shared stamp once more. |

The stamp list shows the whole picture at a glance, e.g.
`all 6 pages, skip 2 (+1 custom)`. Everything is undoable.

## Stamps can be removed later

Every stamp is tagged with a PDF layer named `PDFLogoStamp` and drawn by its own
small content stream. **Tools → Remove stamps from a saved PDF** finds those tags
and clears only those streams, so removing the stamp from page 2 leaves every
other page intact and never touches page text or graphics. Files stamped by
another program can be handled too, with an explicit opt-in tick-box.

---

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/AUDIT.md`](docs/AUDIT.md) | Technical audit of the previous version: 30 findings with impact, severity and fixes |
| [`docs/CHANGES.md`](docs/CHANGES.md) | What changed in v2 and why, file by file |
| [`docs/TESTING.md`](docs/TESTING.md) | Test plan, results, performance figures, known limitations |
| [`docs/BUILD.md`](docs/BUILD.md) | Install, run, test, build and package |

## Architecture

```
ui  (Tkinter: window, interactive canvas, dialogs)
 ↓
models  (stamps, page selection, undo/redo)
 ↓
services  (pdf_service, image_service, batch)
 ↓
foundation  (geometry, config, errors, logging)
```

Nothing below `pdf_stamper/ui/` imports Tkinter, so the engine is testable and
scriptable on its own:

```python
from pdf_stamper.pdf_service import add_logo_stamp

# Bottom-right, 20 pt in from each edge, 80 % opaque, pages 1 and 3.
add_logo_stamp("report.pdf", "report_stamped.pdf", "logo.png",
               logo_size=(200, 100), anchor="bottom-right", offset=(-20, -20),
               pages={0, 2}, opacity=80)
```

The v1 call style still works too — `add_logo_stamp(src, out, logo, (200, 100), 750)`
centres the logo horizontally with y measured from the top of the page.

## Performance

150-page PDF, 4000×4000 PNG logo: open 1 ms · render a page 10 ms (cached < 1 ms)
· **export all 150 pages 2.0 s** · output size unchanged. Export and batch run in
the background with progress and Cancel, so the window never freezes.

## Requirements

- Windows 10 / 11 · Python 3.10+ (only to run from source)
- PyMuPDF ≥ 1.24, Pillow ≥ 10 · optional `tkinterdnd2` for Explorer drag-and-drop

## Troubleshooting

| Problem | What to do |
| --- | --- |
| “This PDF is password protected” | Open it in a PDF reader, save an unprotected copy, then stamp that |
| “Unable to load the selected image” | Use a PNG, JPG, BMP, GIF, TIFF or WEBP file under 80 megapixels |
| “The PDF could not be saved” | Check the folder exists and is writable, the file is not open elsewhere, and there is disk space |
| Stamp looks faint | Raise **Opacity** in the properties panel |
| Something went wrong | `%LOCALAPPDATA%\PDF Logo Stamper\logs\app.log`, or run with `PDFSTAMPER_DEBUG=1` |

> **Note:** `dist/main.exe` in this repository is a build of the **old** version.
> Build the current app with `.\build.ps1`, which produces
> `dist\PDF Logo Stamper.exe`.
