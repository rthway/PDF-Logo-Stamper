"""All PDF work: opening, rendering for the preview, export, and stamp removal.

Coordinate contract
-------------------
Stamps are stored in *visual* page points (see geometry.py). MuPDF's
``insert_image`` however expects the page's own *unrotated* coordinates, so every
placement passes through ``visual_rect_to_page()``. Likewise the stamp's rotation
is expressed clockwise-on-screen and converted with ``image_angle_for_page()``.
Getting these two conversions wrong is the classic "looked right in the preview,
landed somewhere else in the file" bug, so they live in exactly one place.
"""

import os
import re
import shutil
import tempfile

import pymupdf
from PIL import Image

from . import image_service
from .errors import (AppError, MSG_BAD_PDF, MSG_ENCRYPTED_PDF, MSG_SAVE_FAILED)
from .logging_setup import get_logger

log = get_logger(__name__)

# Stamps are tagged with this optional-content group (PDF layer) so they can be
# found and removed later. The name is kept from v1 for file compatibility.
STAMP_OCG_NAME = "PDFLogoStamp"

# A stamp inserted by insert_image() is drawn by its own minimal content stream;
# matching that exact shape is what makes per-page removal safe.
SINGLE_IMAGE_STREAM = re.compile(rb"^\s*q\s+[-\d.eE\s]+cm\s*/([^\s/]+)\s+Do\s*Q\s*$")

PDF_FILE_TYPES = [("PDF files", "*.pdf"), ("All files", "*.*")]


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------

def visual_rect_to_page(page, rect):
    """Convert a visual-space rect (x, y, w, h) to the page's own coordinates."""
    x, y, width, height = rect
    visual = pymupdf.Rect(x, y, x + width, y + height)
    converted = visual * page.derotation_matrix
    converted.normalize()
    return converted


def image_angle_for_page(page, rotation):
    """Rotation to bake into the image so it appears at `rotation` on screen."""
    return (float(rotation) - float(page.rotation)) % 360.0


def page_size(page):
    """Visible page size in points (accounts for /Rotate)."""
    return (page.rect.width, page.rect.height)


# ---------------------------------------------------------------------------
# Document wrapper
# ---------------------------------------------------------------------------

class PdfDocument:
    """An open PDF with a small LRU cache of rendered pages.

    Pages are rendered on demand and cached per (page, zoom), so paging back and
    forth in a 500-page file never re-renders and never holds more than
    `cache_size` bitmaps in memory.
    """

    def __init__(self, path, cache_size=6):
        self.path = os.path.abspath(path)
        self._cache = {}
        self._cache_order = []
        self._cache_size = cache_size
        try:
            self.doc = pymupdf.open(self.path)
        except Exception as exc:                      # noqa: BLE001 - MuPDF raises broadly
            log.warning("Cannot open PDF %s: %s", path, exc)
            raise AppError(MSG_BAD_PDF, f"{path}: {exc}")

        if self.doc.needs_pass:
            self.doc.close()
            raise AppError(MSG_ENCRYPTED_PDF, f"{path}: needs password")
        if self.doc.page_count == 0:
            self.doc.close()
            raise AppError("This PDF contains no pages.", path)
        log.info("Opened %s (%d pages)", os.path.basename(path), self.doc.page_count)

    # -- basics ----------------------------------------------------------
    @property
    def page_count(self):
        return self.doc.page_count

    @property
    def name(self):
        return os.path.basename(self.path)

    def page_size(self, index):
        return page_size(self.doc[self._valid(index)])

    def page_rotation(self, index):
        return self.doc[self._valid(index)].rotation

    def page_label(self, index):
        width, height = self.page_size(index)
        return f"{width:.0f} x {height:.0f} pt"

    def _valid(self, index):
        if not 0 <= index < self.doc.page_count:
            raise AppError(f"Page {index + 1} does not exist in this document.")
        return index

    # -- rendering -------------------------------------------------------
    def render_page(self, index, scale):
        """Render a page to a PIL RGB image at `scale` pixels per point."""
        index = self._valid(index)
        key = (index, round(float(scale), 3))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            page = self.doc[index]
            matrix = pymupdf.Matrix(scale, scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height),
                                    pixmap.samples)
        except Exception as exc:                      # noqa: BLE001
            log.warning("Render failed for page %d: %s", index + 1, exc)
            raise AppError("This page could not be displayed.\n\n"
                           "The page may use unsupported content.", exc)
        self._cache[key] = image
        self._cache_order.append(key)
        while len(self._cache_order) > self._cache_size:
            self._cache.pop(self._cache_order.pop(0), None)
        return image

    def clear_cache(self):
        self._cache.clear()
        self._cache_order.clear()

    def has_stamps(self, index):
        return bool(stamp_xrefs_on_page(self.doc, self.doc[self._valid(index)]))

    def close(self):
        self.clear_cache()
        try:
            if not self.doc.is_closed:
                self.doc.close()
        except Exception:                             # noqa: BLE001
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def _same_path(first, second):
    try:
        return os.path.exists(first) and os.path.exists(second) and \
            os.path.samefile(first, second)
    except OSError:
        return os.path.normcase(os.path.abspath(first)) == \
            os.path.normcase(os.path.abspath(second))


def save_document(doc, output_path, source_path=None):
    """Save `doc`, writing through a temp file when overwriting the source.

    The temp file lives in the destination folder so the final step is an atomic
    same-volume replace: an interrupted save can never leave a truncated PDF
    where the user's original used to be.
    """
    output_path = os.path.abspath(output_path)
    folder = os.path.dirname(output_path) or "."
    if not os.path.isdir(folder):
        raise AppError(MSG_SAVE_FAILED, f"No such folder: {folder}")

    in_place = source_path is not None and _same_path(output_path, source_path)
    handle, temp_path = None, None
    try:
        handle, temp_path = tempfile.mkstemp(suffix=".pdf", prefix=".stamp-",
                                            dir=folder)
        os.close(handle)
        handle = None
        doc.save(temp_path, garbage=3, deflate=True)
        doc.close()
        os.replace(temp_path, output_path)
        temp_path = None
    except AppError:
        raise
    except Exception as exc:                          # noqa: BLE001
        log.warning("Save failed for %s: %s", output_path, exc)
        raise AppError(MSG_SAVE_FAILED, f"{output_path}: {exc}")
    finally:
        if handle is not None:
            os.close(handle)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
    log.info("Saved %s (in place: %s)", os.path.basename(output_path), in_place)


# ---------------------------------------------------------------------------
# Export (stamping)
# ---------------------------------------------------------------------------

def export_stamped_pdf(source_path, output_path, stamps, store=None, dpi=300,
                       current_page=0, progress=None, cancelled=None):
    """Write `source_path` to `output_path` with `stamps` applied.

    stamps: iterable of models.Stamp, painted in list order (z-order).
    progress(done, total, page_index): optional callback for the UI.
    cancelled(): optional predicate; when it returns True the export is aborted.

    Returns a dict summary: pages stamped, placements written.
    """
    store = store or image_service.ImageStore()
    stamps = list(stamps)
    if not stamps:
        raise AppError("Add a stamp before saving.")

    try:
        doc = pymupdf.open(source_path)
    except Exception as exc:                          # noqa: BLE001
        raise AppError(MSG_BAD_PDF, f"{source_path}: {exc}")

    try:
        if doc.needs_pass:
            raise AppError(MSG_ENCRYPTED_PDF, source_path)

        page_count = doc.page_count
        plan = {}
        for stamp in stamps:
            for index in sorted(stamp.pages.resolve(page_count, current_page)):
                plan.setdefault(index, []).append(stamp)
        if not plan:
            raise AppError("The page selection is empty, so there is nothing to "
                           "stamp.\n\nChoose 'All pages' or a valid page range.")

        ocg = doc.add_ocg(STAMP_OCG_NAME, on=True)
        placements = 0
        for done, (index, page_stamps) in enumerate(sorted(plan.items()), start=1):
            if cancelled is not None and cancelled():
                raise AppError("The export was cancelled.")
            page = doc[index]
            visual_size = page_size(page)
            for stamp in page_stamps:
                _place(page, stamp, visual_size, ocg, store, dpi, index)
                placements += 1
            if progress:
                progress(done, len(plan), index)

        save_document(doc, output_path, source_path)
        summary = {"pages": len(plan), "placements": placements,
                   "output": os.path.abspath(output_path)}
        log.info("Exported %s: %d placements on %d pages",
                 os.path.basename(output_path), placements, len(plan))
        return summary
    except AppError:
        if not doc.is_closed:
            doc.close()
        raise
    except Exception as exc:                          # noqa: BLE001
        if not doc.is_closed:
            doc.close()
        log.exception("Unexpected export failure")
        raise AppError(MSG_SAVE_FAILED, exc)


def _place(page, stamp, visual_size, ocg, store, dpi, page_index=None):
    """Insert one stamp onto one page, preview-accurately.

    Every value is read through `Stamp.value_for(..., page_index)`, so a page with
    its own override is stamped with its own position, size, angle, opacity and
    image.
    """
    box = stamp.box_on(visual_size, page_index)
    rotation = stamp.value_for("rotation", page_index)
    angle = image_angle_for_page(page, rotation)
    image_path = stamp.image_for(page_index)
    natural = stamp.natural_for(page_index)
    scale = image_service.export_scale(natural, (box[2], box[3]), dpi)
    # Render with the page-corrected angle so the drawn extent matches the rect
    # we compute below in the page's own (derotated) coordinate system.
    image = store.render(image_path, (box[2], box[3]), angle,
                         stamp.value_for("opacity", page_index), scale)
    visual_rotated = stamp.rotated_box_on(visual_size, page_index)
    rect = visual_rect_to_page(page, visual_rotated)
    page.insert_image(rect, stream=image_service.to_png_bytes(image),
                      overlay=True, oc=ocg, keep_proportion=False)


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------

def stamp_xrefs_on_page(doc, page):
    """Image xrefs on this page tagged with the app's optional-content group."""
    try:
        ocgs = doc.get_ocgs()
    except Exception:                                 # noqa: BLE001
        return set()
    tagged = {xref for xref, info in ocgs.items()
              if info.get("name") == STAMP_OCG_NAME}
    if not tagged:
        return set()

    found = set()
    for info in page.get_images(full=True):
        xref = info[0]
        key = doc.xref_get_key(xref, "OC")
        if key and key[0] == "xref":
            try:
                oc_xref = int(key[1].split()[0])
            except (ValueError, IndexError):
                continue
            if oc_xref in tagged:
                found.add(xref)
    return found


def _content_stream_is_shared(doc, page, content_xref):
    """True when another page also uses this content stream.

    Blanking a shared stream would strip the stamp from unrelated pages, so those
    are skipped rather than risk collateral damage.
    """
    for other in range(doc.page_count):
        if other == page.number:
            continue
        try:
            if content_xref in doc[other].get_contents():
                return True
        except Exception:                             # noqa: BLE001
            continue
    return False


def remove_stamps_from_page(doc, page, tagged_only=True):
    """Remove stamp drawings from one page. Returns how many were removed."""
    stamp_xrefs = stamp_xrefs_on_page(doc, page)
    if tagged_only and not stamp_xrefs:
        return 0

    names = {info[7]: info[0] for info in page.get_images(full=True)}
    removed = 0
    for content_xref in page.get_contents():
        try:
            stream = doc.xref_stream(content_xref)
        except Exception:                             # noqa: BLE001
            continue
        if not stream:
            continue
        match = SINGLE_IMAGE_STREAM.match(stream)
        if not match:
            continue
        xref = names.get(match.group(1).decode("latin-1"))
        if xref is None or (tagged_only and xref not in stamp_xrefs):
            continue
        if _content_stream_is_shared(doc, page, content_xref):
            log.info("Skipped shared content stream %d on page %d",
                     content_xref, page.number + 1)
            continue
        doc.update_stream(content_xref, b" ")
        removed += 1
    return removed


def remove_stamps(input_pdf_path, output_pdf_path, pages=None, tagged_only=True):
    """Remove stamps from the given 0-based pages and save.

    Returns (pages_touched, stamps_removed). Nothing is written when no stamp was
    found, so a failed guess never overwrites a file.
    """
    try:
        doc = pymupdf.open(input_pdf_path)
    except Exception as exc:                          # noqa: BLE001
        raise AppError(MSG_BAD_PDF, f"{input_pdf_path}: {exc}")
    try:
        if doc.needs_pass:
            raise AppError(MSG_ENCRYPTED_PDF, input_pdf_path)
        targets = set(range(doc.page_count)) if pages is None else set(pages)
        touched = total = 0
        for index in sorted(targets):
            if not 0 <= index < doc.page_count:
                continue
            count = remove_stamps_from_page(doc, doc[index], tagged_only)
            if count:
                touched += 1
                total += count
        if total:
            save_document(doc, output_pdf_path, input_pdf_path)
        log.info("Removed %d stamp(s) from %d page(s)", total, touched)
        return touched, total
    finally:
        if not doc.is_closed:
            doc.close()


# ---------------------------------------------------------------------------
# Backwards-compatible helper (kept so v1 scripts keep working)
# ---------------------------------------------------------------------------

def add_logo_stamp(input_pdf_path, output_pdf_path, logo_path, logo_size=(200, 100),
                   anchor="bottom-center", offset=(0, 0), pages=None, opacity=100,
                   rotate=0, keep_proportion=True, bottom_margin=None):
    """Stamp a logo onto pages without the GUI. Returns the page count stamped.

    Accepts both historical call styles:

    * v1:   ``add_logo_stamp(src, out, logo, (200, 100), 750)`` - the 5th argument
      is a number, meaning "centre horizontally, y measured from the page top".
    * v1.5: ``add_logo_stamp(src, out, logo, (200, 100), 'bottom-right', (-20, -20))``
    """
    from .models import PageSelection, Stamp, format_page_spec

    if isinstance(anchor, (int, float)) and not isinstance(anchor, bool):
        bottom_margin, anchor = anchor, "top-center"
    if bottom_margin is not None:
        anchor, offset = "top-center", (0, float(bottom_margin))

    store = image_service.ImageStore()
    natural = store.natural_size(logo_path)
    selection = PageSelection("all") if pages is None else \
        PageSelection("range", format_page_spec(set(pages)))

    if anchor in ("custom", None):
        stamp = Stamp(image_path=logo_path, natural_size=natural,
                      x=float(offset[0]), y=float(offset[1]),
                      width=float(logo_size[0]), height=float(logo_size[1]),
                      rotation=float(rotate), opacity=int(opacity),
                      keep_ratio=bool(keep_proportion), anchor="custom",
                      pages=selection)
    else:
        stamp = Stamp(image_path=logo_path, natural_size=natural,
                      width=float(logo_size[0]), height=float(logo_size[1]),
                      rotation=float(rotate), opacity=int(opacity),
                      keep_ratio=bool(keep_proportion), anchor=anchor,
                      margin_x=float(offset[0]), margin_y=float(offset[1]),
                      pages=selection)
        # v1/v1.5 offsets are signed deltas from the anchor, not margins.
        if anchor.endswith("right"):
            stamp.margin_x = -float(offset[0])
        if anchor.startswith("bottom"):
            stamp.margin_y = -float(offset[1])

    summary = export_stamped_pdf(input_pdf_path, output_pdf_path, [stamp],
                                 store=store, dpi=300)
    return summary["pages"]
