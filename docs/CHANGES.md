# Change Report — v1 → v2.0.0

Format: **File → Change → Reason → Impact.** Audit item IDs (P1…P30) refer to
[AUDIT.md](AUDIT.md).

---

## New: layered package

| File | Change | Reason | Impact |
| --- | --- | --- | --- |
| `pdf_stamper/__init__.py` | New package root; version and app name | P22: one 800-line module mixed UI with PDF work | Engine is importable and testable without Tk |
| `pdf_stamper/errors.py` | New `AppError(message, detail)` + reusable message texts | P7: raw exception strings reached users | Every failure has a user sentence and a technical detail |
| `pdf_stamper/logging_setup.py` | New rotating log in `%LOCALAPPDATA%\PDF Logo Stamper\logs` | P7/P12: nothing to diagnose from | Support can ask for one file; no document text logged |
| `pdf_stamper/config.py` | New JSON settings in `%APPDATA%`, atomic save, corrupt-file fallback | P21: everything reset each launch | Defaults, recent files, folders and window size persist |
| `pdf_stamper/geometry.py` | New: anchors, `fit_size`, `rotated_extent`, `Viewport`, rotation helpers | P26: preview and export each did their own maths | One conversion path — the reason preview and export now agree |
| `pdf_stamper/models.py` | New `Stamp`, `PageSelection`, `StampLayer`, `History`, page-spec parsing | P17/P22: no model, no undo, single stamp | Multiple stamps, z-order, per-stamp page scope, 60-step undo |
| `pdf_stamper/image_service.py` | New RGBA-only loader/renderer with cache, size guard, `export_scale` | P5/P11/P15 | No temp files, transparency preserved, sane output size |
| `pdf_stamper/pdf_service.py` | New document wrapper (LRU render cache), export, removal, atomic save | P1/P4/P8/P13/P16 | Correct placement, safe saves, fast paging |
| `pdf_stamper/batch.py` | New folder-to-folder batch stamping | Requirement 14 | Reuses the single-file export path, so results match the preview |
| `pdf_stamper/ui/theme.py` | New design system: palette, type scale, ttk styles, generated vector icons | P19 | Modern flat look with no binary icon assets |
| `pdf_stamper/ui/widgets.py` | New `Tooltip`, `ToolButton`, `Section`, `NumberField`, `StatusBar` | P9/P19, accessibility | Consistent spacing, tooltips, visible focus, validated fields |
| `pdf_stamper/ui/canvas.py` | New interactive canvas: render, zoom, scroll, select, drag, 8 resize handles, rotation handle, snapping | **P17 — the headline requirement** | Users edit on the page instead of typing coordinates |
| `pdf_stamper/ui/dialogs.py` | New message/progress/batch/removal/about/shortcuts dialogs | P7/P14 | Friendly errors, cancellable background work |
| `pdf_stamper/ui/app.py` | New main window: menu, toolbar, sidebar, properties panel, status bar, shortcuts, drag-and-drop | P17/P19 | The layout the brief asked for |

## Rewritten

| File | Change | Reason | Impact |
| --- | --- | --- | --- |
| `main.py` | Reduced to an entry point that still re-exports `add_logo_stamp`, `remove_stamps`, `parse_page_spec`, `format_page_spec` | Requirement 24: keep existing functionality | `python main.py` still launches; old scripts importing these names keep working (v1 *and* v1.5 signatures accepted — see `TestLegacyApi`) |
| `README.md` | Rewritten: user guide, feature list, architecture, build, tests | Documentation must match the app | — |

## Behaviour changes worth knowing

| Change | Reason | Impact |
| --- | --- | --- |
| Stamps are tagged with the `PDFLogoStamp` PDF layer | Enables per-page removal later | Same tag name as v1.5, so files stamped by the previous version are still removable |
| Opacity is baked into the image's alpha channel | Preview and export identical; no PDF transparency-group differences between viewers | A partially transparent stamp looks the same everywhere |
| Rotation accepts any angle | P3 | 90° steps still available as one-click buttons |
| Output defaults to `<name>_stamped.pdf` | P4: never write over the source by accident | Saving over the original now requires an explicit confirmation |
| Invalid numbers are rejected, not defaulted | P9 | A typo no longer silently changes the stamp |
| Page spec `"-"` alone is rejected | It silently meant "all pages" | Ambiguous input now reports an error |
| Export downsamples oversized logos to ~300 dpi | P15 | Much smaller output files; no visible quality loss |

## New build and project files

| File | Purpose |
| --- | --- |
| `requirements.txt` | Pinned floors; optional `tkinterdnd2` for Explorer drag-and-drop |
| `assets/app.ico` | Multi-resolution app/exe icon (16→256 px) |
| `version_info.txt` | Windows version resource (Explorer → Properties → Details) |
| `pdf_logo_stamper.spec` | Reproducible one-file windowed PyInstaller build |
| `build.ps1` | `pip install` → tests → clean → build, with a clear failure if tests fail |
| `.gitignore` | Keeps `dist/`, `build/`, `__pycache__`, local settings out of git |
| `tests/` | 203 automated tests (see [TESTING.md](TESTING.md)) |
| `docs/` | Audit, this report, testing report, build guide |

## Follow-up fix: continuous multi-page workspace

Reported after the first v2 pass: *"in a UI I do not scroll to all pages to adjust
logo"*. The workspace rendered a single page and the wheel only scrolled inside it,
so reaching page 7 meant clicking Next seven times and nothing showed how the
stamp looked across the document.

| File | Change | Reason | Impact |
| --- | --- | --- | --- |
| `pdf_stamper/ui/canvas.py` | Rewritten around a page **strip**: all pages laid out vertically (`_ensure_layout`), `viewport_for(index)` per page, only pages intersecting the viewport (+240 px overscan) rasterised, scroll position drives the current page (`_after_scroll`, `_most_visible_page`), page labels drawn in the gaps, current page outlined | Scrolling must reach every page, without rasterising a 300-page file | Wheel/scrollbar runs from page 1 to the last page; the stamp is visible on every page it applies to; ≤ 6 page bitmaps held at a time |
| `pdf_stamper/ui/canvas.py` | `scroll_to_page()` is now the single owner of deliberate page jumps; `apply_zoom_mode(for_page=…)` fits the target page | Page field / Prev / Next / Home / End / fit changes all did slightly different things | Consistent behaviour, and fit-page works on documents with mixed page sizes |
| `pdf_stamper/ui/canvas.py` | Click-vs-scroll arbitration (`_scroll_top`): only a real scroll re-picks the working page | A click on a stamp on another page was snapped back by the next idle scroll check, moving the handles away from the cursor | Clicking a stamp on any visible page keeps that page current |
| `pdf_stamper/ui/app.py` | New `on_page_change` callback wired to the sidebar, stamp list, page summary and status bar | Scrolling has to keep the rest of the UI truthful | Page field, "Applies to" text and status update as you scroll |
| `tests/test_scrolling.py` | New, 13 tests | Lock the behaviour down | Includes an end-to-end check that a stamp adjusted after scrolling exports to the right place on pages 1, 4 and 5 |

`Home` / `End` were added as first-page / last-page shortcuts.

## Follow-up feature: skip pages, and per-page exceptions

Requested after the scrolling fix: *"in case sometime I want to skip some pages
logo and use can delete or modify position and logo for specific page"*. Page
selection could only express ranges, and one stamp had one geometry for every
page it touched.

| File | Change | Reason | Impact |
| --- | --- | --- | --- |
| `pdf_stamper/models.py` | `PageSelection.skip` (a page spec of pages to leave alone) with `set_skipped` / `toggle_skipped` / `is_skipped`; `resolve()` subtracts it | "All pages except 3 and 7" was impossible to express | One click skips the page being viewed; the skip list stays compact (`2-4,8`) |
| `pdf_stamper/models.py` | `Stamp.overrides` - `{page: {field: value}}` - plus `value_for`, `customise`, `clear_override`, `set_values`, `image_for`, `natural_for`, and page-aware `box_on` / `rotated_box_on` / `move_to` | A specific page may need its own position, size, angle, opacity or logo | Per-page exceptions that survive later edits to the shared settings, and are deep-copied by undo and duplicate |
| `pdf_stamper/pdf_service.py` | `_place()` reads every value through `value_for(..., page_index)` | The export must honour the same exceptions the preview shows | A page with an override is written with its own geometry and image |
| `pdf_stamper/ui/canvas.py` | Draws each page with that page's values; `_edit_page()` decides whether a drag/resize/rotate writes to the page override or the shared settings; "custom for this page" and "skipped on this page" badges | Direct manipulation has to respect the exception | Dragging on a customised page moves only that page |
| `pdf_stamper/ui/app.py` | New **This page** panel (state text, *Skip page N*, *Customise for page N*, *Different image on page N*), `Skip these pages` field, context-menu entries, and property fields routed through `_edit_page()` | Make it discoverable without a modal | The panel always describes the page in view; the stamp list shows `all 6 pages, skip 2 (+1 custom)` |
| `pdf_stamper/ui/widgets.py` | New `ScrollableColumn`; both side panels now scroll when taller than the window | Found by screenshot: the new controls pushed `Skip these pages` off the bottom of the sidebar | Nothing is unreachable on a 700 px-tall window; the scrollbar only appears when needed |
| `tests/test_per_page.py` | New, 38 tests | Lock down skipping, overrides, export and the UI | Includes exports proving a skipped page is untouched and a customised page carries its own position and its own logo |

## Bugs found *by the new tests* during the refactor

These were not in the original bug list — the test-suite surfaced them:

1. **Page-range typo crashed the preview** (P10) — `9-2` raised out of the canvas
   redraw. Fixed with `resolve_or_empty()`.
2. **Theme caches were bound to the first Tk root** — a second window in the same
   process used dead font/image objects and raised `TclError`. Fixed by rebinding
   caches per root.
3. **Empty workspace was never painted** (P20) — found by running the built exe;
   the first-run screen showed nothing.
4. **Edge-handle resizing moved the stamp's centre** — the pinned point for edge
   handles must be that edge's midpoint, not the box centre.
5. **The UI test harness fed canvas coordinates to press/motion/release**, which
   Tk delivers in *widget* coordinates. Harmless while the view never scrolled;
   once it did, clicks landed on the next page and a per-page test failed for the
   right reason. The harness now converts (`UiTestCase.widget_point`).
6. **`_refresh_properties` returned before refreshing the new per-page panel** when
   nothing was selected, so its buttons never greyed out.
7. **Batch stamping into the input folder re-stamped its own output on the next
   run** — each run doubled the work (a test fixture reached 434,000 files before
   this was noticed). `process_folder` now skips files that already carry the
   output suffix when the input and output folders are the same, and explains
   itself when a folder holds nothing else.
