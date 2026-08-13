# PyInstaller build spec for PDF Logo Stamper.
#   pyinstaller --noconfirm pdf_logo_stamper.spec
# Produces a single windowed executable in dist/.

import os

block_cipher = None
project_dir = os.path.abspath(os.getcwd())

hidden_imports = [
    "PIL._tkinter_finder",     # Pillow's ImageTk bridge
    "pymupdf",
]
# tkinterdnd2 is optional; include it only when installed.
try:
    import tkinterdnd2  # noqa: F401
    hidden_imports.append("tkinterdnd2")
    from PyInstaller.utils.hooks import collect_data_files
    dnd_datas = collect_data_files("tkinterdnd2")
except Exception:
    dnd_datas = []

analysis = Analysis(
    ["main.py"],
    pathex=[project_dir],
    binaries=[],
    datas=[("assets/app.ico", "assets")] + dnd_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    # Keep the bundle lean: these are never imported by the app.
    excludes=["numpy", "matplotlib", "pytest", "unittest", "pydoc_data",
              "tkinter.test", "test"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    name="PDF Logo Stamper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                     # GUI app: no console window
    disable_windowed_traceback=False,
    icon="assets/app.ico",
    version="version_info.txt",
)
