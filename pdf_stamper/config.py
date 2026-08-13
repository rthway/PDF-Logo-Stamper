"""Persisted user settings (%APPDATA%\\PDF Logo Stamper\\settings.json).

Unknown / corrupt files fall back to defaults rather than crashing the app.
"""

import json
import os

from .logging_setup import get_logger

log = get_logger(__name__)

APP_DIR_NAME = "PDF Logo Stamper"
MAX_RECENT = 8

DEFAULTS = {
    "default_output_folder": "",
    "output_suffix": "_stamped",
    "stamp_width": 160.0,
    "stamp_height": 80.0,
    "stamp_opacity": 100,
    "stamp_anchor": "bottom-right",
    "stamp_margin_x": 24.0,
    "stamp_margin_y": 24.0,
    "keep_aspect_ratio": True,
    "page_selection_mode": "all",
    "recent_files": [],
    "recent_logos": [],
    "last_pdf_folder": "",
    "last_logo_folder": "",
    "window_geometry": "",
    "zoom_mode": "fit-page",
    "confirm_overwrite": True,
    "export_dpi": 300,
}


def config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def config_path():
    return os.path.join(config_dir(), "settings.json")


class Config:
    """Dict-like settings store with typed access and atomic saves."""

    def __init__(self, path=None):
        self.path = path or config_path()
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                for key, value in stored.items():
                    if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
                        self.data[key] = value
                    elif key in DEFAULTS and isinstance(DEFAULTS[key], float):
                        try:
                            self.data[key] = float(value)
                        except (TypeError, ValueError):
                            pass
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings (%s); using defaults", exc)

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("Could not save settings: %s", exc)

    # -- access ---------------------------------------------------------
    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.data[key] = value

    def add_recent(self, key, path):
        if not path:
            return
        items = [p for p in self.data.get(key, []) if os.path.normcase(p) !=
                 os.path.normcase(path)]
        items.insert(0, path)
        self.data[key] = items[:MAX_RECENT]

    def existing_recent(self, key):
        return [p for p in self.data.get(key, []) if os.path.exists(p)]
