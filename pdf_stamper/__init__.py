"""PDF Logo Stamper - a Windows desktop app for stamping logos onto PDF pages.

Layered architecture:

    ui            (pdf_stamper.ui)          Tkinter windows, canvas, dialogs
      |
    application   (pdf_stamper.models)      stamps, page selection, undo/redo
      |
    services      pdf_service, image_service, batch
      |
    foundation    geometry, config, errors, logging_setup

No module below `ui` imports Tkinter, which keeps the whole engine testable
head-less and reusable from scripts.
"""

__version__ = "2.0.0"
__author__ = "Roshan Kumar Thapa"
APP_NAME = "PDF Logo Stamper"
