# Build & Development Guide

Target platform: **Windows 10 / 11**, Python **3.10 – 3.13** (developed on 3.12).

---

## 1. Install dependencies

```powershell
cd <project folder>
python -m venv .venv                 # optional but recommended
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` installs:

| Package | Why |
| --- | --- |
| `PyMuPDF >= 1.24` | PDF rendering, image insertion, saving |
| `Pillow >= 10` | image loading, transparency, rotation, Tk bridge |
| `tkinterdnd2` | *optional* — dragging files from Explorer onto the window |

Tkinter itself ships with the official python.org installer. If `import tkinter`
fails, re-run the installer and enable **tcl/tk and IDLE**.

## 2. Run the development version

```powershell
python main.py
```

Verbose logging (DEBUG level plus console output):

```powershell
$env:PDFSTAMPER_DEBUG = "1"; python main.py
```

Runtime files the app creates:

| Path | Contents |
| --- | --- |
| `%APPDATA%\PDF Logo Stamper\settings.json` | preferences, recent files, window size |
| `%LOCALAPPDATA%\PDF Logo Stamper\logs\app.log` | rotating log (1 MB × 4) |

## 3. Run the tests

```powershell
python -m unittest discover -s tests -t .     # all 150
python -m unittest tests.test_export_accuracy # placement accuracy only
python -m unittest tests.test_ui -v           # UI behaviour, verbose
```

The UI tests open real windows; they skip automatically on a headless machine.
Test artefacts are written to `%TEMP%\pdf_stamper_tests` and can be deleted
freely.

## 4. Build the executable

The one-step script installs dependencies, runs the tests, and builds only if
they pass:

```powershell
.\build.ps1
```

Options: `.\build.ps1 -SkipTests`, `.\build.ps1 -TestsOnly`.

Equivalent manual commands:

```powershell
python -m pip install "pyinstaller>=6.0"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm pdf_logo_stamper.spec
```

Output: **`dist\PDF Logo Stamper.exe`** — one self-contained file, ~39 MB, no
console window, with the app icon and version metadata. The target PC does not
need Python installed.

Verified: built with PyInstaller 6.22 and launched on Windows 11; the window,
icon and empty state come up correctly.

### What the spec does

| Setting | Reason |
| --- | --- |
| `console=False` | GUI app — no command window |
| `icon="assets/app.ico"` | taskbar, Explorer and title-bar icon |
| `version="version_info.txt"` | Explorer → Properties → Details shows version 2.0.0 |
| `hiddenimports=["PIL._tkinter_finder", "pymupdf"]` | Pillow's Tk bridge and PyMuPDF are imported indirectly |
| `datas=[("assets/app.ico", "assets")]` | icon available at runtime |
| `excludes=[numpy, matplotlib, pytest, unittest, …]` | keeps the bundle small |
| `tkinterdnd2` included only when installed | optional feature must not break the build |

## 5. Distribution checklist

1. `.\build.ps1` (tests must pass).
2. Launch `dist\PDF Logo Stamper.exe` on a machine **without** Python and check:
   open a PDF, add a stamp, drag it, save, and open the result.
3. Publish the exe as a release asset — not committed to git (`dist/` is ignored).
4. Optional but recommended:
   - **Code signing** (`signtool sign /fd SHA256 /tr <timestamp-url> …`) — without
     it Windows SmartScreen warns on first run.
   - **Installer** — e.g. Inno Setup, for Start-menu shortcuts and
     `.pdf` associations. Not provided here.

## 6. Bumping the version

Update all three, then rebuild:

1. `pdf_stamper/__init__.py` → `__version__`
2. `version_info.txt` → `filevers`, `prodvers`, `FileVersion`, `ProductVersion`
3. `docs/CHANGES.md` → a new section

## 7. Project layout

```
main.py                     entry point + backwards-compatible helper API
pdf_stamper/
  __init__.py               version, app name
  errors.py                 AppError + user-facing message texts
  logging_setup.py          rotating log configuration
  config.py                 settings in %APPDATA%
  geometry.py               anchors, rotation maths, screen<->page conversion
  models.py                 Stamp, PageSelection, StampLayer, History
  image_service.py          logo loading, transparency, rendering, caching
  pdf_service.py            open/render/export/remove, atomic saving
  batch.py                  folder-to-folder batch stamping
  ui/
    theme.py                palette, fonts, ttk styles, generated icons
    widgets.py              tooltip, tool button, section, number field, status bar
    canvas.py               interactive page view (drag / resize / rotate)
    dialogs.py              errors, progress, batch, removal, about, shortcuts
    app.py                  main window and controller
tests/                      150 automated tests
assets/app.ico              application icon
pdf_logo_stamper.spec       PyInstaller build spec
version_info.txt            Windows version resource
build.ps1                   test + build script
docs/                       AUDIT, CHANGES, TESTING, BUILD
```

Dependency direction is strictly one-way: `ui → models/services → geometry`.
Nothing outside `pdf_stamper/ui/` imports Tkinter, which is what lets the whole
engine be tested — and scripted — without a display.
