# CV template system

Implemented 19 October 2026. The acceptance catalogue contains **50 renderable designs**, including the preserved `modern`, `classic`, and `developer` IDs. Open `/templates/` or choose **Template gallery** in the dashboard. The migration has been applied to the configured local PostgreSQL database; all 50 built-ins are available there.

## Existing M3/M8 assessment

M3 already had `CVTemplate`, public list/detail APIs, `TemplateService`, and a non-destructive three-template seed migration. Its fields already cover identity, description, category, ATS guidance, supported career levels/roles, thumbnail path, renderer path, availability, and version. The three existing templates extend a common M8 `base.html` and are retained without renaming or replacing their files.

M8 already owned HTML context normalization, an application-template path allowlist, authenticated owner-scoped previews, WeasyPrint PDFs, and python-docx exports. Its PDF resource fetcher blocks network and filesystem resources. M9 already loaded M3 choices into manual/AI creation and import review; M2 already persisted canonical `meta.template_id` and supported optimistic versioning. M7 already displayed live drafts by rebuilding a renderer-supplied document. M10's schema and field names are unchanged.

Baseline before implementation: **323 Django tests passed**; **7 JavaScript test files passed**. A focused baseline of 28 catalogue/rendering/dashboard/contract tests also passed before edits.

The supplied [Resume.io gallery](https://resume.io/uk/cv-templates) was inspected for general gallery functionality. No proprietary layouts, markup, CSS, names, images, or branding were copied.

## Ownership and architecture

```text
Canonical M10 CV JSON
  -> M3 CVTemplate record + curated design definition
  -> M8 context_builder + designs (presentation only)
  -> original shared header/section partials + design tokens
  -> HTML -> WeasyPrint -> PDF
```

`templates_app/catalogue.json` supplies M3's built-in design metadata. `catalogue.py` matches an ID to its registered renderer path, so a customized administrator renderer is not silently replaced. This extends the existing catalogue; it is not a second database model or persistence system. M8 interprets only the curated typography, header, section order, density, column, skill, and color settings. CV data never supplies CSS, a renderer path, or HTML markup.

47 new designs use `cv_templates/designed.html`, `partials/header.html`, `partials/section.html`, and `partials/design.css`. `m8_renderer/services/designs.py` groups normalized sections into the correct main/side columns without dropping optional content. The legacy three continue using their original template files and shared `base.html`.

`0003_template_gallery` adds category choices and missing records. Its seed is frozen in the migration and skips existing IDs and names; administrator content is preserved. Reversing its data operation deliberately leaves records intact. No CV or schema migration is introduced. On customized deployments, name collisions/disabled records may prevent a full stock catalogue; the preview command reports unavailable IDs instead of inventing working cards.

The legacy base also gains safe long-word wrapping and heading pagination rules without changing its visual theme.

Pagination follow-up: entry titles/subtitles are kept with following content only
inside their own entry. Terminal headings explicitly allow a page break, including
the `h3` elements used by new designs, so certificates and languages cannot chain
all remaining sections onto the next page. Long entries can split at normal text
boundaries. The three original templates use 10pt body text with 1.4 line spacing,
14mm A4 margins, and tighter section/header gaps. Summary and description tags do
not introduce template-indentation blank lines; user-supplied line breaks remain.
The reported short career CV now fits one page with all text preserved. Longer
documents continue onto additional pages. Coverage is in
`tests/test_renderer_pagination.py`; regenerate gallery previews after CSS changes.

Legacy `developer` retains its database category `technical`, and `classic` retains `professional`. The additive API field `gallery_category` groups Developer under Modern for the requested seven gallery categories. Existing `category` values and IDs remain compatible.

## Original layout families

| Family | Actual rendering behavior |
| --- | --- |
| ledger | Original Modern, Classic and Developer compatibility layouts |
| split | Balanced main column plus supporting education/skills rail |
| sidebar | Padded, lightly colored supporting column with a strong top accent |
| compact | Tight section spacing, short heading gaps and restrained separator rules |
| executive | Larger name treatment, generous header spacing and prominent summary |
| minimal | Light header rule, quiet headings and carefully spaced entries |
| technical | Monospaced role/headings and a vertical section guide |
| asymmetry | Oversized name and an offset supporting rail |
| traditional | Serif/small-cap typography, double rules and italic entry titles |
| ats | Single-column, conventional headings and linear text flow |
| academic | Education-first variants, inset entries and scholarly subtitle treatment |
| portfolio | Project-first variants with larger project titles and portfolio rules |

Variants also differ in section hierarchy, header arrangement, heading style, name size, font, skill treatment, density, and rail placement/proportions. Automated configuration checks reject new variants that differ only in color. The three historical layouts intentionally retain their original styling.

## Complete registered catalogue

Every row has description, career levels, role suggestions, ATS guidance, design configuration and a generated thumbnail in M3. `all` means `fresher`, `experienced`, and `other`; executive designs support `experienced` and `other`. ATS metadata is guidance, not an ATS score or universal compatibility guarantee. Multi-column and creative designs have more complex reading order.

| ID | Name | Gallery category | Family | Implementation | Levels | ATS-oriented |
| --- | --- | --- | --- | --- | --- | --- |
| `modern` | Modern | Modern | ledger | `modern.html` | all | Yes |
| `developer` | Developer | Modern | ledger | `developer.html` | all | Yes |
| `modern_horizon` | Horizon | Modern | split | `designed.html` | all | No |
| `modern_current` | Current | Modern | sidebar | `designed.html` | all | No |
| `modern_vector` | Vector | Modern | technical | `designed.html` | all | Yes |
| `modern_arc` | Arc | Modern | split | `designed.html` | all | No |
| `modern_signal` | Signal | Modern | compact | `designed.html` | all | Yes |
| `modern_axis` | Axis | Modern | sidebar | `designed.html` | all | No |
| `modern_stride` | Stride | Modern | portfolio | `designed.html` | all | No |
| `modern_frame` | Frame | Modern | asymmetry | `designed.html` | all | No |
| `classic` | Classic | Professional | ledger | `classic.html` | all | Yes |
| `professional_blue` | Blue Ledger | Professional | split | `designed.html` | all | No |
| `professional_meridian` | Meridian | Professional | traditional | `designed.html` | all | Yes |
| `professional_anchor` | Anchor | Professional | sidebar | `designed.html` | all | No |
| `professional_counsel` | Counsel | Professional | traditional | `designed.html` | all | Yes |
| `professional_precision` | Precision | Professional | compact | `designed.html` | all | Yes |
| `professional_summit` | Summit | Professional | executive | `designed.html` | all | Yes |
| `professional_clarity` | Clarity | Professional | split | `designed.html` | all | No |
| `professional_steward` | Steward | Professional | academic | `designed.html` | all | Yes |
| `professional_bridge` | Bridge | Professional | technical | `designed.html` | all | Yes |
| `simple_essential` | Essential | Simple | minimal | `designed.html` | all | Yes |
| `simple_notebook` | Notebook | Simple | academic | `designed.html` | all | Yes |
| `simple_direct` | Direct | Simple | compact | `designed.html` | all | Yes |
| `simple_outline` | Outline | Simple | minimal | `designed.html` | all | Yes |
| `simple_foundation` | Foundation | Simple | traditional | `designed.html` | all | Yes |
| `simple_study` | Study | Simple | academic | `designed.html` | all | Yes |
| `simple_breeze` | Breeze | Simple | split | `designed.html` | all | No |
| `simple_daily` | Daily | Simple | minimal | `designed.html` | all | Yes |
| `creative_studio` | Studio | Creative | asymmetry | `designed.html` | all | No |
| `creative_folio` | Folio | Creative | portfolio | `designed.html` | all | No |
| `creative_prism` | Prism | Creative | sidebar | `designed.html` | all | No |
| `creative_editorial` | Editorial | Creative | asymmetry | `designed.html` | all | No |
| `creative_canvas` | Canvas | Creative | portfolio | `designed.html` | all | No |
| `creative_muse` | Muse | Creative | split | `designed.html` | all | No |
| `creative_type` | Type | Creative | technical | `designed.html` | all | No |
| `ats_standard` | ATS Standard | ATS-Friendly | ats | `designed.html` | all | Yes |
| `ats_chronicle` | ATS Chronicle | ATS-Friendly | ats | `designed.html` | all | Yes |
| `ats_technical` | ATS Technical | ATS-Friendly | ats | `designed.html` | all | Yes |
| `ats_graduate` | ATS Graduate | ATS-Friendly | ats | `designed.html` | all | Yes |
| `ats_research` | ATS Research | ATS-Friendly | ats | `designed.html` | all | Yes |
| `ats_experience` | ATS Experience | ATS-Friendly | ats | `designed.html` | all | Yes |
| `ats_plain` | ATS Plain | ATS-Friendly | ats | `designed.html` | all | Yes |
| `minimalist_space` | Space | Minimalist | minimal | `designed.html` | all | Yes |
| `minimalist_ink` | Ink | Minimalist | traditional | `designed.html` | all | Yes |
| `minimalist_line` | Line | Minimalist | minimal | `designed.html` | all | Yes |
| `minimalist_quiet` | Quiet | Minimalist | split | `designed.html` | all | No |
| `minimalist_form` | Form | Minimalist | compact | `designed.html` | all | Yes |
| `executive_boardroom` | Boardroom | Executive | executive | `designed.html` | experienced, other | Yes |
| `executive_director` | Director | Executive | executive | `designed.html` | experienced, other | Yes |
| `executive_legacy` | Legacy | Executive | traditional | `designed.html` | experienced, other | Yes |

Category totals: Modern 10; Professional 10; Simple 8; Creative 7; ATS-Friendly 7; Minimalist 5; Executive 3.

## Gallery and public APIs

`/templates/` is an M9 HTML shell with local CSS/JavaScript and no new frontend dependencies. It offers category tabs, search, career-level filters, relevant role suggestions, reset, loading/empty/error states, retry, and Load More. It opens with 12 featured designs spanning every category and varied layout families. It displays 12 cards initially: three columns on desktop, four on wide screens, two on tablet, and one on phones. Card thumbnails are lazy-loaded cached WebP images, never per-card PDF requests.

M3 keeps the original unpaginated `GET /api/templates/` list contract for existing dashboard, chatbot, and import consumers. Opt-in pagination uses `?page=1&page_size=12` (maximum 24). Combinable filters: `category`, `career_level`, `search`, `role`. Additive metadata: `gallery_category`, `category_label`, `layout_family`, `design_config`, `preview_html_url`. Missing files, unsafe paths, and unregistered generic designs cannot be selected through M3/M2.

Each card provides Preview and Use template. The accessible native preview dialog loads one populated HTML document, supports Fit/75%/100%/125% zoom and scrolling, and clears the document on close. Embedded pages remove their outer browser padding to avoid nested scrolling. Filters preserve no private CV data.

## Synthetic data and previews

`m8_renderer/samples/comparison.json` is a complete M10-compliant fictional Alex Morgan CV with work, education, skills, projects, certifications, achievements and languages. Reserved example domains and a fictional-use phone number are used. All 50 thumbnails use exactly this profile for fair comparison. `samples.sample_cv()` also supplies eight synthetic role variants: backend, graduate, analyst, marketing, administrator, designer, manager and senior. No public preview generation reads real CV records.

M8 owns `GET /api/cvs/templates/<template_id>/preview/`. Without parameters it uses the common sample; `?sample=designer` selects a supported synthetic variant. Supplying **any** `cv_id` requires authentication and an owner-scoped CV lookup. Invalid/foreign IDs cannot fall back to private content. Personal responses use `no-store`; the endpoint sends a restrictive CSP, and the iframe disallows scripts. The gallery uses M1's authenticated transport, offers a saved-CV selector, and obtains private content only for the selected preview. Its initial CV selector loads up to 100 records; direct editor links work even for CVs outside that list.

## Thumbnail generation and visual references

Existing dependencies: WeasyPrint, Pillow, and system Poppler `pdftoppm`. No browser dependency, AI request, or PDF rendering is added to gallery page loads.

```bash
python manage.py migrate
python manage.py generate_template_previews
python manage.py collectstatic --noinput  # production static-file deployment
```

The command loads M3's real active renderer, renders the canonical comparison profile through M8 to PDF, rasterizes the first A4 page at 840 pixels high, and writes optimized WebP files to `m8_renderer/static/cv_templates/previews/<id>.webp`. Source hashes cover the catalogue, rendering templates, M8 HTML/PDF rendering code, and sample JSON. `manifest.json` records source hashes, PDF hashes, and image sizes. It skips up-to-date assets; `--force` rebuilds; `--template modern_horizon` targets one design. The 50 thumbnails total approximately 1.9 MB.

```bash
python manage.py generate_template_previews --check
```

Check mode freshly renders/rasterizes each design and compares it with the cached image using RMS pixel difference (tolerance 1), checks the source hash, and never rewrites references. Regenerate after any design/sample change. Small raster differences are possible across operating systems or installed fonts; investigate before replacing references. First-page thumbnails represent the beginning of a document, not a promise that all career histories fit one page.

Screenshots captured with actual Chromium: [desktop](template-gallery/gallery-desktop.png), [cards](template-gallery/gallery-cards.png), [mobile](template-gallery/gallery-mobile.png), [full preview](template-gallery/gallery-preview.png). The full contact sheet and individual layout thumbnails were visually inspected, in addition to automated PDF/text checks. These checks do not guarantee every possible user-supplied CV will look equally balanced.

## Selection and changing templates

Manual creation from the gallery sends name, target role, career level, selected ID and an empty draft through the existing M2 create API, then opens M7. AI creation passes these selections to the dashboard's existing creation form, which starts the existing M5 interview without changing AI logic or response contracts. Successful chat creation removes the initial creation query parameters so reload resumes the saved conversation. Sign-in links preserve a pending template selection.

The existing import review dropdown now receives all available entries from the same M3 API, sets canonical `meta.template_id`, and saves through M2. Import extraction and AI generation behavior are unchanged.

For an existing CV, open **Change template** in M7, or select a saved CV in the gallery and choose Use template. M7 keeps unsaved edits in place and asks the user to save before navigating. The gallery retrieves the owner's current version and sends only:

```json
{"template_id": "professional_blue", "expected_version": 4}
```

Existing M2 PATCH ownership/availability checks and versioning apply. Other canonical data and career metadata are preserved, the same CV ID receives a new version/snapshot, and the editor reopens with the selected M8 renderer. A stale version produces 409 and requests reload. Switching makes no AI calls and never creates a replacement CV.

M7's local draft renderer now honors M8's section ordering and column groupings and preserves skill tag/list presentation. Certification URLs are included in HTML, live preview, PDF and DOCX rather than being silently omitted.

## PDF and DOCX compatibility

PDF remains the primary design-accurate format. Saved editor and dashboard previews now show rasterized pages of the actual M8 PDF, with an explicit page count; the editable draft sidebar remains a continuous content preview. WeasyPrint uses A4 pages, margins, wrapped text, widows/orphans, and heading break rules. Content length is not forced to a single page; long entries can fragment so an oversized entry is not silently clipped. Empty sections are omitted. Long CV tests cover every layout family with large summaries, 100 skills, five experiences, eight projects, and end-of-section markers.

Word downloads now have two explicit modes:

- **Word · exact layout** uses `FixedDOCXExporter`: each actual PDF page is a 200-DPI PNG, anchored to an A4 Word page with explicit page breaks. It preserves sidebar, typography, color, margins and pagination. The text is an image and cannot be edited as normal Word paragraphs. Each page image carries its extracted page text as alternative text. PDF remains the selectable-text format for this exact design.
- **Word · editable** retains the existing python-docx exporter and now sets A4 explicitly instead of its former US Letter default. It preserves editable content and accent color using a linear layout. It can reflow and does not promise the PDF's columns or page count.

The editor's main Word button chooses exact layout; the editable option is separate and clearly labelled. Existing API clients retain the editable default unless they request `?layout=fixed`. Microsoft Word/LibreOffice native visual rendering has not been tested in this environment; fixed Word packaging, page anchors/breaks, A4 dimensions and embedded-image equality are verified automatically.

## Verification

- Baseline: 323 Django tests; 7 JavaScript test files.
- New focused suite: 16 passing tests covering all 50 HTML/PDF designs, complete sample text, A4 dimensions, nonblank pages, all 12 families with long content/missing sections, escaping, unique metadata/images, sample schema validation, filters/pagination, owner-scoped previews, version conflicts, AI-session/M2 selection persistence, import approval and migration idempotence.
- DOCX follow-up: 7 tests passed, including existing export checks and new template content. Final PDF/legacy follow-up: 9 tests passed after the wrapping/pagination adjustment. Final catalogue/filter follow-up: 13 tests passed after featured ordering.
- Final Django regression: **342 discovered; 339 passed and 3 opt-in browser tests skipped** (browser journeys also run explicitly).
- Final JavaScript regression: 8 test files passed, including gallery payload/filter behavior, unsaved-editor protection, and live-preview column/section ordering.
- Chromium: 3 journeys passed at 1600-pixel desktop and 390-pixel mobile widths, checking all 50 cards via Load More, category/search/empty state, real previews/zoom, manual creation, authenticated preview, in-place template switching, and AI handoff with retained name/role/level/template metadata. Mobile has one column and no horizontal page overflow.
- Fresh-render visual check: all 50 cached previews match current rendering. System checks and migration consistency checks pass.
- Local PostgreSQL: migration applied; 50 renderable catalogue entries; no missing built-ins. Regression tests use an isolated SQLite database and offline AI transport. The PostgreSQL catalogue was verified, but the complete suite was not run against PostgreSQL.

```bash
python manage.py test --settings=config.test_settings --noinput
node --test tests/*.test.cjs
RUN_GALLERY_BROWSER=1 python manage.py test tests.test_template_gallery_browser --settings=config.test_settings --noinput
GALLERY_SCREENSHOTS=/tmp/cv-gallery-browser RUN_GALLERY_BROWSER=1 python manage.py test tests.test_template_gallery_browser --settings=config.test_settings --noinput
```

Browser tests reuse the existing ChromeDriver helper at `/snap/chromium/current/usr/lib/chromium-browser/chromedriver`. They require local socket access; the restricted sandbox needs an execution escalation. Gallery/preview journeys need no CDN libraries or provider key. The AI handoff loads the existing dashboard, whose styling still references its existing CDN; its form assertions do not depend on that stylesheet. The older broad browser suite in `tests/browser_e2e.py` remains separately opt-in and was not rerun for this change.

## Manual acceptance walkthrough

1. Run migrations and serve the existing Django app with static files. Open `/templates/`; verify 12 populated cards, category counts, search, role suggestions, career-level filtering, Reset and Load More through all 50.
2. Preview several different families. Check header/contact wrapping, all content, Fit/100%/125%, scrolling, keyboard Close/Escape and phone layout.
3. Sign in, choose a design, create a manual CV, fill sections in M7, save and download PDF. Confirm the chosen layout in live preview and export.
4. Choose a different design and Guided AI interview. Confirm the dashboard retains name/role/level/ID; complete and save the chat, then inspect M8's selected design.
5. Import a fictional CV, review extracted content, choose any new template in the existing review dropdown, approve and check the editor/PDF.
6. Edit a saved CV without saving, then click Change template: the draft must remain. Save, open the gallery, privately preview another design, apply it, and confirm the same CV ID/content with an incremented version.
7. Open another tab, modify the same CV after opening its selection dialog, then apply the stale selection: confirm 409 and no content loss.
8. Try a long multi-page CV and optional empty sections. Inspect page transitions in the actual PDF. Download DOCX and confirm editable content while expecting simpler layout.
9. Sign out or use a second account. Personal preview/export endpoints must reject inaccessible CVs; public samples must remain fictional.

## Files created or modified

- `docs/CV_TEMPLATE_SYSTEM.md`
- `m7_editor/static/m7_editor/js/editor.js`
- `m7_editor/static/m7_editor/js/live_preview.js`
- `m7_editor/templates/m7_editor/editor.html`
- `m8_renderer/management/__init__.py`
- `m8_renderer/management/commands/__init__.py`
- `m8_renderer/management/commands/generate_template_previews.py`
- `m8_renderer/samples/__init__.py`
- `m8_renderer/samples/comparison.json`
- `m8_renderer/services/context_builder.py`
- `m8_renderer/services/designs.py`
- `m8_renderer/services/docx_exporter.py`
- `m8_renderer/services/renderer.py`
- `m8_renderer/templates/cv_templates/base.html`
- `m8_renderer/templates/cv_templates/designed.html`
- `m8_renderer/templates/cv_templates/partials/design.css`
- `m8_renderer/templates/cv_templates/partials/header.html`
- `m8_renderer/templates/cv_templates/partials/section.html`
- `m8_renderer/urls.py`
- `m8_renderer/views.py`
- `m9_dashboard/static/m9_dashboard/css/template_gallery.css`
- `m9_dashboard/static/m9_dashboard/js/dashboard.js`
- `m9_dashboard/static/m9_dashboard/js/template_gallery.js`
- `m9_dashboard/templates/m9_dashboard/dashboard.html`
- `m9_dashboard/templates/m9_dashboard/template_gallery.html`
- `m9_dashboard/urls.py`
- `m9_dashboard/views.py`
- `templates_app/catalogue.json`
- `templates_app/catalogue.py`
- `templates_app/migrations/0003_template_gallery.py`
- `templates_app/models.py`
- `templates_app/serializers.py`
- `templates_app/services.py`
- `templates_app/views.py`
- `tests/live_preview.test.cjs`
- `tests/template_gallery.test.cjs`
- `tests/test_template_gallery.py`
- `tests/test_template_gallery_browser.py`
- `m8_renderer/static/cv_templates/previews/`: 50 actual-render WebP thumbnails and `manifest.json`.
- `docs/template-gallery/`: four actual Chromium screenshots.

Known limits: ATS metadata is guidance only; editable DOCX can reflow; exact-layout DOCX uses page images; the gallery's sample preview and the editor's draft sidebar are continuous HTML; saved CV previews use actual PDF pages; the saved-CV picker initially lists at most 100 entries; legacy renderer customizations are preserved and may require separately generated previews; visual references depend on system fonts; Chromium coverage does not replace Safari/Firefox testing. No new packages, React, M10 schema changes, M2 persistence paths, or chatbot AI behavior were introduced.


## Saved-preview and export consistency update

The former saved preview showed browser HTML as one continuous sheet while the PDF used WeasyPrint page breaks. DOCX was generated independently on Letter paper. Saved previews now use `GET /api/cvs/<id>/preview/document/`, which renders the PDF and displays **every** physical page with its actual page count. The older HTML `/preview/` endpoint remains compatible with draft editing and existing integrations.

M8 owns `document_artifacts.py`, the shared PDF rasterizer and saved-preview HTML. `PDFExporter` caches rendered bytes briefly using a hash of the actual HTML and WeasyPrint version. Rasterized pages use a PDF-content hash; changed content/styles invalidate the key. Private endpoints still authenticate ownership before rendering/cache access and send `Cache-Control: no-store`. PDF and exact Word downloads share this PDF source; no AI call or CV update is involved. No data is shrunk or removed to force a page count.

The editor sends `expected_version` for saved previews and exports. A stale version returns 409 instead of quietly downloading a different CV revision. Response headers expose `X-CV-Version`, `X-CV-Page-Count` and `X-CV-PDF-SHA256` where applicable. Fixed Word uses `POST /api/cvs/<id>/export/docx/?layout=fixed&expected_version=<version>`; editable Word uses `layout=editable` (also the backwards-compatible API default).

`tests/test_export_parity.py` verifies one/multiple-page counts, identical PDF hashes, byte-identical images inside preview/Word, A4 geometry, explicit Word page anchors/breaks, editable-mode text, content-based cache invalidation, ownership, stale versions and unchanged CV records. `tests/test_export_parity_browser.py` verifies the real editor preview and downloads in Chromium. It runs with `RUN_EXPORT_BROWSER=1 EXPORT_ALPINE_JS=/path/to/the/existing/alpine.js` and uses a temporary offline copy of the editor's existing Alpine version. No runtime frontend package or database migration was introduced.

Export update files: `m8_renderer/services/document_artifacts.py`, `fixed_docx_exporter.py`, `pdf_exporter.py`, `docx_exporter.py`, `m8_renderer/views.py`, `urls.py`, `templates/m8_renderer/document_preview.html`, the M7 editor script/template, and M9's saved-preview action. Regression coverage is in `tests/test_export_parity.py`, `tests/test_export_parity_browser.py`, `tests/editor.test.cjs`, and existing M9 integration tests (their mocked PDFs now contain valid PDF structure for page-count headers).

Browser screenshots of actual PDF-page previews: [one page](export-preview/one-page-preview.png), [multiple pages](export-preview/multiple-page-preview.png). Browser test CVs use fictional data. User-provided comparison files and regenerated personal exports are kept outside the repository in private temporary storage.

Export-update verification: full regression discovered 364 tests, with 359 passing and 5 opt-in browser tests skipped. The two editor export browser journeys were also run explicitly and passed. All 8 JavaScript test files passed; all 50 cached thumbnails match fresh rendering. The specifically supplied CV 18 was verified as 2 PDF pages, 2 saved-preview pages, and 2 fixed Word pages/images, with its exported text preserved. Its original CV record and supplied download files were not changed.
