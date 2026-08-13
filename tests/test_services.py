"""Image loading/transparency, PDF open/render/export/removal, config, batch."""

import os
import sys
import unittest

import pymupdf
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_stamper import batch, config, image_service, pdf_service
from pdf_stamper.errors import AppError
from pdf_stamper.models import PageSelection, Stamp
from tests import helpers


class TestImageService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = image_service.ImageStore()
        cls.transparent = helpers.make_transparent_logo(
            helpers.temp_path("svc_transparent.png"))
        cls.opaque = helpers.make_logo(helpers.temp_path("svc_opaque.png"))
        cls.jpeg = helpers.make_jpeg_logo(helpers.temp_path("svc_logo.jpg"))

    def test_transparent_png_keeps_alpha(self):
        image = self.store.load(self.transparent)
        self.assertEqual(image.mode, "RGBA")
        self.assertTrue(image_service.has_transparency(image))
        self.assertEqual(image.getpixel((0, 0))[3], 0, "corner must stay transparent")

    def test_render_preserves_transparency(self):
        rendered = self.store.render(self.transparent, (200, 100), 0, 100, 1.0)
        self.assertEqual(rendered.mode, "RGBA")
        self.assertEqual(rendered.getpixel((0, 0))[3], 0)
        self.assertTrue(image_service.has_transparency(rendered))

    def test_transparency_survives_the_png_round_trip(self):
        rendered = self.store.render(self.transparent, (200, 100), 0, 100, 1.0)
        reloaded = Image.open(
            __import__("io").BytesIO(image_service.to_png_bytes(rendered)))
        self.assertEqual(reloaded.mode, "RGBA")
        self.assertEqual(reloaded.getpixel((0, 0))[3], 0)

    def test_opacity_scales_alpha_without_flattening(self):
        rendered = self.store.render(self.opaque, (200, 100), 0, 50, 1.0)
        alpha = rendered.getchannel("A")
        self.assertAlmostEqual(alpha.getextrema()[1], 127, delta=2)

    def test_jpeg_loads_as_rgba(self):
        image = self.store.load(self.jpeg)
        self.assertEqual(image.mode, "RGBA")
        self.assertFalse(image_service.has_transparency(image))

    def test_rendered_size_is_the_rotated_extent(self):
        for angle in (0, 30, 90, 180):
            with self.subTest(angle=angle):
                rendered = self.store.render(self.opaque, (200, 100), angle, 100, 2.0)
                from pdf_stamper.geometry import rotated_extent
                expected = rotated_extent(200, 100, angle)
                self.assertEqual(rendered.size,
                                 (round(expected[0] * 2), round(expected[1] * 2)))

    def test_corrupt_image_raises_friendly_error(self):
        path = helpers.temp_path("svc_corrupt.png")
        with open(path, "wb") as handle:
            handle.write(b"this is definitely not a PNG")
        with self.assertRaises(AppError) as caught:
            self.store.load(path)
        self.assertIn("Unable to load", caught.exception.message)
        self.assertTrue(caught.exception.detail)

    def test_missing_image_raises_friendly_error(self):
        with self.assertRaises(AppError):
            self.store.load(helpers.temp_path("does_not_exist.png"))

    def test_oversized_image_is_refused(self):
        original = image_service.MAX_PIXELS
        image_service.MAX_PIXELS = 100          # pretend limit
        try:
            with self.assertRaises(AppError) as caught:
                image_service.ImageStore().load(self.opaque)
            self.assertIn("too large", caught.exception.message)
        finally:
            image_service.MAX_PIXELS = original

    def test_export_scale_never_upsamples(self):
        # 200x100 source stamped into a 400x200 pt box: 1 px per pt at best.
        self.assertAlmostEqual(image_service.export_scale((200, 100), (400, 200),
                                                          dpi=600), 1.0, places=6)
        # Small box, plenty of source pixels: honour the DPI request.
        self.assertAlmostEqual(image_service.export_scale((2000, 1000), (100, 50),
                                                          dpi=288), 4.0, places=6)

    def test_render_cache_returns_same_object(self):
        first = self.store.render(self.opaque, (100, 50), 0, 100, 1.0)
        second = self.store.render(self.opaque, (100, 50), 0, 100, 1.0)
        self.assertIs(first, second)


class TestPdfDocument(unittest.TestCase):
    def test_open_and_page_metrics(self):
        path = helpers.make_pdf(helpers.temp_path("svc_doc.pdf"), 3, helpers.LETTER)
        with pdf_service.PdfDocument(path) as document:
            self.assertEqual(document.page_count, 3)
            self.assertEqual(document.page_size(0), helpers.LETTER)
            self.assertEqual(document.page_rotation(0), 0)
            self.assertIn("612", document.page_label(0))

    def test_rotated_page_reports_visual_size(self):
        path = helpers.make_pdf(helpers.temp_path("svc_rot.pdf"), 1, helpers.A4,
                                rotation=90)
        with pdf_service.PdfDocument(path) as document:
            self.assertEqual(document.page_size(0), (842.0, 595.0))
            self.assertEqual(document.page_rotation(0), 90)

    def test_render_scales_and_caches(self):
        path = helpers.make_pdf(helpers.temp_path("svc_render.pdf"), 1, helpers.A4)
        with pdf_service.PdfDocument(path) as document:
            image = document.render_page(0, 1.0)
            self.assertEqual(image.size, (595, 842))
            self.assertIs(document.render_page(0, 1.0), image)
            half = document.render_page(0, 0.5)
            self.assertEqual(half.size, (298, 421))

    def test_cache_is_bounded(self):
        path = helpers.make_pdf(helpers.temp_path("svc_cache.pdf"), 12, helpers.A4)
        with pdf_service.PdfDocument(path, cache_size=3) as document:
            for index in range(12):
                document.render_page(index, 0.3)
            self.assertLessEqual(len(document._cache), 3)

    def test_invalid_page_raises(self):
        path = helpers.make_pdf(helpers.temp_path("svc_pages.pdf"), 2)
        with pdf_service.PdfDocument(path) as document:
            with self.assertRaises(AppError):
                document.page_size(5)

    def test_corrupt_pdf_raises_friendly_error(self):
        path = helpers.temp_path("svc_broken.pdf")
        with open(path, "wb") as handle:
            handle.write(b"%PDF-1.7\nnot really a pdf\n")
        with self.assertRaises(AppError) as caught:
            pdf_service.PdfDocument(path)
        self.assertIn("Unable to open", caught.exception.message)

    def test_encrypted_pdf_raises_friendly_error(self):
        path = helpers.temp_path("svc_encrypted.pdf")
        doc = pymupdf.open()
        doc.new_page()
        doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                 owner_pw="owner", user_pw="user")
        doc.close()
        with self.assertRaises(AppError) as caught:
            pdf_service.PdfDocument(path)
        self.assertIn("password protected", caught.exception.message)

    def test_missing_file_raises_friendly_error(self):
        with self.assertRaises(AppError):
            pdf_service.PdfDocument(helpers.temp_path("nope.pdf"))


class TestExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = image_service.ImageStore()
        cls.logo = helpers.make_logo(helpers.temp_path("svc_export_logo.png"))
        cls.natural = cls.store.natural_size(cls.logo)

    def stamp(self, **kwargs):
        options = dict(image_path=self.logo, natural_size=self.natural,
                       x=50.0, y=50.0, width=120.0, height=60.0, keep_ratio=False,
                       anchor="custom", pages=PageSelection("all"))
        options.update(kwargs)
        return Stamp(**options)

    def test_page_selection_modes(self):
        source = helpers.make_pdf(helpers.temp_path("svc_sel.pdf"), 5, helpers.A4)
        cases = {
            "all": (PageSelection("all"), {0, 1, 2, 3, 4}),
            "current": (PageSelection("current"), {2}),
            "range": (PageSelection("range", "2-3,5"), {1, 2, 4}),
        }
        for name, (selection, expected) in cases.items():
            with self.subTest(mode=name):
                output = helpers.temp_path(f"svc_sel_{name}.pdf")
                summary = pdf_service.export_stamped_pdf(
                    source, output, [self.stamp(pages=selection)], store=self.store,
                    current_page=2)
                self.assertEqual(summary["pages"], len(expected))
                with pymupdf.open(output) as doc:
                    stamped = {index for index in range(doc.page_count)
                               if doc[index].get_images()}
                self.assertEqual(stamped, expected)

    def test_multiple_stamps_keep_z_order(self):
        source = helpers.make_pdf(helpers.temp_path("svc_multi.pdf"), 1, helpers.A4)
        output = helpers.temp_path("svc_multi_out.pdf")
        summary = pdf_service.export_stamped_pdf(
            source, output,
            [self.stamp(x=40.0, y=40.0), self.stamp(x=80.0, y=80.0)],
            store=self.store)
        self.assertEqual(summary["placements"], 2)
        with pymupdf.open(output) as doc:
            page = doc[0]
            names = [info[7] for info in page.get_images(full=True)]
            self.assertEqual(len(names), 2)
            streams = b" ".join(doc.xref_stream(x) for x in page.get_contents())
            # The later stamp must be drawn after the earlier one.
            self.assertLess(streams.find(names[0].encode()),
                            streams.rfind(names[1].encode()))

    def test_empty_stamp_list_is_refused(self):
        source = helpers.make_pdf(helpers.temp_path("svc_empty.pdf"), 1)
        with self.assertRaises(AppError):
            pdf_service.export_stamped_pdf(source, helpers.temp_path("x.pdf"), [],
                                           store=self.store)

    def test_empty_page_selection_is_refused(self):
        source = helpers.make_pdf(helpers.temp_path("svc_none.pdf"), 2)
        stamp = self.stamp(pages=PageSelection("range", "9-9"))
        with self.assertRaises(AppError):
            pdf_service.export_stamped_pdf(source, helpers.temp_path("y.pdf"),
                                           [stamp], store=self.store)

    def test_invalid_output_folder_reports_save_error(self):
        source = helpers.make_pdf(helpers.temp_path("svc_dest.pdf"), 1)
        bad = os.path.join(helpers.temp_dir(), "no_such_folder", "out.pdf")
        with self.assertRaises(AppError) as caught:
            pdf_service.export_stamped_pdf(source, bad, [self.stamp()],
                                           store=self.store)
        self.assertIn("could not be saved", caught.exception.message)

    def test_in_place_save_keeps_a_valid_pdf(self):
        path = helpers.make_pdf(helpers.temp_path("svc_inplace.pdf"), 2, helpers.A4)
        pdf_service.export_stamped_pdf(path, path, [self.stamp()], store=self.store)
        with pymupdf.open(path) as doc:
            self.assertEqual(doc.page_count, 2)
            self.assertTrue(doc[0].get_images())
            self.assertIn("Test page 1", doc[0].get_text())

    def test_no_temp_files_left_behind(self):
        source = helpers.make_pdf(helpers.temp_path("svc_tmp.pdf"), 1)
        output = helpers.temp_path("svc_tmp_out.pdf")
        pdf_service.export_stamped_pdf(source, output, [self.stamp()],
                                       store=self.store)
        leftovers = [name for name in os.listdir(helpers.temp_dir())
                     if name.startswith(".stamp-")]
        self.assertEqual(leftovers, [])

    def test_existing_page_content_is_preserved(self):
        source = helpers.make_pdf(helpers.temp_path("svc_keep.pdf"), 2, helpers.A4)
        output = helpers.temp_path("svc_keep_out.pdf")
        pdf_service.export_stamped_pdf(source, output, [self.stamp()],
                                       store=self.store)
        with pymupdf.open(output) as doc:
            for index in range(2):
                self.assertIn(f"Test page {index + 1}", doc[index].get_text())

    def test_progress_and_cancellation(self):
        source = helpers.make_pdf(helpers.temp_path("svc_prog.pdf"), 6, helpers.A4)
        seen = []
        pdf_service.export_stamped_pdf(
            source, helpers.temp_path("svc_prog_out.pdf"), [self.stamp()],
            store=self.store, progress=lambda done, total, page: seen.append(done))
        self.assertEqual(seen, [1, 2, 3, 4, 5, 6])

        with self.assertRaises(AppError):
            pdf_service.export_stamped_pdf(
                source, helpers.temp_path("svc_cancel.pdf"), [self.stamp()],
                store=self.store, cancelled=lambda: True)

    def test_metadata_is_preserved(self):
        path = helpers.temp_path("svc_meta.pdf")
        doc = pymupdf.open()
        doc.new_page()
        doc.set_metadata({"title": "Quarterly Report", "author": "Finance"})
        doc.save(path)
        doc.close()
        output = helpers.temp_path("svc_meta_out.pdf")
        pdf_service.export_stamped_pdf(path, output, [self.stamp()], store=self.store)
        with pymupdf.open(output) as doc:
            self.assertEqual(doc.metadata.get("title"), "Quarterly Report")
            self.assertEqual(doc.metadata.get("author"), "Finance")

    def test_export_embeds_reasonable_image_size(self):
        """A small stamp from a big logo must not embed the full-resolution image."""
        big = helpers.make_logo(helpers.temp_path("svc_big.png"), (2000, 1000))
        source = helpers.make_pdf(helpers.temp_path("svc_big_src.pdf"), 1)
        output = helpers.temp_path("svc_big_out.pdf")
        pdf_service.export_stamped_pdf(
            source, output,
            [self.stamp(image_path=big, natural_size=(2000, 1000),
                        width=100.0, height=50.0)],
            store=image_service.ImageStore(), dpi=300)
        with pymupdf.open(output) as doc:
            info = doc[0].get_images(full=True)[0]
            self.assertLessEqual(info[2], 500, "embedded image is wider than needed")


class TestStampRemoval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = image_service.ImageStore()
        cls.logo = helpers.make_logo(helpers.temp_path("svc_rm_logo.png"))

    def _stamped(self, name, pages=4):
        source = helpers.make_pdf(helpers.temp_path(f"{name}_src.pdf"), pages)
        output = helpers.temp_path(f"{name}_stamped.pdf")
        stamp = Stamp(image_path=self.logo,
                      natural_size=self.store.natural_size(self.logo),
                      x=60.0, y=60.0, width=120.0, height=60.0, keep_ratio=False,
                      anchor="custom", pages=PageSelection("all"))
        pdf_service.export_stamped_pdf(source, output, [stamp], store=self.store)
        return output

    def _draws_stamp(self, path):
        drawn = []
        with pymupdf.open(path) as doc:
            for index in range(doc.page_count):
                page = doc[index]
                names = {info[7] for info in page.get_images(full=True)}
                streams = b" ".join(doc.xref_stream(x) for x in page.get_contents())
                drawn.append(any(f"/{name} Do".encode() in streams
                                 for name in names))
        return drawn

    def test_stamps_are_tagged(self):
        path = self._stamped("svc_tag")
        with pymupdf.open(path) as doc:
            self.assertTrue(pdf_service.stamp_xrefs_on_page(doc, doc[0]))
            names = {info.get("name") for info in doc.get_ocgs().values()}
            self.assertIn(pdf_service.STAMP_OCG_NAME, names)

    def test_removal_is_per_page(self):
        path = self._stamped("svc_rm_one")
        output = helpers.temp_path("svc_rm_one_out.pdf")
        touched, total = pdf_service.remove_stamps(path, output, pages={1})
        self.assertEqual((touched, total), (1, 1))
        self.assertEqual(self._draws_stamp(output), [True, False, True, True])

    def test_removal_keeps_page_text(self):
        path = self._stamped("svc_rm_text")
        output = helpers.temp_path("svc_rm_text_out.pdf")
        pdf_service.remove_stamps(path, output, pages=None)
        with pymupdf.open(output) as doc:
            for index in range(doc.page_count):
                self.assertIn(f"Test page {index + 1}", doc[index].get_text())

    def test_removal_of_all_pages(self):
        path = self._stamped("svc_rm_all")
        output = helpers.temp_path("svc_rm_all_out.pdf")
        touched, total = pdf_service.remove_stamps(path, output, pages=None)
        self.assertEqual((touched, total), (4, 4))
        self.assertEqual(self._draws_stamp(output), [False] * 4)

    def test_second_removal_is_a_no_op_and_writes_nothing(self):
        path = self._stamped("svc_rm_twice")
        first = helpers.temp_path("svc_rm_twice_1.pdf")
        pdf_service.remove_stamps(path, first, pages={0})
        second = helpers.temp_path("svc_rm_twice_2.pdf")
        touched, total = pdf_service.remove_stamps(first, second, pages={0})
        self.assertEqual((touched, total), (0, 0))
        self.assertFalse(os.path.exists(second), "no output when nothing removed")

    def test_untagged_removal_is_opt_in(self):
        """An image drawn by another tool is left alone unless asked for."""
        path = helpers.make_pdf(helpers.temp_path("svc_untagged.pdf"), 1)
        with pymupdf.open(path) as doc:
            doc[0].insert_image(pymupdf.Rect(20, 20, 120, 70), filename=self.logo)
            doc.save(helpers.temp_path("svc_untagged2.pdf"))
        source = helpers.temp_path("svc_untagged2.pdf")

        strict = helpers.temp_path("svc_untagged_strict.pdf")
        self.assertEqual(pdf_service.remove_stamps(source, strict, tagged_only=True),
                         (0, 0))
        loose = helpers.temp_path("svc_untagged_loose.pdf")
        self.assertEqual(pdf_service.remove_stamps(source, loose, tagged_only=False),
                         (1, 1))


class TestLegacyApi(unittest.TestCase):
    """The v1 and v1.5 helper signatures must keep working."""

    @classmethod
    def setUpClass(cls):
        cls.logo = helpers.make_logo(helpers.temp_path("svc_legacy_logo.png"))

    def test_v1_bottom_margin_signature(self):
        source = helpers.make_pdf(helpers.temp_path("svc_legacy1.pdf"), 2,
                                  helpers.A4, text=False)
        output = helpers.temp_path("svc_legacy1_out.pdf")
        count = pdf_service.add_logo_stamp(source, output, self.logo, (200, 100), 750)
        self.assertEqual(count, 2)
        image = helpers.render(output, 0, 1.0)
        box = helpers.ink_bbox(image)
        # v1 centred horizontally with y measured from the top of the page.
        self.assertAlmostEqual((box[0] + box[2]) / 2, 595 / 2, delta=2)
        self.assertAlmostEqual(box[1], 750, delta=2)

    def test_v15_anchor_signature(self):
        source = helpers.make_pdf(helpers.temp_path("svc_legacy2.pdf"), 3,
                                  helpers.A4, text=False)
        output = helpers.temp_path("svc_legacy2_out.pdf")
        count = pdf_service.add_logo_stamp(source, output, self.logo,
                                          logo_size=(200, 100),
                                          anchor="bottom-right", offset=(-20, -20),
                                          pages={0, 2}, opacity=80,
                                          keep_proportion=True)
        self.assertEqual(count, 2)
        image = helpers.render(output, 0, 1.0)
        box = helpers.ink_bbox(image)
        self.assertAlmostEqual(box[2], 595 - 20, delta=2)
        self.assertAlmostEqual(box[3], 842 - 20, delta=2)
        self.assertIsNone(helpers.ink_bbox(helpers.render(output, 1, 1.0)))


class TestConfig(unittest.TestCase):
    def test_round_trip(self):
        path = helpers.temp_path("svc_settings.json")
        if os.path.exists(path):
            os.remove(path)
        first = config.Config(path)
        first.set("stamp_opacity", 55)
        first.add_recent("recent_files", "C:\\docs\\a.pdf")
        first.add_recent("recent_files", "C:\\docs\\b.pdf")
        first.save()

        second = config.Config(path)
        self.assertEqual(second.get("stamp_opacity"), 55)
        self.assertEqual(second.get("recent_files")[0], "C:\\docs\\b.pdf")

    def test_recent_list_deduplicates_and_caps(self):
        store = config.Config(helpers.temp_path("svc_settings2.json"))
        store.data["recent_files"] = []
        for index in range(12):
            store.add_recent("recent_files", f"C:\\docs\\{index}.pdf")
        store.add_recent("recent_files", "C:\\docs\\11.pdf")
        recent = store.get("recent_files")
        self.assertEqual(len(recent), config.MAX_RECENT)
        self.assertEqual(len(set(recent)), len(recent))

    def test_corrupt_settings_fall_back_to_defaults(self):
        path = helpers.temp_path("svc_settings_bad.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        store = config.Config(path)
        self.assertEqual(store.get("stamp_opacity"),
                         config.DEFAULTS["stamp_opacity"])


class TestBatch(unittest.TestCase):
    def fresh_folder(self, name):
        """An empty folder.

        Batch runs write PDFs, so a fixture folder that is never cleaned grows with
        every test run - and when input and output are the same folder it grows
        exponentially.
        """
        import shutil
        path = os.path.join(helpers.temp_dir(), name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)
        return path

    def test_processes_a_folder_and_reports_each_file(self):
        folder = self.fresh_folder("batch_in")
        output = self.fresh_folder("batch_out")
        for name in ("one.pdf", "two.pdf"):
            helpers.make_pdf(os.path.join(folder, name), 2, helpers.A4)
        with open(os.path.join(folder, "notes.txt"), "w", encoding="utf-8") as handle:
            handle.write("ignored")
        broken = os.path.join(folder, "broken.pdf")
        with open(broken, "wb") as handle:
            handle.write(b"%PDF-1.4 broken")

        logo = helpers.make_logo(helpers.temp_path("svc_batch_logo.png"))
        store = image_service.ImageStore()
        stamp = Stamp(image_path=logo, natural_size=store.natural_size(logo),
                      width=100.0, height=50.0, keep_ratio=True,
                      anchor="bottom-right", pages=PageSelection("all"))
        results = batch.process_folder(folder, output, [stamp], store=store,
                                      suffix="_stamped")

        succeeded = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]
        self.assertEqual(len(succeeded), 2)
        self.assertEqual(len(failed), 1)
        self.assertTrue(failed[0].message)
        for result in succeeded:
            self.assertTrue(os.path.exists(result.output_path))
            with pymupdf.open(result.output_path) as doc:
                self.assertTrue(doc[0].get_images())

    def _same_folder_stamp(self):
        logo = helpers.make_logo(helpers.temp_path("svc_batch_logo2.png"))
        store = image_service.ImageStore()
        return store, Stamp(image_path=logo, natural_size=store.natural_size(logo),
                            width=80.0, height=40.0, anchor="top-left",
                            pages=PageSelection("all"))

    def test_refuses_to_write_into_the_input_folder_files(self):
        folder = self.fresh_folder("batch_one_folder")
        helpers.make_pdf(os.path.join(folder, "doc.pdf"), 1)
        store, stamp = self._same_folder_stamp()
        results = batch.process_folder(folder, folder, [stamp], store=store,
                                      suffix="_stamped")
        self.assertTrue(results[0].ok)
        self.assertNotEqual(os.path.normcase(results[0].output_path),
                            os.path.normcase(os.path.join(folder, "doc.pdf")))
        self.assertTrue(os.path.exists(os.path.join(folder, "doc.pdf")))

    def test_second_run_into_the_same_folder_ignores_its_own_output(self):
        """Otherwise each run stamps the previous run's results, forever."""
        folder = self.fresh_folder("batch_one_folder_twice")
        helpers.make_pdf(os.path.join(folder, "doc.pdf"), 1)
        store, stamp = self._same_folder_stamp()
        first = batch.process_folder(folder, folder, [stamp], store=store,
                                     suffix="_stamped")
        self.assertEqual(len(first), 1)
        second = batch.process_folder(folder, folder, [stamp], store=store,
                                      suffix="_stamped")
        self.assertEqual([os.path.basename(r.source_path) for r in second],
                         ["doc.pdf"], "only the original may be processed again")
        self.assertEqual(len([name for name in os.listdir(folder)
                              if name.endswith(".pdf")]), 3)

    def test_folder_of_only_previous_output_is_explained(self):
        folder = self.fresh_folder("batch_only_output")
        helpers.make_pdf(os.path.join(folder, "doc_stamped.pdf"), 1)
        store, stamp = self._same_folder_stamp()
        with self.assertRaises(AppError) as caught:
            batch.process_folder(folder, folder, [stamp], store=store,
                                 suffix="_stamped")
        self.assertIn("earlier batch run", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
