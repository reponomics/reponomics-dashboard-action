"""Render a no-data dashboard placeholder for disabled Pages mode."""

from datetime import datetime, timezone
from pathlib import Path


OUTPUT_PATH = Path("docs") / "index.html"


def render() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>GitHub Traffic Dashboard Disabled</title>
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
    <p>This repository is collecting GitHub traffic data, but the Pages
    dashboard is disabled. No traffic metrics are published here.</p>
    <p><small>Last collection: {now}</small></p>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(f"Dashboard placeholder written to {OUTPUT_PATH}")


if __name__ == "__main__":
    render()
