# Shared workspace UI

The dashboard, editor and template gallery share navy workspace navigation,
locally served Inter typography, forms and keyboard navigation. The dashboard
adds a warm light canvas, teal-to-indigo actions and violet/coral accents.
Dashboard dialogs (account, creation, import, AI review and chat) inherit this
theme. Desktop navigation becomes a wrapping top navigation on smaller screens;
editor sections scroll horizontally on phones while forms remain full width.

- Navigation: `m9_dashboard/templates/m9_dashboard/workspace_nav.html`.
- Theme and responsive layouts: `m9_dashboard/static/m9_dashboard/css/workspace.css`.
- Dashboard styling: `m9_dashboard/static/m9_dashboard/css/dashboard_refresh.css`.
- Dashboard content: `m9_dashboard/templates/m9_dashboard/dashboard_workspace.html`.
- Original career illustration: `m9_dashboard/static/m9_dashboard/img/career-workspace.svg`.
- Local Inter variable font and license: `m9_dashboard/static/m9_dashboard/fonts/`.
- Shared utility source: `ui/workspace.input.css`.
- Generated utility output: `m9_dashboard/static/m9_dashboard/css/utilities.css`.

The editor exposes save, preview and PDF download directly. “More downloads”
contains exact-layout Word, editable Word and draft JSON, with an explanation of
the difference between Word formats. All existing DOM action IDs and API
contracts remain available. “Create a CV” opens the creation form from every
screen. Live preview and exported CV styles stay isolated from the workspace.

## Build

```bash
npm ci
npm run build:css
```

The pinned Tailwind version matches the existing compiled editor version.
The source scans dashboard/editor templates and JavaScript, including classes
used by dynamic cards and Alpine expressions. Commit regenerated utilities when
changing class names. Shared CSS changes invalidate editor/dashboard asset
versions automatically. No Node server or Tailwind CDN is needed in production.
The editor continues to use its existing Alpine script dependency.

## Verification

```bash
python manage.py test --settings=config.test_settings --noinput
node --test tests/*.test.cjs
```

Opt-in Chromium journeys use an isolated test database, synthetic CVs and the
existing browser harness. A locally cached Alpine 3.17.4 file is required:

```bash
RUN_WORKSPACE_BROWSER=1 EXPORT_ALPINE_JS=/path/to/alpine.js \
WORKSPACE_SCREENSHOTS=/tmp/cv-workspace-review \
python manage.py test tests.test_workspace_browser \
  --settings=config.test_settings --noinput
```

These exercise desktop navigation, editing and saving, download-menu keyboard
access, creation links, and gallery/form layouts at 390px and 320px. They also
compare shared typography between pages and check navigation and document
overflow. Existing gallery/export browser suites verify template selection,
one/multiple-page previews and PDF/exact Word downloads.

## Dashboard onboarding

An account with no CVs shows “Your first CV is waiting,” an original vector
illustration, AI creation, a template-gallery link and an import action. These
reuse the existing creation, gallery and import flows; no draft is created by
opening an action. The welcome-panel Create a CV button opens manual creation.
Stats link to the CV list or gallery and reflect saved data only.

When filters match no saved CVs, the dashboard instead offers Clear search &
filters. It retains the underlying CVs and statistics. This is separate from
new-account onboarding. Existing saved-card controls and all API contracts
remain unchanged. Administration has no frontend navigation link.

The illustration, texture, font and CSS are served locally. Inter's Latin
variable WOFF2 subset is derived from the Google Fonts Inter distribution and
includes the SIL Open Font License. Characters outside the subset use system
font fallbacks. The shared font does not change CV document frames or exports.
Intro/sparkle animations are brief; reduced-motion preferences disable all
dashboard animation, hover movement and smooth scrolling. Primary controls
have visible focus states and mobile layouts support 320px widths.

Dashboard browser journeys require no external frontend libraries:

```bash
RUN_DASHBOARD_BROWSER=1 DASHBOARD_SCREENSHOTS=/tmp/dashboard-design-review \
python manage.py test tests.test_dashboard_design_browser \
  --settings=config.test_settings --noinput
```

They verify real email login, empty-state actions, manual/AI creation mode,
import/template navigation, unchanged data on opening actions, search recovery,
card navigation, reduced motion and layouts at 1440, 1024, 768, 390 and 320px.

Reviewed previews: [desktop](dashboard-refresh/desktop.png),
[mobile](dashboard-refresh/mobile.png), and
[saved CVs](dashboard-refresh/saved-cvs.png). These use synthetic test records.

## Visual template selection during creation

Both manual creation and the AI interview now show a visual template picker in
the creation form. It loads the existing 50-design catalogue, shows actual
sample thumbnails and style labels, and offers search, style filters and a
larger preview. The selected design appears first when the form opens; several
different styles follow so users can compare layouts. The full collection
remains available by scrolling or filtering.

Previews do not select a design automatically. Select a thumbnail radio or use
the larger preview's Use button. The footer confirms the chosen name. Filtering
does not discard the selection, and previewing preserves the CV name, target
role and career level. The existing `templateId` control remains hidden as the
canonical selection for unchanged M2/M5 payloads. Gallery handoffs keep their
chosen template. No CV or chat session is created until the main submit action.

Loading prevents premature submission, retry retains typed details, and stale
catalogue responses cannot overwrite a reopened form. If metadata loading
fails, the form shows the default Modern preview with an explicit retry message;
the backend still validates template availability when creating the CV/session.
Pressing Enter in template search does not submit the CV form. Radio choices
support native keyboard navigation, and the layout stacks on phones.

Implementation: `template_picker.html`, `js/template_picker.js` and
`css/template_picker.css` under M9. It reuses existing catalogue thumbnails and
metadata without new APIs or CV schema changes.

Picker previews: [desktop](template-picker/desktop.png),
[mobile](template-picker/mobile.png) and [larger preview](template-picker/preview.png).
Verification passed: 28 focused Django tests, all eight Node test files and
13 Chromium regression journeys, plus a separate native Enter-key check that
confirms template search cannot submit the creation form.
