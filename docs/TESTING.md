# Testing Report

Run everything:

```powershell
python -m unittest discover -s tests -t .
```

**Result: 203 tests, 0 failures, 0 errors** (~65 s on the development machine,
Windows 11, Python 3.12.10, PyMuPDF 1.28.2, Pillow 12.3.0).

| Module | Tests | Covers |
| --- | --- | --- |
| `tests/test_geometry.py` | 21 | anchors, aspect fitting, rotated extents, screen↔page conversion, zoom-to-fit, hit-testing |
| `tests/test_models.py` | 27 | page-spec parsing/formatting, page selection, stamp geometry, z-order, undo/redo |
| `tests/test_services.py` | 45 | image loading and transparency, PDF open/render/cache, export, page selection, stamp removal, legacy API, config, batch |
| `tests/test_export_accuracy.py` | 9 | **preview → exported PDF position, measured from the rendered output** |
| `tests/test_per_page.py` | 38 | skipping pages, per-page overrides (position, size, angle, opacity, image), per-page export, and the per-page UI |
| `tests/test_scrolling.py` | 13 | continuous multi-page scrolling: page strip layout, lazy rendering, reaching the last page, editing on a scrolled-to page |
| `tests/test_ui.py` | 50 | the real window: open, navigate, zoom, add/drag/resize/rotate/delete, fields, presets, undo, save, removal, batch, shortcuts, empty state |

UI tests build a real `MainWindow` and synthesise real press/motion/release
events; they skip automatically when no display is available.

---

## 1. The headline test

> A stamp positioned at a known location in the preview appears at the
> mathematically corresponding location in the exported PDF.

`TestPlacementFromCanvasCoordinates.test_dropped_position_matches_export` takes a
canvas **pixel** coordinate, converts it through the same `Viewport` the mouse
uses, exports, re-opens the saved file, renders it at 144 dpi and measures the ink
bounding box. Tolerance: **3 px ≈ 1.5 pt**.

| Case | Zoom | Scroll offset | Result |
| --- | --- | --- | --- |
| A4 595×842 | 73.31 % | (13, 25) | pass |
| Letter 612×792 | 100 % | (0, 0) | pass |
| Legal 612×1008 | 40 % | (120, −340) | pass |
| A4 landscape 842×595 | 185 % | (−200, 30) | pass |
| Custom 400×300 | 240 % | (7, 9) | pass |

Plus `test_zoom_does_not_change_the_result` — the same visual drop point at 30 %,
100 % and 275 % zoom exports to the same coordinates.

`TestSaving.test_exported_position_matches_the_preview` repeats the check through
the **whole UI**: real drag on the canvas → `Save` → measure the exported ink.

## 2. PDF coverage

| Case | Test | Result |
| --- | --- | --- |
| 1 page | accuracy suite | pass |
| Multi-page (2, 3, 5, 6, 12, 150) | services + UI | pass |
| A4 / Letter / Legal / A4-landscape / custom 400×300 | accuracy suite | pass |
| Mixed page sizes in one document | `TestMixedPageSizes` | pass — the anchor recomputes per page |
| `/Rotate` 0 / 90 / 180 / 270 | `TestPageRotationAccuracy` | pass — position **and** upright orientation |
| Existing page text/graphics preserved | `test_existing_page_content_is_preserved` | pass |
| Metadata preserved (title, author) | `test_metadata_is_preserved` | pass |
| Corrupt PDF | `test_corrupt_pdf_raises_friendly_error` | pass — friendly message, no traceback |
| Encrypted PDF (AES-256) | `test_encrypted_pdf_raises_friendly_error` | pass |
| Missing file | `test_missing_file_raises_friendly_error` | pass |
| 150-page document | performance run below | pass |

## 3. Image coverage

| Case | Test | Result |
| --- | --- | --- |
| Transparent PNG (transparent border **and** a see-through hole) | `test_transparent_png_keeps_alpha`, `test_render_preserves_transparency` | pass — alpha 0 stays 0; never flattened to white |
| Transparency survives embedding | `test_transparency_survives_the_png_round_trip` | pass |
| Opaque PNG | accuracy suite | pass |
| JPEG | `test_jpeg_loads_as_rgba` | pass |
| Large image (4000×4000) | performance run | pass — 56 ms load |
| Small image (100×50) | services | pass |
| Rotated/EXIF-oriented image | `ImageOps.exif_transpose` in loader | pass |
| Corrupt image | `test_corrupt_image_raises_friendly_error` | pass |
| Oversized (decompression-bomb guard) | `test_oversized_image_is_refused` | pass |
| Aspect-ratio lock | `TestKeepAspectRatio`, `test_resize_keeps_aspect_ratio_when_locked` | pass |

## 4. Editing coverage

| Interaction | Test | Result |
| --- | --- | --- |
| Drag by an exact pixel delta | `test_drag_moves_the_stamp_by_the_pixel_delta` | pass |
| Shift-drag constrains to one axis | `test_shift_drag_constrains_to_one_axis` | pass |
| Snap to page centre | `test_snapping_to_page_centre` | pass |
| Corner resize pins the opposite corner | `test_corner_handle_resizes_and_pins_the_opposite_corner` | pass |
| Edge resize changes one axis only | `test_edge_handle_resizes_one_axis_only` | pass |
| Minimum size enforced | `test_resize_cannot_go_below_the_minimum` | pass |
| Rotation handle (free) | `test_rotation_handle_rotates_the_stamp` | pass — 90° ± 2° |
| Shift snaps rotation to 15° | `test_shift_rotation_snaps_to_15_degrees` | pass |
| Rotation direction matches the preview | `test_rotation_direction_is_clockwise_on_screen` | pass — corner-marker check at 0/45/90/180/270 |
| Click selects topmost; empty space deselects | `test_click_selects_topmost_and_empty_space_deselects` | pass |
| Arrow-key nudge (1 pt / 10 pt) | `test_arrow_keys_nudge_only_the_canvas` | pass |
| Typing in a field does **not** nudge the stamp | `test_typing_in_a_field_does_not_move_the_stamp` | pass (regression for audit P18) |
| Delete / duplicate | `test_delete_and_duplicate` | pass |
| Bring forward / send backward | `test_z_order_buttons`, `test_multiple_stamps_keep_z_order` | pass — z-order verified in the exported content stream |
| Property fields drive the model | `test_property_fields_drive_the_model` | pass |
| Invalid field text rejected, not defaulted | `test_invalid_field_text_is_rejected_not_silently_defaulted` | pass |
| Nine presets + margins | `test_presets_and_margins`, `test_all_nine_anchor_presets_land_on_their_corner` | pass |
| Preset adapts to another page size | `test_preset_adapts_to_a_different_page_size` | pass |
| Centre on page / reset size | `test_centre_and_reset_size` | pass |
| Undo/redo across add, move, resize, delete | `test_undo_redo_across_add_move_resize_delete` | pass |
| One drag = one undo step | `test_drag_creates_exactly_one_undo_step` | pass |
| Zoom in/out, fit page, fit width | `test_zoom_controls_and_status` | pass |
| Page navigation, clamped at both ends | `test_page_navigation` | pass |
| Scroll from page 1 to the last page | `test_scrolling_reaches_the_last_page` | pass |
| Wheel carries on past the bottom of a page | `test_mouse_wheel_moves_past_the_bottom_of_a_page` | pass |
| Only visible pages rasterised (40-page file) | `test_only_visible_pages_are_rendered` | pass — ≤ 6 bitmaps held |
| Stamp shown on every visible page it applies to | `test_stamp_is_shown_on_every_visible_page_it_applies_to` | pass |
| Drag the stamp on a scrolled-to page | `test_dragging_the_stamp_on_a_later_page_works` | pass |
| Clicking a stamp on another page makes it current | `test_clicking_a_stamp_on_another_page_makes_that_page_current` | pass |
| Handles follow the current page | `test_handles_follow_the_current_page` | pass |
| Edit after scrolling → correct export on every page | `test_editing_after_scrolling_still_exports_to_the_right_place` | pass |
| Mixed page sizes centred in the strip | `test_mixed_page_sizes_are_centred_individually` | pass |

## 4b. Per-page control

| Case | Test | Result |
| --- | --- | --- |
| Skip removes pages from any selection mode | `TestSkippedPages` (7 tests) | pass |
| Skip list stays compact (`2-4,8`) and round-trips | `test_skip_list_stays_compact`, `test_toggle_round_trip` | pass |
| Invalid skip spec reported, never crashes the preview | `test_invalid_skip_is_reported_but_never_crashes_display`, `test_invalid_skip_field_does_not_crash_the_preview` | pass |
| Skipped pages are not stamped in the exported file | `test_skipped_pages_are_not_stamped` | pass — images only on the kept pages |
| Skipping every page is refused with an explanation | `test_skipping_every_page_is_refused_with_an_explanation` | pass |
| Customising a page changes nothing at that moment | `test_customise_freezes_the_current_appearance` | pass |
| Editing a custom page leaves the others alone | `test_editing_a_custom_page_leaves_the_others_alone`, `test_customise_then_edit_only_affects_that_page` | pass |
| Editing shared settings leaves custom pages alone | `test_editing_a_shared_page_leaves_custom_pages_alone` | pass |
| Per-page position exported correctly | `test_one_page_gets_its_own_position` | pass — measured on pages 1, 2, 3 |
| Per-page image exported correctly | `test_one_page_gets_its_own_image` | pass — red logo on page 1, green on page 3, no bleed |
| Per-page size / rotation / opacity exported | `test_one_page_gets_its_own_size_rotation_and_opacity` | pass — two distinct embedded bitmaps |
| Skips and overrides combined | `test_overrides_and_skips_combine` | pass |
| Custom page on a different page size | `test_a_custom_page_on_a_different_page_size` | pass |
| Property fields edit only the custom page | `test_property_fields_edit_only_the_custom_page` | pass |
| Reset returns a page to the shared settings | `test_reset_puts_the_page_back_under_shared_settings` | pass |
| Different image on one page, via the UI | `test_different_image_on_one_page` | pass |
| Undo/redo of skip and customise | `test_undo_restores_skip_and_customisation` | pass |
| Preview badges for skipped / custom pages | `test_skipped_page_shows_a_badge_in_the_preview`, `test_custom_page_shows_a_badge_in_the_preview` | pass |
| Saving writes skips and per-page edits | `test_saving_writes_skips_and_per_page_edits` | pass — page 2 empty, page 3 in its own place |
| Per-page buttons disabled without a selection | `test_per_page_controls_are_disabled_without_a_selection` | pass |

## 5. Export coverage

| Case | Test | Result |
| --- | --- | --- |
| Current page only | `test_page_selection_modes` | pass |
| All pages | same | pass |
| Page range (`2-3,5`) | same | pass |
| Empty selection | `test_empty_page_selection_is_refused` | pass — explained, nothing written |
| No stamps | `test_empty_stamp_list_is_refused` / `test_save_without_stamps_is_refused` | pass |
| Existing output file | `test_overwrite_asks_first_and_cancel_keeps_the_file` | pass — file untouched on cancel |
| Saving over the source | `test_saving_over_the_source_asks_and_then_reopens` | pass — confirmed, atomic, document reopened |
| Invalid output folder | `test_invalid_output_folder_reports_save_error` | pass |
| No temp files left behind | `test_no_temp_files_left_behind` | pass |
| Progress callbacks / cancellation | `test_progress_and_cancellation` | pass |
| Output image not oversized | `test_export_embeds_reasonable_image_size` | pass |
| Batch over a folder (incl. one broken file) | `TestBatch`, `test_batch_runs_over_a_folder` | pass — 2 ok, 1 reported failed, run continued |
| Batch never overwrites its input | `test_refuses_to_write_into_the_input_folder_files` | pass |
| Batch into its own folder ignores earlier output | `test_second_run_into_the_same_folder_ignores_its_own_output` | pass |
| A folder holding only earlier output is explained | `test_folder_of_only_previous_output_is_explained` | pass |
| Stamp removal per page / all pages / repeat | `TestStampRemoval` (5 tests) | pass — other pages keep their stamps, text untouched |
| Untagged-stamp removal is opt-in | `test_untagged_removal_is_opt_in` | pass |
| Removal through the UI | `TestRemoveExistingStamps` | pass |
| v1 / v1.5 script API | `TestLegacyApi` | pass — both signatures produce the documented placement |

## 6. Performance

Measured on the development machine with a 150-page text-and-vector PDF (1.4 MB)
and a 4000×4000 RGBA PNG:

| Operation | Result |
| --- | --- |
| Open 150-page PDF | 1 ms (lazy — pages render on demand) |
| Render one page at 75 % | 10 ms |
| Same page again (cached) | < 1 ms |
| Render 10 consecutive pages | 30 ms total (3 ms/page) |
| Load 4000×4000 PNG | 56 ms |
| Prepare it as a stamp | 164 ms (cached afterwards) |
| Export 150 pages, 300 dpi stamp | **2.03 s** (14 ms/page) |
| Output size | 1.4 MB in → 1.4 MB out |
| Embedded stamp bitmap | 417×417 px from the 4000×4000 source (DPI-capped, never upsampled) |

Export and batch run on a worker thread with a progress dialog and Cancel, so the
UI stays responsive; window resize re-renders are debounced (60 ms) and the page
cache is bounded.

## 7. Manual verification

- Ran the built `dist\PDF Logo Stamper.exe` on Windows 11: window opens with the
  app icon, correct empty state, disabled actions until a document is open.
- Visual check of the layout at 1320×860 (screenshots taken during development):
  toolbar, sidebar, workspace with selection handles and rotation handle,
  properties panel, status bar reading
  `Moved to bottom right | Page 1 of 6 | 82% Fit page | app_logo.png selected`.
- Four visual defects found this way and fixed: reversed page-navigation
  chevrons, clipped rotation buttons, invisible position-preset icons, and the
  unpainted empty state.
- A fifth found the same way: the per-page controls pushed the sidebar past the
  bottom of a 700 px window. Both side panels now scroll (verified at 1120×700:
  `Skip these pages` and the page summary are reachable, and the scrollbar
  disappears again on a tall window).

## 8. Known limitations

1. **PDFs from other producers are untested.** Every test PDF is generated by
   PyMuPDF. Files from Word, InDesign, scanners or old PDF 1.3 producers were not
   available offline. The placement maths depends only on `page.rect` and
   `/Rotate`, which are producer-independent, but this is worth a real-world pass.
2. **Password-protected PDFs are rejected**, not opened with a password prompt.
3. **Stamp removal only removes stamps that are drawn by their own content
   stream** — that is how this app (and PyMuPDF's `insert_image`) writes them.
   A stamp merged into a page's main content stream by another tool cannot be
   removed without rewriting page content, which risks the real content; the app
   deliberately skips those and says so.
4. **Shared content streams are skipped during removal** (rare: pages that share
   one content object). The log records when this happens.
5. **Explorer drag-and-drop needs the optional `tkinterdnd2` package.** Without
   it the app runs normally and the empty state omits the "drop here" hint;
   in-app stamp dragging is unaffected.
6. **No high-DPI scaling test above 200 %** was performed.
7. **The executable is unsigned**, so Windows SmartScreen will warn on first run.
8. UI tests need an interactive desktop session; they self-skip on headless CI.
