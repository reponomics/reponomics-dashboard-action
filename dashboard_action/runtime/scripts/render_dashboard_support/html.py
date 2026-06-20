"""HTML assembly for the generated dashboard pages."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping, TypedDict, cast

from render_dashboard_support.assets import load_asset
from render_dashboard_support.status import render_version_badges as _render_version_badges


DashboardData = dict[str, Any]
ExportManifest = dict[str, Any] | None


class StatValues(TypedDict):
    repo_count: str
    total_views: str
    total_uniques: str
    total_clones: str
    total_clone_uniques: str


class DemoUnlockMetadata(TypedDict):
    label: str
    key: str
    note: str
    button_label: str


DEMO_UNLOCK_METADATA_KEYS = frozenset(DemoUnlockMetadata.__annotations__)

ACTION_ROOT = Path(__file__).resolve().parents[4]
VENDORED_INTER_FONT_PATH = ACTION_ROOT / "vendor" / "inter" / "inter-latin-wght-normal.woff2"
VENDORED_MONO_FONT_PATH = (
    ACTION_ROOT / "vendor" / "jetbrains-mono" / "jetbrains-mono-latin-wght-normal.woff2"
)
PBKDF2_ITERATIONS = 600_000
BASE_STYLES = load_asset("base.css")
DASHBOARD_MODULE_ASSETS = (
    "dashboard/chart-adapter.js",
    "dashboard/state.js",
    "dashboard/data-provider.js",
    "dashboard/theme.js",
    "dashboard/format.js",
    "dashboard/selection.js",
    "dashboard/quality-calendar.js",
    "dashboard/series.js",
    "dashboard/momentum.js",
    "dashboard/chart-options.js",
    "dashboard/controls.js",
    "dashboard/charts.js",
    "dashboard/tables.js",
    "dashboard/controller.js",
    "dashboard/app.js",
    "dashboard/json-assets.js",
    "dashboard/secure-core.js",
    "dashboard/theme-preload.js",
    "dashboard/entry-public.js",
    "dashboard/entry-secure.js",
)
PUBLISHED_STYLESHEET_ASSETS = ("font-face.css", "base.css")
STANDALONE_BUNDLE_ASSETS = (
    "dashboard/chart-adapter.js",
    "dashboard/state.js",
    "dashboard/data-provider.js",
    "dashboard/theme.js",
    "dashboard/format.js",
    "dashboard/selection.js",
    "dashboard/quality-calendar.js",
    "dashboard/series.js",
    "dashboard/momentum.js",
    "dashboard/chart-options.js",
    "dashboard/controls.js",
    "dashboard/charts.js",
    "dashboard/tables.js",
    "dashboard/controller.js",
    "dashboard/app.js",
)
SECURE_STANDALONE_BUNDLE_ASSETS = (
    *STANDALONE_BUNDLE_ASSETS,
    "dashboard/secure-core.js",
)
THEME_PRELOAD_ASSET = "dashboard/theme-preload.js"
PUBLIC_ENTRY_ASSET = "dashboard/entry-public.js"
SECURE_ENTRY_ASSET = "dashboard/entry-secure.js"
SECURE_CORE_ASSET = "dashboard/secure-core.js"
PUBLISHED_DASHBOARD_DATA_ASSET = "dashboard-data.json"
PUBLISHED_ENCRYPTED_DASHBOARD_DATA_ASSET = "encrypted-dashboard-data.json"
PUBLISHED_EXPORT_MANIFEST_ASSET = "export-manifest.json"
PUBLISHED_FONT_ASSETS = (
    (VENDORED_INTER_FONT_PATH, "inter-latin-wght-normal.woff2"),
    (VENDORED_MONO_FONT_PATH, "jetbrains-mono-latin-wght-normal.woff2"),
)
DEMO_UNLOCK_STYLESHEET_ASSET = "demo-unlock.css"
DEMO_UNLOCK_STYLES = load_asset(DEMO_UNLOCK_STYLESHEET_ASSET)
PUBLISHED_META_CSP = "; ".join(
    [
        "default-src 'none'",
        "base-uri 'none'",
        "object-src 'none'",
        "script-src 'self'",
        "script-src-elem 'self'",
        "script-src-attr 'none'",
        "style-src 'self'",
        "style-src-elem 'self'",
        "style-src-attr 'none'",
        "font-src 'self'",
        "img-src 'self'",
        "connect-src 'self'",
        "media-src 'none'",
        "frame-src 'none'",
        "child-src 'none'",
        "worker-src 'none'",
        "manifest-src 'none'",
        "form-action 'none'",
    ]
)
HEADER_CSP = PUBLISHED_META_CSP + "; frame-ancestors 'none'"


def _font_face_rule(family: str, path: Path, weight_range: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"""
    @font-face {{
      font-family: '{family}';
      font-style: normal;
      font-weight: {weight_range};
      font-display: swap;
      src: url('data:font/woff2;base64,{data}') format('woff2');
    }}"""


def build_font_face_styles() -> str:
    """Return self-contained @font-face rules for vendored dashboard fonts."""
    return (
        _font_face_rule("Inter", VENDORED_INTER_FONT_PATH, "100 900")
        + "\n"
        + _font_face_rule("JetBrains Mono", VENDORED_MONO_FONT_PATH, "100 800")
    )


def build_dashboard_shell(
    updated_text: str,
    stat_values: StatValues,
    hidden: bool = False,
) -> str:
    """Build the shared dashboard markup used by plaintext and encrypted pages."""
    hidden_attr = ' class="dashboard-hidden"' if hidden else ""
    return f"""
  <div id="dashboard-app"{hidden_attr}>
    <div class="hero">
      <div class="hero-copy">
        <p class="tagline"><span class="pulse-dot" aria-hidden="true"></span><span>Traffic and growth data for your repos</span></p>
        <div class="brand-lockup">
          <h1 class="brand">reponomics<span class="accent">.</span></h1>
          <div class="brand-eyebrow">Dashboard</div>
        </div>
        <p class="updated" id="updated-text">{updated_text}</p>
{_render_version_badges()}
      </div>
      <div class="hero-toolbar">
        <div class="hero-toolbar-controls">
          <span class="status-badge active" id="activeBadge"></span>
          <span class="status-badge compare" id="compareBadge"></span>
          <button class="toolbar-button" id="clearSelectionBtn" type="button">Clear selection</button>
          <button class="toolbar-button" id="export-button" type="button" title="Download canonical retained CSV data as a ZIP file">Export to CSV</button>
          <button class="toolbar-button" id="export-hash-button" type="button" title="Copy SHA-256 digest for manual download verification">Copy SHA-256</button>
          <details class="export-verify-tip">
            <summary class="toolbar-button visible" title="How download verification works">Verification</summary>
            <div class="export-verify-popover" role="note">
              <p><strong>Automatic in-browser checks:</strong> on export, the dashboard verifies encrypted asset size + SHA-256, decrypts with your key, then verifies decrypted ZIP SHA-256 against this page's embedded <code>export-manifest</code> before download.</p>
              <p><strong>Optional manual verification:</strong> <code>Copy SHA-256</code> copies <code>&lt;sha256&gt;&nbsp;&nbsp;&lt;filename&gt;</code> for checksum-file format. Use <code>shasum -a 256 &lt;downloaded-file.zip&gt;</code> to compare manually, or save the copied line and run <code>shasum -a 256 -c &lt;checksums.txt&gt;</code>.</p>
            </div>
          </details>
          <button class="toolbar-button theme-toggle visible" id="themeToggle" type="button" aria-label="Toggle light/dark theme" title="Toggle theme">
            <span class="theme-icon" aria-hidden="true">◐</span>
            <span class="theme-label">Theme</span>
          </button>
        </div>
        <p class="auth-status" id="export-status" aria-live="polite" aria-atomic="true"></p>
      </div>
    </div>

    <div class="dashboard-notice-region" id="dashboard-notice-region" hidden aria-live="polite" aria-atomic="true"></div>

    <div class="growth-model-grid" aria-label="Repository growth model">
      <div class="card growth-stage">
        <div class="growth-stage-title">Attention</div>
        <div class="growth-stage-value" id="growthAttentionValue">0 / 0</div>
        <div class="growth-stage-context" id="growthAttentionContext">views / visitors in the selected window</div>
      </div>
      <div class="card growth-stage">
        <div class="growth-stage-title">Interest</div>
        <div class="growth-stage-value" id="growthInterestValue">+0 / +0</div>
        <div class="growth-stage-context" id="growthInterestContext">stars / watchers; current totals as context</div>
      </div>
      <div class="card growth-stage">
        <div class="growth-stage-title">Adoption</div>
        <div class="growth-stage-value" id="growthAdoptionValue">0 / +0</div>
        <div class="growth-stage-context" id="growthAdoptionContext">clones / forks; current total as context</div>
      </div>
    </div>

    <div class="stats-grid" id="stats-grid">
      <div class="card stat-card" data-metric="repos">
        <div class="stat-head">
          <span class="stat-label">Tracked Repos</span>
          <span class="stat-delta hidden" id="deltaRepos"></span>
        </div>
        <div class="stat-value" id="statRepos">{stat_values['repo_count']}</div>
        <svg class="stat-spark" id="sparkRepos" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true"></svg>
      </div>
      <div class="card stat-card" data-metric="views" title="Total page views across tracked repos">
        <div class="stat-head">
          <span class="stat-label">Attention: Views</span>
          <span class="stat-delta hidden" id="deltaViews"></span>
        </div>
        <div class="stat-value" id="statViews">{stat_values['total_views']}</div>
        <svg class="stat-spark" id="sparkViews" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true"></svg>
      </div>
      <div class="card stat-card" data-metric="uniques" title="Unique visitors — distinct viewers (GitHub deduplicates by IP per day)">
        <div class="stat-head">
          <span class="stat-label">Attention: Visitors</span>
          <span class="stat-delta hidden" id="deltaUniques"></span>
        </div>
        <div class="stat-value" id="statUniques">{stat_values['total_uniques']}</div>
        <svg class="stat-spark" id="sparkUniques" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true"></svg>
      </div>
      <div class="card stat-card" data-metric="clones" title="Total git-clone operations across tracked repos">
        <div class="stat-head">
          <span class="stat-label">Adoption: Clones</span>
          <span class="stat-delta hidden" id="deltaClones"></span>
        </div>
        <div class="stat-value" id="statClones">{stat_values['total_clones']}</div>
        <svg class="stat-spark" id="sparkClones" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true"></svg>
      </div>
      <div class="card stat-card" data-metric="cloners" title="Unique cloners — distinct clients that ran git clone (deduplicated by GitHub)">
        <div class="stat-head">
          <span class="stat-label">Adoption: Cloners</span>
          <span class="stat-delta hidden" id="deltaCloneUniques"></span>
        </div>
        <div class="stat-value" id="statCloneUniques">{stat_values['total_clone_uniques']}</div>
        <svg class="stat-spark" id="sparkCloneUniques" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true"></svg>
      </div>
    </div>

    <div class="compare-summary" id="compare-summary"></div>

    <div class="card controls-card">
      <div class="controls-main">
        <div class="controls-group">
          <div class="controls-label">Window</div>
          <div class="segmented-control">
            <button class="segmented-button" data-window="7" type="button">7d</button>
            <button class="segmented-button" data-window="14" type="button">14d</button>
            <button class="segmented-button" data-window="30" type="button">30d</button>
            <button class="segmented-button" data-window="90" type="button">90d</button>
            <button class="segmented-button" data-window="all" type="button">All</button>
          </div>
          <p class="controls-hint" id="rangeHint">Choose a trailing collected-day window, or All data since collection began.</p>
        </div>
        <div class="controls-group">
          <div class="controls-label">Visibility threshold</div>
          <div class="threshold-control">
            <input class="threshold-input" id="thresholdInput" type="number" min="0" step="1" inputmode="numeric" value="1" aria-label="Minimum combined views and clones for a repo to appear">
            <span class="controls-hint">Hide repos with fewer than <span class="threshold-value" id="thresholdValue">1</span> combined views + clones in the selected window.</span>
          </div>
        </div>
      </div>
      <div class="calendar-panel" id="calendar-panel">
        <div class="controls-label">Collection health</div>
        <div class="calendar-head">
          <button class="calendar-nav" id="calendarPrevBtn" type="button" aria-label="Show previous month">◀</button>
          <div class="calendar-month-label" id="calendarMonthLabel">Month</div>
          <button class="calendar-nav" id="calendarNextBtn" type="button" aria-label="Show next month">▶</button>
        </div>
        <div class="calendar-weekdays" aria-hidden="true">
          <span class="calendar-weekday">Mon</span>
          <span class="calendar-weekday">Tue</span>
          <span class="calendar-weekday">Wed</span>
          <span class="calendar-weekday">Thu</span>
          <span class="calendar-weekday">Fri</span>
          <span class="calendar-weekday">Sat</span>
          <span class="calendar-weekday">Sun</span>
        </div>
        <div class="calendar-grid" id="calendarGrid"></div>
        <p class="calendar-hint" id="calendarHint">Collection status per day in the selected window.</p>
        <p class="calendar-day-detail" id="calendarDayDetail" aria-live="polite">Hover or focus a day to inspect collection details.</p>
      </div>
    </div>

    <div class="card repo-strip-card" id="repo-strip-card">
      <span class="repo-strip-label">Repos</span>
      <div class="repo-strip" id="repo-strip" role="toolbar" aria-label="Repository selector"></div>
      <span class="repo-strip-hint" id="repo-strip-hint">Click to focus · ⌘/Ctrl-click to compare</span>
    </div>

    <div class="chart-grid">
      <div class="card">
        <div class="section-header">
          <div class="section-copy">
            <h2 id="dailyChartTitle">Traffic Overview</h2>
            <p class="click-hint">Click a repo to focus. Toggle metrics, or ⌘/Ctrl-click repos to compare.</p>
          </div>
          <div class="section-actions">
            <div class="metric-tabs" role="tablist" aria-label="Metric">
              <button class="metric-tab" data-metric="views" role="tab" type="button" title="Total page views"><span class="swatch"></span>Views</button>
              <button class="metric-tab" data-metric="uniques" role="tab" type="button" title="Unique visitors — distinct viewers per day"><span class="swatch"></span>Visitors</button>
              <button class="metric-tab" data-metric="clones" role="tab" type="button" title="Total git-clone operations"><span class="swatch"></span>Clones</button>
              <button class="metric-tab" data-metric="cloners" role="tab" type="button" title="Unique cloners — distinct clients that ran git clone"><span class="swatch"></span>Unique Clones</button>
              <button class="metric-tab" data-metric="stars" role="tab" type="button" title="Star delta in the selected window"><span class="swatch"></span>Stars</button>
              <button class="metric-tab" data-metric="subscribers" role="tab" type="button" title="Watcher delta in the selected window"><span class="swatch"></span>Watchers</button>
              <button class="metric-tab" data-metric="forks" role="tab" type="button" title="Fork delta in the selected window"><span class="swatch"></span>Forks</button>
            </div>
          </div>
        </div>
        <div class="chart-container">
          <canvas id="dailyChart" role="img" aria-label="Daily traffic line chart"></canvas>
        </div>
      </div>

      <div class="card" id="weekday-card">
        <div class="section-header">
          <div class="section-copy">
            <h2 id="weekdayChartTitle">Weekday Rhythm</h2>
            <p class="click-hint">Average daily <span id="weekdayMetricLabel">views</span> by weekday for the current scope.</p>
          </div>
        </div>
        <div class="chart-container">
          <canvas id="weekdayChart" role="img" aria-label="Average traffic by weekday bar chart"></canvas>
        </div>
      </div>
    </div>

    <div class="card" id="stacked-card">
      <div class="section-header">
        <div class="section-copy">
          <h2 id="stackedChartTitle">By repository</h2>
          <p class="click-hint">Stacked when viewing all repos; lined up when focusing or comparing. Follows the metric tab above.</p>
        </div>
      </div>
      <div class="chart-container tall">
        <canvas id="stackedChart" role="img" aria-label="Per-repository stacked or compared traffic chart"></canvas>
      </div>
    </div>

    <div class="section-grid full" id="momentum-section">
      <div class="card momentum-card">
        <div class="momentum-grid" id="momentum-grid"></div>
      </div>
    </div>

    <div class="section-grid full">
      <div class="card">
        <div class="section-header">
          <div class="section-copy">
            <h2>What's moving</h2>
            <p class="click-hint">Auto-detected traffic, conversion, and growth anomalies. Click a card to focus on the repo.</p>
          </div>
        </div>
        <div id="insights-list"></div>
      </div>
    </div>

    <div class="section-grid">
      <div class="card">
        <div class="section-header">
          <div class="section-copy">
            <h2>Top referrers</h2>
            <p class="click-hint">Where the traffic is coming from. Click a column to sort.</p>
          </div>
        </div>
        <div id="referrer-table"></div>
      </div>
      <div class="card">
        <div class="section-header">
          <div class="section-copy">
            <h2>Popular content</h2>
            <p class="click-hint">Latest top-path rows, separated by repository.</p>
          </div>
        </div>
        <div id="paths-table"></div>
      </div>
    </div>

    <div class="card" id="repo-section">
      <div class="section-header">
        <div class="section-copy">
          <h2>Repositories</h2>
          <p class="click-hint">Click a row to focus on one repo. Use checkboxes to compare multiple repos at the bottom of the dashboard.</p>
        </div>
      </div>
      <div id="repo-table"></div>
    </div>
  </div>
"""


def csp_hash(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def build_csp(
    style_blocks: list[str],
    script_blocks: list[str],
    *,
    allow_font_data: bool = True,
) -> str:
    style_sources = ["'self'", *[csp_hash(block) for block in style_blocks if block]]
    script_sources = ["'self'", *[csp_hash(block) for block in script_blocks if block]]
    font_sources = ["'self'", *(["data:"] if allow_font_data else [])]
    directives = [
        "default-src 'self'",
        "script-src " + " ".join(script_sources),
        "style-src " + " ".join(style_sources),
        "font-src " + " ".join(font_sources),
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
    ]
    return "; ".join(directives)


def published_meta_csp() -> str:
    """Return the CSP enforced by generated hosted dashboard HTML."""
    return PUBLISHED_META_CSP


def theme_bootstrap_js() -> str:
    return """(function() {
      try {
        var saved = localStorage.getItem('reponomics-theme');
        var theme = (saved === 'light' || saved === 'dark')
          ? saved
          : (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
        if (theme === 'light') document.documentElement.setAttribute('data-theme', 'light');
      } catch (e) { /* ignore */ }
    })();"""


def _asset_path(name: str) -> str:
    return f"assets/{name}"


def _json_asset_meta(name: str, asset_name: str) -> str:
    return f'<meta name="{name}" content="{html.escape(_asset_path(asset_name), quote=True)}">'


def _published_head_assets(
    chart_loader: str,
    encrypted: bool,
    *,
    include_demo_styles: bool = False,
) -> str:
    entry_asset = SECURE_ENTRY_ASSET if encrypted else PUBLIC_ENTRY_ASSET
    stylesheets = (
        *PUBLISHED_STYLESHEET_ASSETS,
        *((DEMO_UNLOCK_STYLESHEET_ASSET,) if include_demo_styles else ()),
    )
    tags = [
        f'  <link rel="stylesheet" href="{_asset_path(name)}">'
        for name in stylesheets
    ]
    tags.append(f"  {chart_loader}")
    tags.append(f'  <script type="module" src="{_asset_path(THEME_PRELOAD_ASSET)}"></script>')
    tags.append(f'  <script type="module" src="{_asset_path(entry_asset)}"></script>')
    return "\n".join(tags)


def _published_runtime_asset_content(name: str) -> str:
    if name in {SECURE_ENTRY_ASSET, SECURE_CORE_ASSET}:
        return load_asset(name).replace("__PBKDF2_ITERATIONS__", str(PBKDF2_ITERATIONS))
    return load_asset(name)


def published_runtime_assets(encrypted: bool) -> tuple[str, ...]:
    return DASHBOARD_MODULE_ASSETS


def _standalone_module_content(name: str) -> str:
    source = _published_runtime_asset_content(name)
    source = re.sub(r"^import .*$\n?", "", source, flags=re.MULTILINE)
    source = re.sub(r"^export function ", "function ", source, flags=re.MULTILINE)
    source = re.sub(r"^export const ", "const ", source, flags=re.MULTILINE)
    source = re.sub(r"^export \{[^}]+\};?\n?", "", source, flags=re.MULTILINE)
    return source.strip()


def _public_runtime_js() -> str:
    bootstrap = """
const plaintextDashboardData = JSON.parse(
  document.getElementById('plaintext-dashboard-data').textContent
);
createDashboardApp().renderDashboard(plaintextDashboardData);
"""
    return "\n\n".join(
        [*(_standalone_module_content(name) for name in STANDALONE_BUNDLE_ASSETS), bootstrap]
    )


def _secure_runtime_js() -> str:
    source = _published_runtime_asset_content(SECURE_ENTRY_ASSET)
    source = re.sub(r"^import .*$\n?", "", source, flags=re.MULTILINE)
    json_loader_pattern = (
        r"const encryptedDashboardData = await readJsonAsset\(\n.*?\n\);\n"
        + r"const exportManifestPayload = await readJsonAsset\(\n.*?\n\);\n"
    )
    source = re.sub(
        json_loader_pattern,
        """function readEmbeddedJson(id) {
  return JSON.parse(document.getElementById(id).textContent || 'null');
}
const encryptedDashboardData = readEmbeddedJson('encrypted-dashboard-data');
const exportManifestPayload = readEmbeddedJson('export-manifest');
""",
        source,
        flags=re.DOTALL,
    )
    return "\n\n".join(
        [
            *(_standalone_module_content(name) for name in SECURE_STANDALONE_BUNDLE_ASSETS),
            source.strip(),
        ]
    )


APP_RUNTIME_JS = _public_runtime_js()
SECURE_RUNTIME_JS = _secure_runtime_js()


def copy_published_dashboard_assets(output_path: str, *, encrypted: bool) -> None:
    """Copy first-party dashboard assets beside a generated published page."""
    asset_dir = Path(output_path).parent / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    for asset_name in (
        *PUBLISHED_STYLESHEET_ASSETS,
        DEMO_UNLOCK_STYLESHEET_ASSET,
        *published_runtime_assets(encrypted),
    ):
        (asset_dir / asset_name).parent.mkdir(parents=True, exist_ok=True)
        (asset_dir / asset_name).write_text(
            _published_runtime_asset_content(asset_name)
            if asset_name.endswith(".js")
            else load_asset(asset_name),
            encoding="utf-8",
        )

    for source, filename in PUBLISHED_FONT_ASSETS:
        shutil.copyfile(source, asset_dir / filename)


def write_published_json_asset(output_path: str, asset_name: str, value: object) -> None:
    """Write generated hosted dashboard JSON next to static dashboard assets."""
    asset_path = Path(output_path).parent / _asset_path(asset_name)
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")


def wrap_html(
    body: str,
    chart_loader: str,
    runtime_js: str,
    extra_head: str = "",
    body_attributes: str = "",
    inline_chart_js: str = "",
    extra_csp_scripts: list[str] | None = None,
    extra_styles: str = "",
    external_assets: bool = False,
    encrypted_assets: bool = False,
) -> str:
    """Wrap page markup in the shared HTML shell."""
    body_attribute_text = f" {body_attributes}" if body_attributes else ""
    style_content = "" if external_assets else f"{build_font_face_styles()}\n{BASE_STYLES}{extra_styles}"
    theme_js = theme_bootstrap_js()
    script_blocks = [*(extra_csp_scripts or [])]
    if external_assets:
        head_assets = _published_head_assets(
            chart_loader,
            encrypted_assets,
            include_demo_styles=bool(extra_styles),
        )
        tail_script = ""
        style_tag = ""
        csp_value = published_meta_csp()
    else:
        head_assets = f"  {chart_loader}\n  <style>{style_content}</style>\n  <script>{theme_js}</script>"
        tail_script = f"\n  <script>{runtime_js}</script>"
        style_tag = ""
        csp_value = build_csp(
            [style_content],
            [inline_chart_js, theme_js, *script_blocks, runtime_js],
        )
    csp = html.escape(csp_value, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reponomics Dashboard</title>
  <meta http-equiv="Content-Security-Policy" content="{csp}">
  {extra_head}
{head_assets}{style_tag}
</head>
<body{body_attribute_text}>
{body}

  <footer>
    <div class="footer-line footer-promises">
      <span><b>Free</b> for any user</span>
      <span class="dot">·</span>
      <span><b>No third parties</b></span>
      <span class="dot">·</span>
      <span>Rich <b>personalized insights</b></span>
      <span class="dot">·</span>
      <span>Private hosting on <b>GitHub Pages</b></span>
    </div>
    <div class="footer-line">
      <span>Built with</span>
      <a href="https://github.com/reponomics/reponomics-dashboard">Reponomics</a>
      <span class="dot">·</span>
      <span>Made for indie hackers shipping across many repos</span>
    </div>
  </footer>
{tail_script}
</body>
</html>
"""


def build_public_html(
    dashboard_data: DashboardData,
    chart_loader: str,
    inline_chart_js: str = "",
    *,
    external_assets: bool = False,
) -> str:
    """Build the standard published dashboard HTML."""
    summary = dashboard_data["summary"]
    totals = summary["totals"]
    shell = build_dashboard_shell(
        (
            f"Last updated: {summary['generated_at']} | " +
            f"Tracking {totals['repo_count']} repositories | " +
            f"{totals['days_tracked']} days of data"
        ),
        {
            "repo_count": f"{totals['repo_count']:,}",
            "total_views": f"{totals['total_views']:,}",
            "total_uniques": f"{totals['total_uniques']:,}",
            "total_clones": f"{totals['total_clones']:,}",
            "total_clone_uniques": f"{totals['total_clone_uniques']:,}",
        },
    )
    dashboard_data_json = json.dumps(dashboard_data, separators=(",", ":"))
    if external_assets:
        body = shell
        extra_head = _json_asset_meta(
            "reponomics-dashboard-data",
            PUBLISHED_DASHBOARD_DATA_ASSET,
        )
        extra_csp_scripts: list[str] = []
    else:
        body = (
            shell
            + "\n  <script id=\"plaintext-dashboard-data\" type=\"application/json\">"
            + dashboard_data_json
            + "</script>\n"
        )
        extra_head = ""
        extra_csp_scripts = [dashboard_data_json]
    return wrap_html(
        body,
        chart_loader,
        _public_runtime_js(),
        extra_head=extra_head,
        inline_chart_js=inline_chart_js,
        extra_csp_scripts=extra_csp_scripts,
        external_assets=external_assets,
    )


def _build_demo_unlock_panel(demo_unlock: DemoUnlockMetadata | None) -> str:
    if demo_unlock is None:
        return ""
    metadata = _validate_demo_unlock_metadata(demo_unlock)
    label = html.escape(metadata["label"])
    key = html.escape(metadata["key"])
    note = html.escape(metadata["note"])
    button_label = html.escape(metadata["button_label"])
    return f"""
          <div class="demo-unlock-panel" id="demo-unlock-panel">
            <div class="demo-unlock-copy">
              <div class="demo-unlock-label">{label}</div>
              <p class="demo-unlock-note">{note}</p>
            </div>
            <div class="demo-unlock-key-row">
              <code class="demo-unlock-key" id="demo-unlock-key">{key}</code>
              <button class="demo-unlock-button" id="demo-unlock-button" type="button">{button_label}</button>
            </div>
          </div>
"""


def _validate_demo_unlock_metadata(demo_unlock: object) -> DemoUnlockMetadata:
    if not isinstance(demo_unlock, Mapping):
        raise TypeError("demo_unlock must be a mapping")
    if set(demo_unlock) != DEMO_UNLOCK_METADATA_KEYS:
        expected = ", ".join(sorted(DEMO_UNLOCK_METADATA_KEYS))
        raise ValueError(f"demo_unlock must contain exactly these keys: {expected}")
    if not all(isinstance(demo_unlock[key], str) for key in DEMO_UNLOCK_METADATA_KEYS):
        raise TypeError("demo_unlock values must be strings")
    return cast(DemoUnlockMetadata, demo_unlock)


def build_encrypted_html(
    encrypted_dashboard_data: DashboardData,
    chart_loader: str,
    export_manifest: ExportManifest,
    *,
    demo_unlock: DemoUnlockMetadata | None = None,
    external_assets: bool = False,
) -> str:
    """Build the encrypted published dashboard HTML."""
    demo_unlock_panel = _build_demo_unlock_panel(demo_unlock)
    auth_card = f"""
  <div id="auth-shell">
    <div class="auth-page">
      <div class="auth-wrap">
        <div class="hero">
          <div class="hero-copy auth-hero">
            <div class="auth-hero-head">
              <div class="brand-lockup">
                <h1 class="brand">reponomics<span class="accent">.</span></h1>
                <div class="brand-eyebrow">Dashboard</div>
              </div>
              <button
                class="auth-theme-toggle theme-toggle"
                id="auth-theme-toggle"
                type="button"
                aria-label="Toggle light/dark theme"
                aria-pressed="false"
                title="Toggle theme"
              >
                <span class="theme-icon" aria-hidden="true">◐</span>
                <span class="theme-label">Theme</span>
              </button>
            </div>
            <p class="sub">
              Encrypted Pages mode for private growth analytics. The dashboard
              data is encrypted with your key and decrypted locally &mdash;
              nothing leaves your browser.
            </p>
          </div>
        </div>

        <div class="card auth-card" id="unlock-card">
          <div class="auth-card-heading">
            <span class="auth-card-icon" aria-hidden="true">
              <svg viewBox="0 0 32 32" width="22" height="22" focusable="false">
                <g transform="rotate(45 16 16)">
                  <rect x="6" y="6" width="20" height="20" rx="4.5" stroke="currentColor" stroke-width="2.5" fill="none"/>
                </g>
                <path d="M9 19 L13 15 L17 18 L23 11" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
              </svg>
            </span>
            <div class="auth-card-copy">
              <h2 class="auth-card-title">Unlock Dashboard</h2>
              <p class="auth-card-sub">
                Enter your dashboard key to decrypt the latest dashboard snapshot
                in this browser.
              </p>
	            </div>
	          </div>

{demo_unlock_panel}

	          <form class="auth-form" id="unlock-form" autocomplete="off">
            <label class="auth-hidden-username" aria-hidden="true">
              <input
                id="dashboard-username"
                type="text"
                name="username"
                autocomplete="username"
                value="encrypted-dashboard"
                tabindex="-1"
              >
            </label>
            <div class="auth-input-wrap">
              <input
                class="auth-input"
                id="dashboard-key"
                type="password"
                name="dashboard-key"
                autocomplete="current-password"
                placeholder="Enter dashboard key"
                aria-label="Dashboard key"
              >
            </div>
            <button class="auth-button" id="unlock-button" type="submit">Unlock</button>
          </form>

          <div class="auth-status" id="unlock-status" aria-live="polite"></div>

          <div class="auth-meta">
            <span class="meta-item"><span class="glyph"></span>AES-GCM &middot; PBKDF2-SHA256 &middot; {PBKDF2_ITERATIONS:,} iterations</span>
            <span class="meta-item"><span class="glyph"></span>Decryption is strictly client-side</span>
          </div>

          <div class="auth-help-row">
            <a href="https://github.com/reponomics">Forgot your password?</a>
          </div>
        </div>

        <footer class="auth-footer">
          <div class="footer-line">
            <span>Built with</span>
            <a class="brand-name" href="https://github.com/reponomics">Reponomics</a>
            <span class="dot">&middot;</span>
            <span>self-hosted, no trackers, no cost</span>
          </div>
          <div class="footer-subline">Made for indie hackers shipping across many repos</div>
        </footer>
      </div>
    </div>
  </div>
"""
    shell = build_dashboard_shell(
        "Dashboard locked until the dashboard key is entered.",
        {
            "repo_count": "Locked",
            "total_views": "Locked",
            "total_uniques": "Locked",
            "total_clones": "Locked",
            "total_clone_uniques": "Locked",
        },
        hidden=True,
    )
    encrypted_dashboard_data_json = json.dumps(
        encrypted_dashboard_data, separators=(",", ":")
    )
    export_manifest_json = json.dumps(export_manifest, separators=(",", ":"))
    extra_head_parts = ['<meta name="robots" content="noindex, nofollow">']
    if external_assets:
        body = auth_card + shell
        extra_head_parts.extend(
            [
                _json_asset_meta(
                    "reponomics-encrypted-dashboard-data",
                    PUBLISHED_ENCRYPTED_DASHBOARD_DATA_ASSET,
                ),
                _json_asset_meta(
                    "reponomics-export-manifest",
                    PUBLISHED_EXPORT_MANIFEST_ASSET,
                ),
            ]
        )
        extra_csp_scripts: list[str] = []
    else:
        body = (
            auth_card
            + shell
            + "\n  <script id=\"encrypted-dashboard-data\" type=\"application/json\">"
            + encrypted_dashboard_data_json
            + "</script>\n"
            + "  <script id=\"export-manifest\" type=\"application/json\">"
            + export_manifest_json
            + "</script>\n"
        )
        extra_csp_scripts = [encrypted_dashboard_data_json, export_manifest_json]
    return wrap_html(
        body,
        chart_loader,
        "" if external_assets else _secure_runtime_js(),
        extra_head="\n  ".join(extra_head_parts),
        body_attributes='class="auth-locked" data-screen-label="Unlock - Encrypted Pages"',
        extra_csp_scripts=extra_csp_scripts,
        extra_styles=DEMO_UNLOCK_STYLES if demo_unlock is not None else "",
        external_assets=external_assets,
        encrypted_assets=external_assets,
    )
