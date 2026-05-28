"""
Archived Pages-Disabled Notice Renderer

This archived helper rendered a placeholder `docs/index.html` when Pages publication was disabled.
It is no longer part of the runtime contract: disabled Pages publication means no Pages
upload/deploy step runs, while `plain` mode renders a real HTML dashboard and uploads it
as the private `html-dashboard-plain` workflow artifact.

If a future feature deliberately tombstones an existing Pages deployment after
hosted publication is disabled, this code can be used as historical reference.
That should be implemented as an explicit unpublish/tombstone operation rather
than as the normal disabled-publication path.

ORIGINAL DOCSTRING:
Render a placeholder index page when Pages publication is disabled.
"""

from datetime import datetime, timezone
from pathlib import Path


PAGES_INDEX_PATH = Path("docs") / "index.html"


def render() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    PAGES_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAGES_INDEX_PATH.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>Reponomics Dashboard Disabled</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0d1117;
      color: #c9d1d9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 42rem;
      padding: 2rem;
      line-height: 1.6;
    }}
    h1 {{ color: #58a6ff; }}
    code {{ color: #e6edf3; }}
  </style>
</head>
<body>
  <main>
    <h1>Dashboard disabled</h1>
    <p>This repository is collecting GitHub traffic and growth data, but the Pages
    dashboard is disabled. No dashboard metrics are published here.</p>
    <p><small>Last collection: {now}</small></p>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(f"Pages-disabled placeholder written to {PAGES_INDEX_PATH}")


if __name__ == "__main__":
    render()
