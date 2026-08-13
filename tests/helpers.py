"""Shared fixtures for the test-suite: synthetic PDFs, logos, ink measurement."""

import os
import tempfile

import pymupdf
from PIL import Image, ImageChops

# Common page sizes in points (width, height).
A4 = (595.0, 842.0)
LETTER = (612.0, 792.0)
LEGAL = (612.0, 1008.0)
A4_LANDSCAPE = (842.0, 595.0)
CUSTOM = (400.0, 300.0)

RED = (220, 30, 30, 255)
BLUE = (30, 60, 220, 255)


def temp_dir():
    path = os.path.join(tempfile.gettempdir(), "pdf_stamper_tests")
    os.makedirs(path, exist_ok=True)
    return path


def temp_path(name):
    return os.path.join(temp_dir(), name)


def make_pdf(path, pages=1, size=A4, rotation=0, text=True):
    """Create a PDF with `pages` pages of `size`, optionally /Rotate-d."""
    doc = pymupdf.open()
    for index in range(pages):
        page = doc.new_page(width=size[0], height=size[1])
        if text:
            page.insert_text((40, 60), f"Test page {index + 1}", fontsize=14)
        if rotation:
            page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    return path


def marker_block(size):
    """Side of the corner marker, in source pixels."""
    return max(min(size) // 5, 4)


def make_logo(path, size=(200, 100), marker=True):
    """A fully-inked red logo with a blue marker square in its top-left corner.

    The ink fills the image edge to edge so a measured bbox equals the stamp box
    exactly. The marker makes rotation errors detectable: a flipped or
    mis-rotated stamp puts the blue square on the wrong corner.
    """
    image = Image.new("RGBA", size, RED)
    if marker:
        block = marker_block(size)
        image.paste(Image.new("RGBA", (block, block), BLUE), (0, 0))
    image.save(path)
    return path


def make_transparent_logo(path, size=(200, 100)):
    """A logo with a genuinely transparent border and a transparent centre hole."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    inset = max(min(size) // 10, 2)
    image.paste(Image.new("RGBA", (size[0] - 2 * inset, size[1] - 2 * inset), RED),
                (inset, inset))
    hole = (size[0] // 4, size[1] // 4)
    image.paste(Image.new("RGBA", hole, (0, 0, 0, 0)),
                ((size[0] - hole[0]) // 2, (size[1] - hole[1]) // 2))
    image.save(path)
    return path


def make_jpeg_logo(path, size=(120, 60)):
    Image.new("RGB", size, RED[:3]).save(path, format="JPEG", quality=90)
    return path


def render(path, page_index=0, scale=2.0):
    """Render a saved PDF page to a PIL RGB image at `scale` px per point."""
    with pymupdf.open(path) as doc:
        page = doc[page_index]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _mask(image, channel_tests):
    channels = dict(zip("rgb", image.split()))
    mask = None
    for name, test in channel_tests.items():
        layer = channels[name].point(lambda v, t=test: 255 if t(v) else 0).convert("1")
        mask = layer if mask is None else ImageChops.logical_and(mask, layer)
    return mask


def red_bbox(image):
    """Bounding box of the logo body, in pixels of the rendered image."""
    return _mask(image, {"r": lambda v: v > 140,
                         "g": lambda v: v < 110,
                         "b": lambda v: v < 110}).getbbox()


def blue_bbox(image):
    """Bounding box of the corner marker."""
    return _mask(image, {"r": lambda v: v < 120,
                         "g": lambda v: v < 140,
                         "b": lambda v: v > 140}).getbbox()


def ink_bbox(image, threshold=245):
    """Bounding box of anything that is not (near-)white."""
    grey = image.convert("L").point(lambda v: 255 if v < threshold else 0)
    return grey.getbbox()


def center(bbox):
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
