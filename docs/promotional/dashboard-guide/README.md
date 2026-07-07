# Promotional Dashboard Guide

This directory contains editable promotional guide artifacts for the HTML dashboard:

- `index.html` - editable HTML guide
- `../pdf/reponomics-dashboard-map.pdf` - PDF guide
- `assets/*.png` - screenshots captured from the rendered demo dashboard

These are promotional/support artifacts, not core product documentation. Keep the workflow lightweight and regenerate them only when the dashboard presentation or guide copy changes.

For external beta use, the guide should act as a bridge between the live synthetic demo and the copied-template setup path. Keep the visible guide wired to:

- live demo: `https://reponomics.github.io/reponomics-dashboard-demo/`
- copy-template path: `https://github.com/reponomics/reponomics-dashboard/generate`
- setup checklist: `https://github.com/reponomics/reponomics-dashboard/blob/main/docs/reponomics/getting-started/setup.md`
- support/feedback: `https://github.com/reponomics/reponomics-dashboard-action`

The guide should say that the demo uses synthetic data and a public demo key, that the beta line is `v0`, and that the intended beta users are maintainers comfortable with GitHub Actions, repository secrets, and a bounded repository set. Do not imply that the demo is a hosted Reponomics service or that demo unlock behavior applies to real dashboards.

## Refresh Workflow

Use the individual make targets when changing one layer:

```bash
make render-demo-preview
make dashboard-guide-assets
make dashboard-guide
```

Use the combined target when refreshing everything:

```bash
make dashboard-guide-refresh
```

The default tooling is intentionally ephemeral:

- screenshot capture uses `npx --package playwright`
- HTML/PDF generation uses `pipx run --with Pillow --with reportlab python`

No Node or Python guide-only dependencies are added to the project environment. If you already have equivalent local tooling, override the command variables:

```bash
make dashboard-guide-refresh GUIDE_NODE="node" GUIDE_PYTHON="python3"
```

On macOS, if Playwright has not installed its managed browsers, pass the local Chrome binary:

```bash
make dashboard-guide-assets GUIDE_ASSET_CAPTURE_ARGS='--chrome-executable /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome'
```

If the regular demo fixture hides an optional section, such as the code activity ribbon before event data is added, the capture script preserves the existing checked-in screenshot for that section and continues. Once the fixture includes those events, the same capture target will refresh that screenshot automatically.
