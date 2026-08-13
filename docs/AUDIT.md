# Technical Audit — PDF Logo Stamper

Audit date: 2026-08-13 · Auditor: engineering review before the v2 refactor
Scope: the complete repository (source, assets, build output, git history, docs).

---

## 1. What was there

```
PDF-Logo-Stamper/
├── main.py            single file, GUI + PDF logic together
├── README.md          user documentation
├── app_logo.png       512×512 RGBA sample logo
└── dist/main.exe      30 MB PyInstaller build, committed to git
```

| Area | Finding |
| --- | --- |
| Language / runtime | Python 3.12, Windows-only in practice (Tkinter + PyInstaller) |
| GUI framework | Tkinter, plain `tk` widgets (`pack`), no `ttk`, no theming |
| PDF engine | PyMuPDF, imported through the deprecated `fitz` alias |
| Image engine | Pillow |
| Architecture | None — one 107-line script at HEAD (a 833-line working-tree revision added preview/drag/page-selection features but kept the single-module shape) |
| Modules / components | Module-level widget globals (`entry_pdf`, `entry_width`, …) plus 4 free functions; a later revision introduced a `StamperApp` class |
| PDF processing | `page.insert_image(rect, filename=…, overlay=True)` per page |
| Image processing | `Image.open(...).convert("RGBA")`, written to `processed_logo.png` in the **current working directory** |
| File handling | `filedialog` paths passed straight through; no validation, no overwrite guard |
| State management | Tk `StringVar`s as the source of truth; no model, no undo |
| Error handling | `try/except Exception` → `messagebox.showerror(str(exc))` |
| Logging | None |
| Tests | None in the repository |
| Build | Manual `pyinstaller` command documented in the README; no spec, icon, or version metadata |
| Config | None — every setting reset on each launch |

**Baseline capability set (what had to keep working):** open a PDF, choose a
logo, choose an output path, set width/height, position the stamp, stamp pages,
success/error dialogs, and — from the later working-tree revision — nine anchors
with offsets, drag-to-place, arrow-key nudge, opacity, 90° rotation, a page
spec, per-page exclusion, and removal of previously applied stamps.

---

## 2. Problems

Each entry is **Problem → Impact → Severity → Fix → Plan**. Severity reflects
consequence to a business user's documents, not code aesthetics.

### 2.1 Correctness — stamp placement

**P1. Pages with `/Rotate` are stamped in the wrong place**
- *Problem*: `insert_image()` takes the page's **unrotated** coordinates, while
  `page.rect` and `get_pixmap()` (the preview) are **visual**. The code fed
  visual coordinates straight to `insert_image`.
- *Measured*: a stamp requested at visual (20, 20) with size 100×50 landed at
  (772, 20) sized 50×100 on an A4 page with `/Rotate 90`.
- *Impact*: scanned and landscape-normalised documents — very common in offices —
  get the logo on the wrong edge, rotated. Silent: the preview looks right.
- *Severity*: **Critical**
- *Fix*: convert every placement with `page.derotation_matrix`, and correct the
  image's own angle by the page rotation.
- *Plan*: single `visual_rect_to_page()` + `image_angle_for_page()` in
  `pdf_service`; regression tests at `/Rotate` 0/90/180/270 asserting both
  position and orientation.

**P2. Rotation preview did not match the export**
- *Problem*: the preview rotated the logo with Pillow (`expand=True`, bounding box
  grows), while the export used `insert_image(rotate=90)`, which rotates the image
  *inside* the unchanged rectangle.
- *Impact*: a rotated stamp exported at a different size and position than shown.
- *Severity*: **High**
- *Fix*: pre-rotate the bitmap and insert it into the mathematically computed
  rotated bounding box (`keep_proportion=False`), using the *same* function for
  preview and export.
- *Plan*: `image_service.render()` shared by both paths; extent tests at nine
  angles; a corner-marker test that detects flips.

**P3. Rotation limited to 90° steps**
- *Problem*: `insert_image(rotate=)` only accepts multiples of 90.
- *Impact*: no diagonal "DRAFT/CONFIDENTIAL"-style stamps.
- *Severity*: Enhancement → implemented as part of P2 (any angle now works).

### 2.2 Data loss and file safety

**P4. Saving could destroy the user's original PDF**
- *Problem*: the output path was a free-text field. Choosing the input file
  overwrote it with no warning, and the save was not atomic.
- *Impact*: irreversible loss of a source document; an interrupted save left a
  truncated file where the original had been.
- *Severity*: **Critical**
- *Fix*: explicit confirmation for in-place saves, separate confirmation for
  overwriting any existing file, and writing through a temp file in the
  destination folder followed by `os.replace` (atomic on the same volume).
- *Plan*: `pdf_service.save_document()`; UI confirmations; tests for overwrite,
  cancel-keeps-file, and in-place save validity.

**P5. Temp file written into the working directory**
- *Problem*: `logo.save("processed_logo.png")` wrote next to whatever the CWD
  happened to be (for the frozen exe, often a system or Desktop folder), and the
  file was never cleaned up. A predictable name in a shared directory is also a
  minor tampering vector.
- *Severity*: Medium (security/hygiene)
- *Fix*: keep the image in memory (`io.BytesIO` → PNG bytes); no temp files at all.

**P6. Batch/removal outputs could silently overwrite inputs**
- *Problem*: no unique-name logic existed for bulk operations.
- *Severity*: High (for the new batch feature)
- *Fix*: `batch.unique_output_path()` never returns an input path and never
  overwrites an existing file; tested.

### 2.3 Robustness / error handling

**P7. Every failure surfaced as a raw exception string**
- *Problem*: `messagebox.showerror("Error", str(exc))` shows e.g.
  `code=2: no objects found`.
- *Impact*: users cannot act on it; support has nothing to work from.
- *Severity*: High
- *Fix*: `AppError(message, detail)`; plain-language text with a
  "Show technical details" disclosure and a rotating log file.

**P8. Encrypted PDFs failed confusingly**
- *Problem*: `needs_pass` was never checked; the document opened but rendered
  nothing.
- *Severity*: High
- *Fix*: detect and explain; tested with an AES-256 encrypted file.

**P9. Invalid numeric input was silently replaced by defaults**
- *Problem*: `int(entry.get())` in a `try` with a fallback default meant a typo
  produced a *different* stamp than shown.
- *Severity*: Medium
- *Fix*: `NumberField` rejects invalid text visibly (red) and leaves the model
  untouched.

**P10. An invalid page range crashed the preview** *(found by the new tests)*
- *Problem*: `parse_page_spec` raised from inside the canvas redraw while the
  user was still typing "9-2".
- *Severity*: High
- *Fix*: `PageSelection.resolve_or_empty()` for display paths; the export still
  reports the error.

**P11. No decompression-bomb guard on images**
- *Problem*: any image Pillow could open was loaded at full size.
- *Severity*: Medium (security/availability)
- *Fix*: 80 MP ceiling with a clear message; EXIF orientation honoured.

**P12. Global exception handler absent**
- *Fix*: `root.report_callback_exception` logs and shows a friendly dialog.

### 2.4 Performance

**P13. The whole page re-rendered on every keystroke**
- *Problem*: `trace_add("write")` on every variable called `refresh_preview()`,
  which re-rasterised the page — including per-pixel slider motion and every
  window-resize event.
- *Impact*: visible lag on content-heavy pages; a resize storm queued dozens of
  renders.
- *Severity*: High
- *Fix*: LRU page cache keyed by (page, zoom); a debounced resize handler; stamp
  moves repaint only canvas items.
- *Measured after*: page render 10 ms, cached 0 ms, 3 ms/page average.

**P14. UI froze during export**
- *Problem*: stamping ran on the Tk main thread with no progress.
- *Severity*: High
- *Fix*: worker thread + `ProgressDialog` with cancellation.
- *Measured after*: 150-page export 2.03 s (14 ms/page), UI responsive.

**P15. Full-resolution logos embedded regardless of stamp size**
- *Problem*: a 4000×4000 logo was embedded whole for a 1-inch stamp, once per
  page group.
- *Severity*: Medium (output size)
- *Fix*: `export_scale()` targets 300 dpi and never upsamples.
- *Measured after*: 4000×4000 source → 417×417 embedded; 150-page output stayed
  at the input's 1.4 MB.

**P16. Unbounded page-render memory**
- *Fix*: cache bounded to a handful of bitmaps; zoom capped at 400 %.

### 2.5 UX

**P17. Coordinates instead of direct manipulation** — the core complaint. Size
came only from spinboxes; there were no resize handles, no rotation handle, no
z-order, one stamp only, no zoom, no scroll, no undo. **Severity: High** →
replaced by the interactive canvas (drag, 8 handles, rotation handle, snapping) and
a continuous all-pages workspace.

**P18. Arrow keys were bound to the window, not the canvas**
- *Impact*: pressing Left while typing in a numeric field also moved the stamp.
- *Severity*: Medium — regression-tested now.

**P19. Old-Windows appearance** — raw `tk` widgets, stacked `pack()` labels, no
spacing system, no icons, no tooltips, no status bar, no menu, no shortcuts, no
recent files. **Severity: Medium** → new design system (`ui/theme.py`).

**P20. Empty state showed nothing** *(found while testing the built exe)* — the
canvas was never painted before a document loaded, so a first-time user saw a
blank grey rectangle. **Severity: Medium** → drop-zone empty state, tested.

**P21. No settings persistence** — size, opacity, anchor, folders and window
geometry reset every launch. **Severity: Medium** → `config.py` in `%APPDATA%`.

### 2.6 Maintainability

| Problem | Impact | Severity | Fix |
| --- | --- | --- | --- |
| **P22.** UI and PDF logic in one module, widget globals | untestable, unscriptable | High | layered package; no Tk below `ui/` |
| **P23.** No automated tests | every change risks silent placement regressions | High | 145 tests, incl. preview→export accuracy |
| **P24.** Deprecated `import fitz` | warns today, breaks on a future major | Medium | `import pymupdf` |
| **P25.** No pinned dependencies | "works on my machine" | Medium | `requirements.txt` |
| **P26.** Duplicated geometry maths in preview and export | the two drift apart — exactly what P2 was | High | one `geometry` module, one `render()` |
| **P27.** No `.gitignore`; `__pycache__` loose | noise in diffs | Low | added |

### 2.7 Build / distribution

| Problem | Impact | Severity | Fix |
| --- | --- | --- | --- |
| **P28.** A 30 MB `dist/main.exe` of the *old* app committed to git | repo bloat; users download stale software; no provenance | High | `.gitignore`s `dist/`, reproducible `build.ps1` + spec. **The tracked `dist/main.exe` still exists — see "Open items"** |
| **P29.** No icon, no version resource | looks unfinished; no version in Explorer | Medium | `assets/app.ico`, `version_info.txt` |
| **P30.** Build steps only in prose | not reproducible | Medium | `pdf_logo_stamper.spec`, `build.ps1` (tests then builds) |

### 2.8 Security review

| Check | Before | After |
| --- | --- | --- |
| Command / shell execution | none (good) | none; only `os.startfile` on a folder the user chose |
| Unsafe temp files | predictable name in CWD (P5) | none written |
| Path traversal | paths only from OS dialogs | unchanged, plus explicit folder checks before writing |
| Untrusted PDF handling | crash → raw error | caught, explained, logged; encryption detected |
| Untrusted image handling | unbounded decode (P11) | 80 MP cap, format validation |
| Privilege / network | none needed, none used | unchanged — the app makes no network calls |
| Dependency risk | unpinned | pinned floors; PyMuPDF ≥ 1.24, Pillow ≥ 10 (both current) |
| Log contents | n/a | file paths and counts only, never document text |

### 2.9 Windows compatibility

`os.path.samefile` and `os.replace` are used correctly for NTFS; the in-place
save closes the preview document first, because **Windows cannot replace a file
that is still open** — a defect that would only have appeared once in-place
saving was offered. High-DPI: Tk scales with the system setting; the layout uses
relative packing so it survives 125–200 % scaling.

---

## 3. Open items (recommendations not applied)

1. **`dist/main.exe` is still tracked in git** (30 MB, and it is the *old*
   application). Removing it rewrites repository content the author committed
   deliberately, so it was left alone. Recommended:
   `git rm --cached dist/main.exe` and publish builds as GitHub Release assets.
2. **Code signing** — an unsigned exe triggers SmartScreen. Needs a certificate.
3. **Installer** — a single portable exe is produced today; an Inno Setup script
   would add Start-menu entries and file associations.
4. **Password-protected PDFs** are rejected with an explanation rather than
   prompting for the password.

---

## 4. Severity summary

| Severity | Count | Items |
| --- | --- | --- |
| Critical | 2 | P1 page rotation, P4 data loss on save |
| High | 11 | P2, P6, P7, P8, P10, P13, P14, P17, P22, P23, P28 |
| Medium | 14 | P5, P9, P11, P12, P15, P16, P18, P19, P20, P21, P24, P25, P29, P30 |
| Low / Enhancement | 3 | P3, P26 (structural), P27 |

**P31. The preview showed only one page and the wheel could not leave it**
(reported after the first v2 pass). Reaching page 7 meant seven clicks on Next, and
there was no way to see the stamp across the document. **Severity: High** → the
workspace is now one continuous page strip with lazy rendering; see
[CHANGES.md](CHANGES.md#follow-up-fix-continuous-multi-page-workspace).

All items above except the four in "Open items" are fixed and covered by tests.
