"""Batch stamping of every PDF in a folder.

Deliberately thin: it reuses the same export path as the single-document flow, so
a batch run can never place stamps differently from what the preview showed.
Failures are collected per file instead of aborting the run.
"""

import os
from dataclasses import dataclass

from . import image_service, pdf_service
from .errors import AppError
from .logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class BatchResult:
    source_path: str
    output_path: str = ""
    ok: bool = False
    pages: int = 0
    message: str = ""


def find_pdfs(folder, recursive=False):
    """PDF files in `folder`, sorted, skipping our own previous outputs is the
    caller's business (outputs normally go to a different folder)."""
    if not os.path.isdir(folder):
        raise AppError("The input folder does not exist.\n\n"
                       "Choose a folder that contains PDF files.", folder)
    found = []
    if recursive:
        for root, _, names in os.walk(folder):
            found += [os.path.join(root, name) for name in names
                      if name.lower().endswith(".pdf")]
    else:
        found = [os.path.join(folder, name) for name in os.listdir(folder)
                 if name.lower().endswith(".pdf")
                 and os.path.isfile(os.path.join(folder, name))]
    return sorted(found)


def _same_folder(first, second):
    try:
        return os.path.samefile(first, second)
    except OSError:
        return os.path.normcase(os.path.abspath(first)) == \
            os.path.normcase(os.path.abspath(second))


def unique_output_path(folder, source_path, suffix="_stamped"):
    """Build an output path that never silently overwrites an input file."""
    base, extension = os.path.splitext(os.path.basename(source_path))
    candidate = os.path.join(folder, f"{base}{suffix}{extension}")
    if os.path.normcase(os.path.abspath(candidate)) == \
            os.path.normcase(os.path.abspath(source_path)):
        candidate = os.path.join(folder, f"{base}{suffix}_1{extension}")
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base}{suffix}_{counter}{extension}")
        counter += 1
    return candidate


def process_folder(input_folder, output_folder, stamps, store=None, suffix="_stamped",
                   recursive=False, dpi=300, progress=None, cancelled=None):
    """Stamp every PDF in `input_folder`, writing results to `output_folder`.

    progress(done, total, name): called after each file.
    Returns a list of BatchResult - one per input file, failures included.
    """
    store = store or image_service.ImageStore()
    sources = find_pdfs(input_folder, recursive)
    if not sources:
        raise AppError("No PDF files were found in that folder.", input_folder)

    # Writing results back into the input folder would otherwise make the next run
    # stamp its own output (and the run after that stamp *those*), so previously
    # produced files are left out.
    if _same_folder(input_folder, output_folder) and suffix:
        keep = [path for path in sources
                if not os.path.splitext(os.path.basename(path))[0].endswith(suffix)]
        if len(keep) != len(sources):
            log.info("Skipped %d previously stamped file(s) in the output folder",
                     len(sources) - len(keep))
        sources = keep
        if not sources:
            raise AppError("Every PDF in that folder was produced by an earlier "
                           "batch run.\n\nChoose a different input folder, or a "
                           "separate output folder.", input_folder)

    os.makedirs(output_folder, exist_ok=True)
    results = []
    for index, source in enumerate(sources, start=1):
        if cancelled is not None and cancelled():
            break
        result = BatchResult(source_path=source)
        try:
            result.output_path = unique_output_path(output_folder, source, suffix)
            summary = pdf_service.export_stamped_pdf(source, result.output_path,
                                                     stamps, store=store, dpi=dpi)
            result.ok = True
            result.pages = summary["pages"]
            result.message = f"{summary['pages']} page(s) stamped"
        except AppError as exc:
            result.ok = False
            result.message = exc.message.splitlines()[0]
            log.warning("Batch failure for %s: %s", source, exc.detail or exc.message)
        except Exception as exc:                      # noqa: BLE001
            result.ok = False
            result.message = "Unexpected error while processing this file."
            log.exception("Unexpected batch failure for %s: %s", source, exc)
        results.append(result)
        if progress:
            progress(index, len(sources), os.path.basename(source))
    log.info("Batch finished: %d ok, %d failed",
             sum(1 for r in results if r.ok), sum(1 for r in results if not r.ok))
    return results
