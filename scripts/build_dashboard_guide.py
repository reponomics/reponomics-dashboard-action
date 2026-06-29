"""Build editable HTML and PDF dashboard guide artifacts."""
# ruff: noqa: ISC002

from __future__ import annotations

import html
import importlib
from pathlib import Path
from typing import Any, TypedDict


ROOT = Path(__file__).resolve().parents[1]
GUIDE_DIR = ROOT / "docs/promotional/dashboard-guide"
ASSET_DIR = GUIDE_DIR / "assets"
PDF_DIR = ROOT / "docs/promotional/pdf"
HTML_OUT = GUIDE_DIR / "index.html"
PDF_OUT = PDF_DIR / "reponomics-dashboard-map.pdf"
Notes = list[tuple[str, str, str]]


class SectionPage(TypedDict):
    title: str
    asset: str
    caption: str
    image_h: int
    notes: Notes


OVERVIEW_ITEMS = [
    (
        "Scope, controls, and summary",
        "Last updated, selected window, theme/export controls, the 8 published repos "
        "premise, and the first metrics overview.",
        "blue",
    ),
    (
        "Lead story and next moves",
        "A focused article carousel plus queue, both generated from the same rules-based "
        "prompts that connect metrics to repo context.",
        "green",
    ),
    (
        "Opportunity map",
        "Attention on the x-axis, downstream growth on the y-axis, and clone activity as "
        "mark size.",
        "gold",
    ),
    (
        "Code activity ribbon",
        "Commit and release clusters sit near the traffic timeline without implying branch "
        "topology. Markers focus a repo when the cluster belongs to one repo.",
        "blue",
    ),
    (
        "Readiness queue",
        "Community-health checks translated into practical setup fixes for the visible "
        "published repos.",
        "green",
    ),
    (
        "Growth model",
        "Attention, interest, and adoption cards summarize the path from visibility to "
        "downstream project response.",
        "gold",
    ),
    (
        "Repo strip and momentum",
        "Published repo chips focus or compare the 8 selected repos; momentum summarizes "
        "streaks and notable days.",
        "blue",
    ),
    (
        "Tables",
        "Sortable referrer, path, and repository detail surfaces for source inspection.",
        "green",
    ),
]


SECTION_PAGES: list[SectionPage] = [
    {
        "title": "Lead Story and Next Moves",
        "asset": "next-moves.png",
        "caption": (
            "The focused article creates the first read; the queue preserves the practical "
            "next-move list for scanning and repo focus."
        ),
        "image_h": 348,
        "notes": [
            (
                "Purpose",
                "Create an above-the-fold story without inventing analysis: the lead card "
                "reframes existing rules-based prompts as a focused read.",
                "green",
            ),
            (
                "Carousel",
                "Story tabs and arrow controls rotate through the strongest prompts for the "
                "selected window.",
                "blue",
            ),
            (
                "Affordance",
                "Lead buttons and queue cards focus the associated repo across the dashboard.",
                "gold",
            ),
            (
                "Use case",
                "Useful for flat or mixed windows because it emphasizes what to do next, not "
                "only what already spiked.",
                "green",
            ),
        ],
    },
    {
        "title": "Opportunity Map",
        "asset": "relationship-visuals.png",
        "caption": "Clustered demo data now uses smaller marks so labels and quadrants stay readable.",
        "image_h": 344,
        "notes": [
            (
                "Axes",
                "Right means more attention; up means more downstream growth from stars, "
                "forks, and subscribers.",
                "blue",
            ),
            (
                "Bubble size",
                "Size follows clone activity. The scale is compact so crowded portfolios "
                "still read cleanly.",
                "green",
            ),
            (
                "Quadrants",
                "Labels suggest practical recipes such as clarify next step or amplify.",
                "gold",
            ),
            (
                "Affordance",
                "Points and right-side notes focus the repo. Hover/title text carries exact "
                "values.",
                "blue",
            ),
        ],
    },
    {
        "title": "Code Activity Ribbon",
        "asset": "code-event-graph.png",
        "caption": "A low-noise event layer for spotting traffic-adjacent codebase activity.",
        "image_h": 348,
        "notes": [
            (
                "Purpose",
                "Bring default-branch commits and releases into the same time window as "
                "traffic, so maintainers can inspect temporal adjacency.",
                "green",
            ),
            (
                "Encoding",
                "Daily clusters aggregate commits and releases; releases use the stronger "
                "diamond marker.",
                "blue",
            ),
            (
                "Nearby views",
                "Tooltips and log items show nearby traffic counts as context for follow-up.",
                "gold",
            ),
            (
                "Affordance",
                "Single-repo clusters and log rows focus the repo inside the dashboard; "
                "multi-repo clusters stay as contextual hover targets.",
                "green",
            ),
        ],
    },
    {
        "title": "Readiness Queue",
        "asset": "readiness-queue.png",
        "caption": "A compact path from current attention to public-facing setup improvements.",
        "image_h": 190,
        "notes": [
            (
                "Purpose",
                "Convert attention into practical maintenance actions: README, license, "
                "contributing guide, templates, and conduct files.",
                "green",
            ),
            (
                "Score",
                "The score uses known community-health checks and reports visible coverage.",
                "blue",
            ),
            (
                "Priority",
                "Repos with setup gaps and current views plus clones rise in the queue.",
                "gold",
            ),
            (
                "Affordance",
                "Fix cards focus the repo and make the next maintenance step explicit.",
                "green",
            ),
        ],
    },
    {
        "title": "Tables and Source Inspection",
        "asset": "tables.png",
        "caption": "Use the tables when you need the underlying rows behind a visual or prompt.",
        "image_h": 340,
        "notes": [
            (
                "Referrers",
                "Shows where attention came from in the selected window; column headers sort "
                "the table.",
                "blue",
            ),
            (
                "Popular paths",
                "Useful for spotting docs, release notes, or entry pages that deserve a "
                "clearer next step.",
                "green",
            ),
            (
                "Repositories",
                "Detailed per-repo metrics backstop the heuristic sections with raw values.",
                "gold",
            ),
            (
                "Mobile behavior",
                "Wide tables scroll inside the table area so the page layout remains stable.",
                "green",
            ),
        ],
    },
]


def require_module(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        msg = (
            f"Missing optional guide dependency {name!r}. Run with a Python environment that "
            "has reportlab and Pillow installed, or use the Codex bundled PDF runtime."
        )
        raise SystemExit(msg) from exc


def validate_assets() -> None:
    required = {
        "full-page.png",
        "top-dashboard.png",
        "repo-selection.png",
        *(str(page["asset"]) for page in SECTION_PAGES),
    }
    missing = sorted(path for path in required if not (ASSET_DIR / path).exists())
    if missing:
        raise SystemExit("Missing dashboard guide asset(s): " + ", ".join(missing))


def color_value(name: str) -> str:
    return {
        "blue": "#6bb8ff",
        "green": "#4fc8a5",
        "gold": "#d6a84b",
    }.get(name, "#4fc8a5")


def clean_generated_text(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()) + "\n"


def build_html() -> None:
    GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    sections_html = "\n".join(
        section_html(page["title"], page["asset"], page["caption"], page["notes"])
        for page in SECTION_PAGES
    )
    overview_html = "\n".join(
        f"""
        <li style="--item-color: {color_value(color)}">
          <span class="marker">{idx}</span>
          <div>
            <h3>{html.escape(title)}</h3>
            <p>{html.escape(body)}</p>
          </div>
        </li>
        """
        for idx, (title, body, color) in enumerate(OVERVIEW_ITEMS, 1)
    )
    HTML_OUT.write_text(
        clean_generated_text(
            f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reponomics Dashboard Map</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1118;
      --panel: #111a24;
      --panel-2: #162230;
      --border: #29384a;
      --text: #e6edf5;
      --muted: #9aa8ba;
      --dim: #748397;
      --green: #4fc8a5;
      --blue: #6bb8ff;
      --gold: #d6a84b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 18% 0%, rgba(79, 200, 165, 0.11), transparent 32rem),
        radial-gradient(circle at 82% 22%, rgba(107, 184, 255, 0.12), transparent 34rem),
        var(--bg);
      color: var(--text);
      font: 15px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    a {{ color: var(--blue); }}
    .page {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 56px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 24px;
      align-items: end;
      padding: 22px 0 26px;
      border-bottom: 1px solid var(--border);
    }}
    .eyebrow {{
      color: var(--green);
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.09em;
      text-transform: uppercase;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ margin-top: 6px; font-size: clamp(2.2rem, 6vw, 4.8rem); line-height: 0.94; }}
    .lede {{ max-width: 42rem; margin-top: 14px; color: var(--muted); font-size: 1.05rem; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; }}
    .button {{
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      padding: 9px 12px;
      text-decoration: none;
      font-weight: 700;
    }}
    .map-grid {{
      display: grid;
      grid-template-columns: minmax(12rem, 0.34fr) minmax(0, 1fr);
      gap: 22px;
      margin-top: 26px;
    }}
    .screen-card, .legend-card, .section {{
      border: 1px solid var(--border);
      border-radius: 10px;
      background:
        linear-gradient(135deg, rgba(255,255,255,0.035), transparent 42%),
        var(--panel);
      box-shadow: 0 22px 60px rgba(0,0,0,0.22);
    }}
    .screen-card {{ padding: 14px; }}
    .screen-card img, .section-shot img {{
      display: block;
      width: 100%;
      height: auto;
      border-radius: 7px;
      border: 1px solid rgba(41,56,74,0.7);
    }}
    .legend-card {{ padding: 18px; }}
    .legend-card h2 {{ font-size: 1rem; margin-bottom: 14px; }}
    .overview-list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }}
    .overview-list li {{ display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: start; }}
    .marker {{
      display: grid;
      place-items: center;
      width: 26px;
      height: 26px;
      border-radius: 999px;
      background: var(--item-color);
      color: var(--bg);
      font-weight: 900;
      font-size: 0.8rem;
    }}
    .overview-list h3 {{ color: var(--item-color); font-size: 0.92rem; }}
    .overview-list p {{ color: var(--muted); font-size: 0.88rem; }}
    .section {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(16rem, 0.34fr);
      gap: 22px;
      margin-top: 28px;
      padding: 18px;
    }}
    .section h2 {{ font-size: 1.45rem; margin-bottom: 12px; }}
    .section-shot p {{ color: var(--dim); font-size: 0.85rem; margin-top: 10px; }}
    .notes {{
      border: 1px solid rgba(41,56,74,0.75);
      border-radius: 8px;
      background: var(--panel-2);
      padding: 16px;
      align-self: start;
    }}
    .notes h3 {{ margin-bottom: 14px; font-size: 1rem; }}
    .note {{ margin-top: 14px; }}
    .note:first-of-type {{ margin-top: 0; }}
    .note strong {{ display: block; color: var(--note-color); font-size: 0.86rem; }}
    .note p {{ color: var(--muted); font-size: 0.9rem; }}
    footer {{ color: var(--dim); margin-top: 32px; font-size: 0.8rem; }}
    @media (max-width: 850px) {{
      .hero, .map-grid, .section {{ grid-template-columns: 1fr; }}
      .actions {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div>
        <div class="eyebrow">Reader guide</div>
        <h1>Dashboard Map</h1>
        <p class="lede">A concise visual guide to the Reponomics dashboard: what each section is for, how the lead story connects metrics to practical repo events, and what is interactive in the demo.</p>
      </div>
      <nav class="actions" aria-label="Guide actions">
        <a class="button" href="../pdf/reponomics-dashboard-map.pdf">Open PDF</a>
        <a class="button" href="assets/full-page.png">Full screenshot</a>
      </nav>
    </header>

    <section class="map-grid" aria-labelledby="overview-title">
      <figure class="screen-card">
        <img src="assets/full-page.png" alt="Full dashboard screenshot">
      </figure>
      <div class="legend-card">
        <h2 id="overview-title">How the page is organized</h2>
        <ol class="overview-list">
          {overview_html}
        </ol>
      </div>
    </section>

    <section class="section" aria-labelledby="scope-title">
      <div class="section-shot">
        <h2 id="scope-title">Scope, Controls, Summary, and Published Repos</h2>
        <img src="assets/top-dashboard.png" alt="Dashboard header and controls">
        <img src="assets/repo-selection.png" alt="Published repository selection strip" style="margin-top: 14px">
        <p>The dashboard renders the selected publication subset, even when collection includes more repos.</p>
      </div>
      <aside class="notes">
        <h3>Interaction model</h3>
        {notes_html([
            ("8 published repos", "Publication is scoped to the selected set.", "green"),
            ("Summary cards", "The first metrics strip anchors the lead story in visible counts before the user reads recommendations.", "blue"),
            ("Window and metric controls", "Changing the window or metric redraws charts, maps, tables, and recipes.", "gold"),
            ("Repo chips", "Click a published repo chip or card to focus it; modifier keys support compare-style selection where enabled.", "green"),
            ("Demo affordances", "Export, theme, sorting, and focus controls are functional in the static dashboard.", "green"),
        ])}
      </aside>
    </section>

    {sections_html}

    <footer>Reponomics dashboard guide - generated from local demo preview.</footer>
  </main>
</body>
</html>
""",
        ),
        encoding="utf-8",
    )


def notes_html(notes: list[tuple[str, str, str]]) -> str:
    return "\n".join(
        f"""
        <div class="note" style="--note-color: {color_value(color)}">
          <strong>{html.escape(title)}</strong>
          <p>{html.escape(body)}</p>
        </div>
        """
        for title, body, color in notes
    )


def section_html(title: str, asset: str, caption: str, notes: list[tuple[str, str, str]]) -> str:
    section_id = title.lower().replace(" ", "-").replace(",", "")
    return f"""
    <section class="section" aria-labelledby="{html.escape(section_id)}-title">
      <div class="section-shot">
        <h2 id="{html.escape(section_id)}-title">{html.escape(title)}</h2>
        <img src="assets/{html.escape(asset)}" alt="{html.escape(title)} screenshot">
        <p>{html.escape(caption)}</p>
      </div>
      <aside class="notes">
        <h3>What to look for</h3>
        {notes_html(notes)}
      </aside>
    </section>
    """


def build_pdf() -> None:
    pil_image = require_module("PIL.Image")
    reportlab_canvas = require_module("reportlab.pdfgen.canvas")
    reportlab_colors = require_module("reportlab.lib.colors")
    reportlab_pagesizes = require_module("reportlab.lib.pagesizes")
    reportlab_utils = require_module("reportlab.lib.utils")
    reportlab_metrics = require_module("reportlab.pdfbase.pdfmetrics")

    pdf_dir = PDF_OUT.parent
    pdf_dir.mkdir(parents=True, exist_ok=True)

    page_w, page_h = reportlab_pagesizes.landscape(reportlab_pagesizes.letter)
    margin = 36
    bg = reportlab_colors.HexColor("#0b1118")
    panel = reportlab_colors.HexColor("#111a24")
    panel_2 = reportlab_colors.HexColor("#162230")
    border = reportlab_colors.HexColor("#29384a")
    text = reportlab_colors.HexColor("#e6edf5")
    muted = reportlab_colors.HexColor("#9aa8ba")
    dim = reportlab_colors.HexColor("#748397")

    palette = {
        "blue": reportlab_colors.HexColor("#6bb8ff"),
        "green": reportlab_colors.HexColor("#4fc8a5"),
        "gold": reportlab_colors.HexColor("#d6a84b"),
    }
    pdf = reportlab_canvas.Canvas(str(PDF_OUT), pagesize=(page_w, page_h))
    pdf.setTitle("Reponomics Dashboard Map")
    pdf.setAuthor("Reponomics")
    page_no = 0

    def draw_footer() -> None:
        nonlocal page_no
        page_no += 1
        pdf.setStrokeColor(border)
        pdf.setLineWidth(0.5)
        pdf.line(margin, 24, page_w - margin, 24)
        pdf.setFillColor(dim)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(margin, 12, "Reponomics dashboard guide - generated from local demo preview")
        pdf.drawRightString(page_w - margin, 12, str(page_no))

    def new_page(title: str, eyebrow: str) -> None:
        pdf.setFillColor(bg)
        pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)
        pdf.setFillColor(palette["green"])
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(margin, page_h - 36, eyebrow.upper())
        pdf.setFillColor(text)
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawString(margin, page_h - 62, title)
        pdf.setStrokeColor(border)
        pdf.setLineWidth(0.7)
        pdf.line(margin, page_h - 78, page_w - margin, page_h - 78)

    def wrap_copy(copy: str, font: str, size: float, width: float) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in copy.split():
            candidate = word if not current else current + " " + word
            if reportlab_metrics.stringWidth(candidate, font, size) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
        if current:
            lines.append(current)
        return lines

    def paragraph(
        x: float,
        y: float,
        copy: str,
        *,
        width: float,
        size: float = 9,
        color: Any = muted,
        leading: float = 12,
        font: str = "Helvetica",
    ) -> float:
        pdf.setFillColor(color)
        pdf.setFont(font, size)
        for line in wrap_copy(copy, font, size, width):
            pdf.drawString(x, y, line)
            y -= leading
        return y

    def image_dims(path: Path) -> tuple[int, int]:
        with pil_image.open(path) as image:
            return image.size

    def draw_image_fit(path: Path, x: float, y: float, w: float, h: float) -> None:
        image_w, image_h = image_dims(path)
        scale = min(w / image_w, h / image_h)
        draw_w = image_w * scale
        draw_h = image_h * scale
        draw_x = x + (w - draw_w) / 2
        draw_y = y + (h - draw_h) / 2
        pdf.drawImage(
            reportlab_utils.ImageReader(str(path)),
            draw_x,
            draw_y,
            draw_w,
            draw_h,
            preserveAspectRatio=True,
            mask="auto",
        )
        pdf.setStrokeColor(border)
        pdf.setLineWidth(0.8)
        pdf.roundRect(x, y, w, h, 8, stroke=1, fill=0)

    def bullet_list(x: float, y: float, items: list[tuple[str, str, str]]) -> float:
        for label, body, color_name in items:
            pdf.setFillColor(palette[color_name])
            pdf.setFont("Helvetica-Bold", 8.5)
            pdf.drawString(x, y, label)
            y = paragraph(x + 10, y - 11, body, width=238, size=8.4, leading=10)
            y -= 5
        return y

    def notes_panel(items: list[tuple[str, str, str]]) -> None:
        pdf.setFillColor(panel)
        pdf.setStrokeColor(border)
        pdf.roundRect(520, 102, 236, 370, 10, fill=1, stroke=1)
        pdf.setFillColor(text)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(538, 448, "What to look for")
        bullet_list(538, 426, items)

    new_page("Dashboard Map", "reader guide")
    draw_image_fit(ASSET_DIR / "full-page.png", margin, 78, 150, 460)
    pdf.setFillColor(panel)
    pdf.setStrokeColor(border)
    pdf.roundRect(222, 78, 534, 460, 10, fill=1, stroke=1)
    pdf.setFillColor(text)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(244, 510, "How the page is organized")
    bullet_list(
        244,
        486,
        [
            (f"{idx}. {title}", body, color)
            for idx, (title, body, color) in enumerate(OVERVIEW_ITEMS, 1)
        ],
    )
    pdf.setFillColor(panel_2)
    pdf.setStrokeColor(border)
    pdf.roundRect(244, 110, 478, 48, 8, fill=1, stroke=1)
    pdf.setFillColor(palette["green"])
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(256, 141, "Reading model")
    paragraph(
        256,
        127,
        "The summary cards establish factual context; the lead story creates a focused "
        "read; the lower modules keep the evidence visible.",
        width=442,
        size=8,
        leading=10,
    )
    draw_footer()
    pdf.showPage()

    new_page("Scope, Controls, Summary, and Published Repos", "dashboard map")
    draw_image_fit(ASSET_DIR / "top-dashboard.png", margin, 338, 456, 150)
    draw_image_fit(ASSET_DIR / "repo-selection.png", margin, 258, 456, 52)
    notes_panel(
        [
            ("8 published repos", "Publication is scoped to the selected set.", "green"),
            (
                "Summary cards",
                "The first metrics strip anchors the lead story in visible counts before "
                "the user reads recommendations.",
                "blue",
            ),
            (
                "Window and metric controls",
                "Changing the window or metric redraws charts, maps, tables, and recipes.",
                "gold",
            ),
            (
                "Repo chips",
                "Click a published repo chip or card to focus it; modifier keys support "
                "compare-style selection where enabled.",
                "green",
            ),
            (
                "Demo affordances",
                "Export, theme, sorting, and focus controls are functional in the static dashboard.",
                "green",
            ),
        ]
    )
    draw_footer()
    pdf.showPage()

    for page in SECTION_PAGES:
        new_page(str(page["title"]), "section guide")
        draw_image_fit(ASSET_DIR / str(page["asset"]), margin, 112, 456, float(page["image_h"]))
        paragraph(margin, 100, str(page["caption"]), width=456, size=8, color=dim, leading=10)
        notes_panel(page["notes"])
        draw_footer()
        pdf.showPage()

    pdf.save()


def main() -> None:
    validate_assets()
    build_html()
    build_pdf()
    print(f"Wrote {HTML_OUT}")
    print(f"Wrote {PDF_OUT}")


if __name__ == "__main__":
    main()
