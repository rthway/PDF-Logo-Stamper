"""User-facing error type.

Every failure the user can trigger is wrapped in an AppError carrying a short,
plain-language message plus the technical detail, which is logged but only shown
on demand. Raw tracebacks never reach a normal user.
"""


class AppError(Exception):
    """An error with a message written for the person using the app."""

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.message = message
        self.detail = str(detail)

    def __str__(self):
        return self.message


# Reusable message texts (kept here so wording stays consistent).
MSG_BAD_PDF = ("Unable to open this PDF.\n\n"
               "The file may be corrupted, encrypted, or an unsupported format.")
MSG_ENCRYPTED_PDF = ("This PDF is password protected.\n\n"
                     "Open it in a PDF reader, save an unprotected copy, and try again.")
MSG_BAD_IMAGE = ("Unable to load the selected image.\n\n"
                 "Please select a valid PNG, JPG, BMP, GIF, TIFF or WEBP file.")
MSG_HUGE_IMAGE = ("This image is too large to use as a stamp.\n\n"
                  "Please use an image below 80 megapixels.")
MSG_SAVE_FAILED = ("The PDF could not be saved.\n\n"
                   "Please check that:\n"
                   "  • The destination folder exists and is writable\n"
                   "  • The file is not already open in another program\n"
                   "  • There is enough free disk space")
