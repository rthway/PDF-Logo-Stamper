"""
PDF Logo Stamper - entry point
Author: Roshan Kumar Thapa

Run the app:      python main.py
Run the tests:    python -m unittest discover -s tests -t .

The application code lives in the `pdf_stamper` package:

    pdf_stamper/ui          Tkinter window, interactive canvas, dialogs
    pdf_stamper/models      stamps, page selection, undo/redo
    pdf_stamper/pdf_service PDF open/render/export/stamp-removal
    pdf_stamper/image_service logo loading, transparency, rendering
    pdf_stamper/geometry    screen <-> page coordinate conversion

The helper functions re-exported below keep older scripts that imported
`add_logo_stamp` / `remove_stamps` from this module working unchanged.
"""

import sys

from pdf_stamper.logging_setup import setup_logging
# Re-exported for backwards compatibility with v1 / v1.5 scripts.
from pdf_stamper.pdf_service import (STAMP_OCG_NAME, add_logo_stamp,  # noqa: F401
                                     remove_stamps, remove_stamps_from_page)
from pdf_stamper.models import format_page_spec, parse_page_spec  # noqa: F401


def main():
    setup_logging()
    from pdf_stamper.ui.app import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
