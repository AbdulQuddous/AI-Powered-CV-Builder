# Shared workspace UI

The dashboard, editor and template gallery use the same navy/indigo workspace,
navigation, typography, cards, buttons, form controls and keyboard focus styles.
Dashboard dialogs (account, creation, import, AI review and chat) inherit this
theme. Desktop navigation becomes a wrapping top navigation on smaller screens;
editor sections scroll horizontally on phones while forms remain full width.

- Navigation: `m9_dashboard/templates/m9_dashboard/workspace_nav.html`.
- Theme and responsive layouts: `m9_dashboard/static/m9_dashboard/css/workspace.css`.
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
compare shared colors and typography between pages and check for document
overflow. Existing gallery/export browser suites verify template selection,
one/multiple-page previews and PDF/exact Word downloads.
