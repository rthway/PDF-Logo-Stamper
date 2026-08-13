"""Logo/stamp image handling.

Everything stays RGBA end to end, so a transparent PNG is never flattened onto a
white background. The *same* `render()` function feeds both the preview and the
export - only the pixel scale differs - which is what keeps them identical.
"""

import io
import os

from PIL import Image, ImageOps, UnidentifiedImageError

from . import geometry
from .errors import AppError, MSG_BAD_IMAGE, MSG_HUGE_IMAGE
from .logging_setup import get_logger

log = get_logger(__name__)

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff",
                        ".webp")
FILE_TYPES = [("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff;*.webp"),
              ("PNG images", "*.png"),
              ("JPEG images", "*.jpg;*.jpeg"),
              ("All files", "*.*")]

# Guard against decompression-bomb images (Pillow's own limit is advisory).
MAX_PIXELS = 80_000_000
# Never embed more than this many pixels per point of stamp size.
MAX_EXPORT_SCALE = 8.0


class ImageStore:
    """Loads images once and caches derived renders.

    Cache keys include the file's mtime, so replacing a logo on disk and
    re-adding it picks up the new version.
    """

    def __init__(self, max_renders=48):
        self._sources = {}
        self._renders = {}
        self._order = []
        self._max_renders = max_renders

    # -- loading ---------------------------------------------------------
    def load(self, path):
        """Return the source image as RGBA. Raises AppError for bad input."""
        try:
            key = (os.path.abspath(path), os.path.getmtime(path))
        except OSError as exc:
            raise AppError(MSG_BAD_IMAGE, f"{path}: {exc}")

        cached = self._sources.get(key)
        if cached is not None:
            return cached

        try:
            with Image.open(path) as opened:
                opened.load()
                pixels = opened.width * opened.height
                if pixels > MAX_PIXELS:
                    raise AppError(MSG_HUGE_IMAGE,
                                   f"{path}: {opened.width}x{opened.height}")
                # Honour EXIF orientation for photos used as stamps.
                oriented = ImageOps.exif_transpose(opened)
                image = oriented.convert("RGBA")
        except AppError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            log.warning("Image load failed for %s: %s", path, exc)
            raise AppError(MSG_BAD_IMAGE, f"{path}: {exc}")

        if image.width < 1 or image.height < 1:
            raise AppError(MSG_BAD_IMAGE, f"{path}: empty image")

        self._sources[key] = image
        log.info("Loaded image %s (%dx%d, alpha=%s)", os.path.basename(path),
                 image.width, image.height, has_transparency(image))
        return image

    def natural_size(self, path):
        image = self.load(path)
        return (image.width, image.height)

    # -- rendering -------------------------------------------------------
    def render(self, path, box_points, rotation=0.0, opacity=100, scale=1.0):
        """Render the stamp exactly as it must appear.

        box_points: the unrotated (width, height) of the stamp in PDF points.
        scale:      pixels per point (canvas zoom for preview, DPI/72 for export).

        Returns an RGBA image whose size is the rotated bounding box in pixels,
        so the caller can paste/insert it into `Stamp.rotated_box_on(...)`.
        """
        source = self.load(path)
        box_w, box_h = float(box_points[0]), float(box_points[1])
        if box_w <= 0 or box_h <= 0:
            raise AppError("The stamp size must be greater than zero.")

        extent_w, extent_h = geometry.rotated_extent(box_w, box_h, rotation)
        target = (max(int(round(extent_w * scale)), 1),
                  max(int(round(extent_h * scale)), 1))
        key = (os.path.abspath(path), round(box_w, 2), round(box_h, 2),
               round(float(rotation), 2), int(opacity), target)
        cached = self._renders.get(key)
        if cached is not None:
            return cached

        inner = (max(int(round(box_w * scale)), 1), max(int(round(box_h * scale)), 1))
        image = source.resize(inner, Image.LANCZOS)
        if opacity < 100:
            alpha = image.getchannel("A").point(
                lambda value: int(value * max(0, min(100, opacity)) / 100))
            image.putalpha(alpha)
        if rotation % 360:
            # Negative angle: rotation is clockwise on screen (y grows downward).
            image = image.rotate(-rotation % 360, expand=True,
                                 resample=Image.BICUBIC)
        if image.size != target:
            # Snap to the mathematically computed extent so preview and export
            # agree to the pixel instead of drifting with Pillow's rounding.
            image = image.resize(target, Image.LANCZOS)

        self._remember(key, image)
        return image

    def _remember(self, key, image):
        self._renders[key] = image
        self._order.append(key)
        while len(self._order) > self._max_renders:
            self._renders.pop(self._order.pop(0), None)

    def clear_renders(self):
        self._renders.clear()
        self._order.clear()


def has_transparency(image):
    """True when the image carries at least one non-opaque pixel."""
    if image.mode != "RGBA":
        return image.mode in ("LA", "PA") or "transparency" in image.info
    return image.getchannel("A").getextrema()[0] < 255


def to_png_bytes(image):
    """Lossless PNG bytes with the alpha channel intact."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def export_scale(natural_size, box_points, dpi=300):
    """Pixels-per-point to embed at: honours DPI but never upsamples the source."""
    box_w, box_h = max(float(box_points[0]), 1e-6), max(float(box_points[1]), 1e-6)
    natural_scale = max(natural_size[0] / box_w, natural_size[1] / box_h)
    wanted = max(float(dpi), 72.0) / 72.0
    return max(1.0, min(wanted, natural_scale, MAX_EXPORT_SCALE))


def is_supported(path):
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS
