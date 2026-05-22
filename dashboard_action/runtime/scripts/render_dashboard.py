"""Generate plain and encrypted HTML dashboards from canonical CSV data.

Reads traffic-daily.csv, traffic-referrers.csv, and traffic-paths.csv
via the shared load_data module and produces:

- a published dashboard for docs/ hosting
- a standalone single-file dashboard with Chart.js inlined for offline use

The published dashboard supports two modes:

- plain: unencrypted metrics in docs/index.html
- encrypted: encrypted metrics in docs/index.html, decrypted client-side
"""

import base64
import html
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from load_data import (
    load_daily, load_referrers, load_paths, load_repo_metrics,
    aggregate_totals, aggregate_by_date, aggregate_per_repo,
    top_referrers, top_paths,
    actionable_insights,
    actionable_insights_structured,
    growth_analytics,
)

OUTPUT_PATH = "docs/index.html"
STANDALONE_OUTPUT_PATH = "dist/dashboard-standalone.html"
ACTION_ROOT = Path(__file__).resolve().parents[3]
VENDORED_CHART_JS_PATH = ACTION_ROOT / "vendor" / "chart.js" / "chart.umd.min.js"
VENDORED_INTER_FONT_PATH = ACTION_ROOT / "vendor" / "inter" / "inter-latin-wght-normal.woff2"
VENDORED_MONO_FONT_PATH = (
    ACTION_ROOT / "vendor" / "jetbrains-mono" / "jetbrains-mono-latin-wght-normal.woff2"
)
PUBLISHED_CHART_JS_PATH = "assets/chart.umd.min.js"

ACCESS_MODE_ENV = "DASHBOARD_ACCESS_MODE"
DASHBOARD_KEY_ENV = "DASHBOARD_KEY"
LEGACY_PASSPHRASE_ENV = "DASHBOARD_PASSPHRASE"
ACCESS_MODE_PUBLIC = "public"
ACCESS_MODE_ENCRYPTED = "encrypted"
ACCESS_MODE_LEGACY_SHARED_SECRET = "shared-secret"

PBKDF2_ITERATIONS = 300_000
PBKDF2_SALT_BYTES = 16
AES_GCM_IV_BYTES = 12
WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
UPDATE_NOTICE_ENV = "REPONOMICS_UPDATE_NOTICE_JSON"

BASE_STYLES = """
    :root {
      /* Surfaces: three-step ladder so cards visibly lift from the canvas. */
      --bg: #0a0e14;
      --bg-raised: #1c2128;
      --bg-card: #1c2128;
      --bg-card-2: #14191f;
      --border: #30363d;
      --border-soft: #21262d;
      --text: #e6edf3;
      --text-muted: #8b949e;
      --text-dim: #6e7681;
      /* Brand accents: flat blue plus warm amber for stars/forks. */
      --accent: #1f6feb;
      --accent-2: #bf6a02;
      --c-views: #58a6ff;
      --c-uniques: #3fb950;
      --c-clones: #CC79A7;
      --c-cloners: #ffa657;
      --c-positive: #3fb950;
      --c-negative: #f85149;
      --hero-glow-1: rgba(31, 111, 235, 0.10);
      --hero-glow-2: rgba(31, 111, 235, 0.04);
      --chart-grid: rgba(48, 54, 61, 0.4);
      --chart-axis: rgba(48, 54, 61, 0.7);
      --chart-tooltip-bg: rgba(22, 27, 34, 0.96);
      --chart-tooltip-border: #30363d;
      --inset-highlight: rgba(255, 255, 255, 0.03);
      --card-shadow: 0 12px 28px rgba(0, 0, 0, 0.35);
      --card-shadow-hover: 0 18px 36px rgba(0, 0, 0, 0.45);
      --radius: 14px;
      --radius-lg: 18px;
    }
    [data-theme="light"] {
      --bg: #ffffff;
      --bg-raised: #ffffff;
      --bg-card: #ffffff;
      --bg-card-2: #f6f8fa;
      --border: #d0d7de;
      --border-soft: #d8dee4;
      --text: #1f2328;
      --text-muted: #57606a;
      --text-dim: #6e7781;
      --accent: #0969da;
      --accent-2: #9a6700;
      --c-views: #0969da;
      --c-uniques: #1a7f37;
      --c-clones: #af3aa6;
      --c-cloners: #bf6a02;
      --c-positive: #1a7f37;
      --c-negative: #cf222e;
      --hero-glow-1: rgba(9, 105, 218, 0.08);
      --hero-glow-2: rgba(9, 105, 218, 0.03);
      --chart-grid: rgba(140, 149, 159, 0.18);
      --chart-axis: rgba(140, 149, 159, 0.5);
      --chart-tooltip-bg: rgba(255, 255, 255, 0.98);
      --chart-tooltip-border: #d0d7de;
      --inset-highlight: rgba(255, 255, 255, 0.6);
      --card-shadow: 0 4px 14px rgba(31, 35, 40, 0.06), 0 1px 3px rgba(31, 35, 40, 0.04);
      --card-shadow-hover: 0 8px 22px rgba(31, 35, 40, 0.10), 0 2px 4px rgba(31, 35, 40, 0.06);
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html { color-scheme: dark; }
    [data-theme="light"] { color-scheme: light; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background:
        radial-gradient(1200px 600px at 85% -10%, var(--hero-glow-1), transparent 60%),
        radial-gradient(900px 500px at -10% 10%, var(--hero-glow-2), transparent 55%),
        var(--bg);
      background-attachment: fixed;
      color: var(--text);
      padding: 1.5rem;
      max-width: 1280px;
      margin: 0 auto;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    .mono {
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, Consolas, monospace;
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.01em;
    }
    h1 {
      color: var(--text);
      font-size: clamp(1.75rem, 4vw, 2.5rem);
      line-height: 1.05;
      margin-bottom: 0.4rem;
      font-weight: 700;
      letter-spacing: -0.025em;
    }
    /* Brand wordmark: Inter Black, lowercase, tight tracking, blue period. */
    h1.brand {
      font-family: 'Inter', sans-serif;
      font-size: clamp(2.2rem, 4.5vw, 3.2rem);
      font-weight: 900;
      letter-spacing: -0.055em;
      line-height: 0.95;
      text-transform: lowercase;
      margin: 0;
    }
    h1.brand .accent { color: var(--accent); }
    .brand-lockup {
      display: flex;
      flex-direction: column;
      gap: 0;
      margin-bottom: 0.4rem;
    }
    .brand-eyebrow {
      font-family: 'Inter', sans-serif;
      font-size: 0.82rem;
      font-weight: 500;
      letter-spacing: 0.24em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-top: 0.55rem;
    }
    h2 {
      color: var(--text);
      font-size: 1rem;
      font-weight: 600;
      letter-spacing: -0.01em;
    }
    .updated { color: var(--text-muted); font-size: 0.88rem; line-height: 1.5; }
    .tagline {
      color: var(--text-muted);
      font-size: 0.95rem;
      margin-bottom: 0.4rem;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--c-positive);
      box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.6);
      animation: pulse 2.2s ease-out infinite;
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.55); }
      80% { box-shadow: 0 0 0 10px rgba(63, 185, 80, 0); }
      100% { box-shadow: 0 0 0 0 rgba(63, 185, 80, 0); }
    }
    .hero {
      display: flex;
      gap: 1rem;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 1.5rem;
    }
    .hero-copy { min-width: 0; }
    .hero-toolbar {
      display: flex;
      gap: 0.6rem;
      flex-wrap: wrap;
      justify-content: flex-end;
      align-items: center;
    }
    .controls-card {
      display: flex;
      gap: 1rem;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      margin-bottom: 1.1rem;
    }
    .controls-group {
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
    }
    .controls-label {
      color: #8b949e;
      font-size: 0.76rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .segmented-control {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    .segmented-button {
      border: 1px solid var(--border);
      background: var(--bg-raised);
      color: var(--text);
      border-radius: 999px;
      padding: 0.5rem 0.9rem;
      cursor: pointer;
      font-size: 0.88rem;
      font-weight: 500;
      transition: border-color 150ms ease, background 150ms ease, color 150ms ease, transform 120ms ease;
    }
    .segmented-button:hover { border-color: var(--accent); color: var(--text); }
    .segmented-button:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }
    .segmented-button.active {
      color: var(--text);
      border-color: rgba(124, 106, 255, 0.55);
      background: rgba(124, 106, 255, 0.14);
      box-shadow: inset 0 0 0 1px rgba(124, 106, 255, 0.15);
    }
    .controls-hint {
      color: #8b949e;
      font-size: 0.88rem;
      line-height: 1.45;
      max-width: 62ch;
    }
    .threshold-control {
      display: flex;
      align-items: center;
      gap: 0.7rem;
      flex-wrap: wrap;
    }
    .threshold-input {
      width: 96px;
      background: var(--bg-raised);
      border: 1px solid var(--border);
      border-radius: 10px;
      color: var(--text);
      padding: 0.55rem 0.7rem;
      font-size: 0.96rem;
    }
    .threshold-input:focus {
      outline: 2px solid var(--accent);
      outline-offset: 1px;
    }
    .threshold-value {
      color: #58a6ff;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .toolbar-button {
      border: 1px solid var(--border);
      background: var(--bg-raised);
      color: var(--text);
      border-radius: 999px;
      padding: 0.55rem 0.9rem;
      cursor: pointer;
      font-size: 0.86rem;
      font-weight: 500;
      display: none;
      transition: border-color 150ms ease, color 150ms ease, background 150ms ease;
    }
    .toolbar-button.visible { display: inline-flex; }
    .toolbar-button:hover { border-color: var(--accent); color: var(--accent); background: rgba(124, 106, 255, 0.08); }
    .toolbar-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .theme-toggle { gap: 0.4rem; }
    .theme-toggle .theme-icon { font-size: 1rem; line-height: 1; }
    @media (max-width: 480px) {
      .theme-toggle .theme-label { display: none; }
    }
    .status-badge {
      display: none;
      border-radius: 999px;
      padding: 0.4rem 0.75rem;
      font-size: 0.8rem;
      font-weight: 600;
      letter-spacing: 0.01em;
      border: 1px solid var(--border);
      background: var(--bg-raised);
      color: var(--text-muted);
    }
    .status-badge.visible { display: inline-flex; align-items: center; gap: 0.4rem; }
    .status-badge.active { color: var(--accent); border-color: rgba(124, 106, 255, 0.45); background: rgba(124, 106, 255, 0.08); }
    .status-badge.compare { color: var(--c-uniques); border-color: rgba(63, 185, 80, 0.4); background: rgba(63, 185, 80, 0.06); }
    .card {
      background: linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 1.15rem;
      margin-bottom: 1.1rem;
      box-shadow: 0 1px 0 var(--inset-highlight) inset, var(--card-shadow);
      min-width: 0;
    }
    .chart-grid > *, .section-grid > * { min-width: 0; }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 0.85rem;
      margin-bottom: 1.2rem;
    }
    .stat-card {
      position: relative;
      overflow: hidden;
      min-height: 148px;
      padding: 1rem 1.05rem 0.95rem;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 0.55rem;
      transition: transform 200ms ease, border-color 200ms ease, box-shadow 200ms ease;
    }
    .stat-card:hover {
      transform: translateY(-1px);
      border-color: var(--metric-color, var(--accent));
      box-shadow: 0 1px 0 var(--inset-highlight) inset, var(--card-shadow-hover);
    }
    @keyframes spark-draw {
      from { stroke-dashoffset: 1; }
      to { stroke-dashoffset: 0; }
    }
    .stat-spark path.line {
      stroke-dasharray: 1;
      animation: spark-draw 900ms ease-out 80ms both;
    }
    .stat-card::before {
      content: '';
      position: absolute;
      inset: 0 0 auto 0;
      height: 2px;
      background: var(--metric-color, var(--accent));
      opacity: 0.85;
    }
    .stat-card[data-metric="repos"] { --metric-color: var(--accent); }
    .stat-card[data-metric="views"] { --metric-color: var(--c-views); }
    .stat-card[data-metric="uniques"] { --metric-color: var(--c-uniques); }
    .stat-card[data-metric="clones"] { --metric-color: var(--c-clones); }
    .stat-card[data-metric="cloners"] { --metric-color: var(--c-cloners); }
    .stat-card[data-metric="stars"] { --metric-color: var(--accent-2); }
    .growth-model-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.85rem;
      margin-bottom: 1.2rem;
    }
    .growth-stage {
      min-height: 118px;
      display: grid;
      gap: 0.5rem;
    }
    .growth-stage-title {
      color: var(--text-muted);
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .growth-stage-value {
      color: var(--text);
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, Consolas, monospace;
      font-size: clamp(1.35rem, 2vw, 1.9rem);
      font-weight: 650;
      line-height: 1.1;
    }
    .growth-stage-context {
      color: var(--text-muted);
      font-size: 0.82rem;
      line-height: 1.35;
    }
    .growth-cell {
      display: inline-grid;
      gap: 0.2rem;
      min-width: 180px;
      justify-content: end;
    }
    .growth-row {
      display: grid;
      grid-template-columns: minmax(3.25rem, max-content) minmax(4.5rem, max-content) minmax(4rem, max-content);
      align-items: baseline;
      column-gap: 0.45rem;
      white-space: nowrap;
    }
    .growth-label,
    .growth-total {
      color: var(--text-muted);
    }
    .growth-label {
      text-align: left;
    }
    .growth-total {
      text-align: right;
    }
    .stat-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }
    .stat-value {
      color: var(--text);
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, Consolas, monospace;
      font-variant-numeric: tabular-nums;
      font-size: clamp(1.7rem, 2.4vw, 2.3rem);
      line-height: 1;
      font-weight: 600;
      letter-spacing: -0.03em;
      align-self: end;
    }
    .stat-label {
      color: var(--text-muted);
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .stat-delta {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.74rem;
      font-weight: 600;
      padding: 0.2rem 0.45rem;
      border-radius: 999px;
      border: 1px solid transparent;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .stat-delta.up { color: var(--c-positive); background: rgba(63, 185, 80, 0.10); border-color: rgba(63, 185, 80, 0.28); }
    .stat-delta.down { color: var(--c-negative); background: rgba(248, 81, 73, 0.10); border-color: rgba(248, 81, 73, 0.28); }
    .stat-delta.flat { color: var(--text-muted); background: rgba(139, 148, 158, 0.08); border-color: rgba(139, 148, 158, 0.22); }
    .stat-delta.hidden { display: none; }
    .stat-spark {
      height: 34px;
      width: 100%;
      display: block;
      opacity: 0.9;
    }
    .stat-spark path.line { fill: none; stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; }
    .stat-spark path.area { stroke: none; opacity: 0.22; }
    .compare-summary {
      display: none;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 0.85rem;
      margin-bottom: 1.2rem;
    }
    .compare-summary.visible { display: grid; }
    .compare-card {
      position: relative;
      overflow: hidden;
      border-radius: var(--radius-lg);
      padding: 1rem 1.05rem 0.95rem;
      background: linear-gradient(180deg, var(--bg-card), var(--bg-card-2));
      border: 1px solid var(--border);
      box-shadow: var(--card-shadow);
    }
    .compare-card::before {
      content: '';
      position: absolute;
      inset: 0 0 auto 0;
      height: 2px;
      background: var(--repo-color, var(--accent));
    }
    .compare-header {
      display: flex;
      align-items: center;
      gap: 0.55rem;
      margin-bottom: 0.6rem;
      color: var(--text);
      font-weight: 600;
      letter-spacing: -0.005em;
    }
    .color-dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      flex: 0 0 auto;
    }
    .compare-metric-row {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 0.6rem;
      margin-top: 0.25rem;
    }
    .compare-metric-row.primary .compare-metric-value {
      font-size: 1.5rem;
      color: var(--text);
    }
    .compare-metric-value {
      color: var(--text);
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
      font-variant-numeric: tabular-nums;
      font-size: 1rem;
      font-weight: 600;
    }
    .compare-metric-value.muted { color: var(--text-muted); font-weight: 500; }
    .compare-metric-label {
      color: var(--text-muted);
      font-size: 0.74rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .chart-grid {
      display: grid;
      grid-template-columns: 1.45fr 1fr;
      gap: 1.1rem;
      margin-bottom: 1.1rem;
    }
    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 0.8rem;
      margin-bottom: 0.8rem;
      flex-wrap: wrap;
    }
    .section-copy { min-width: 0; }
    .section-actions {
      display: inline-flex;
      gap: 0.4rem;
      flex-wrap: wrap;
      align-items: center;
    }
    .click-hint { color: var(--text-muted); font-size: 0.83rem; line-height: 1.45; }
    .chart-container {
      position: relative;
      height: 320px;
    }
    .chart-container.tall { height: 360px; }
    .metric-tabs {
      display: inline-flex;
      gap: 0.3rem;
      background: var(--bg-card-2);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 0.25rem;
    }
    .metric-tab {
      border: 1px solid transparent;
      background: transparent;
      color: var(--text-muted);
      border-radius: 9px;
      padding: 0.4rem 0.7rem;
      font-size: 0.82rem;
      font-weight: 600;
      letter-spacing: 0.01em;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      transition: color 150ms ease, background 150ms ease, border-color 150ms ease;
    }
    .metric-tab .swatch {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--metric-color, var(--text-muted));
    }
    .metric-tab[data-metric="views"] { --metric-color: var(--c-views); }
    .metric-tab[data-metric="uniques"] { --metric-color: var(--c-uniques); }
    .metric-tab[data-metric="clones"] { --metric-color: var(--c-clones); }
    .metric-tab[data-metric="cloners"] { --metric-color: var(--c-cloners); }
    .metric-tab:hover { color: var(--text); }
    .metric-tab.active {
      color: var(--text);
      background: var(--bg-raised);
      border-color: var(--border);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.02);
    }
    .metric-tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .section-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.1rem;
      margin-bottom: 1.1rem;
    }
    .section-grid.full { grid-template-columns: 1fr; }
    .repo-strip-card {
      padding: 0.75rem 0.9rem;
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 0.85rem;
      align-items: center;
    }
    .repo-strip-label {
      color: var(--text-muted);
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      white-space: nowrap;
    }
    .repo-strip {
      display: flex;
      gap: 0.45rem;
      overflow-x: auto;
      min-width: 0;
      scrollbar-width: thin;
      scrollbar-color: var(--border) transparent;
      padding-bottom: 2px;
      mask-image: linear-gradient(90deg, transparent 0, black 12px, black calc(100% - 12px), transparent 100%);
      -webkit-mask-image: linear-gradient(90deg, transparent 0, black 12px, black calc(100% - 12px), transparent 100%);
    }
    .repo-strip::-webkit-scrollbar { height: 4px; }
    .repo-strip::-webkit-scrollbar-thumb { background: var(--border); border-radius: 999px; }
    .repo-strip-hint {
      color: var(--text-dim);
      font-size: 0.74rem;
      white-space: nowrap;
    }
    .repo-chip {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      flex: 0 0 auto;
      padding: 0.4rem 0.75rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--bg-raised);
      color: var(--text);
      font-size: 0.85rem;
      font-weight: 500;
      cursor: pointer;
      transition: border-color 150ms ease, background 150ms ease, color 150ms ease, transform 120ms ease;
      white-space: nowrap;
    }
    .repo-chip:hover {
      border-color: rgba(124, 106, 255, 0.45);
      background: rgba(124, 106, 255, 0.08);
    }
    .repo-chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .repo-chip .chip-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--chip-color, var(--text-muted));
      box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.04);
      flex: 0 0 auto;
    }
    .repo-chip .chip-mark {
      display: none;
      width: 14px;
      height: 14px;
      border-radius: 999px;
      background: var(--chip-color);
      color: var(--bg);
      font-size: 0.65rem;
      font-weight: 800;
      text-align: center;
      line-height: 14px;
    }
    .repo-chip.selected {
      background: var(--bg-raised);
      border-color: var(--chip-color);
      box-shadow: 0 0 0 1px var(--chip-color), 0 0 18px rgba(124, 106, 255, 0.18);
    }
    .repo-chip.selected .chip-mark { display: inline-block; }
    .repo-chip.compared {
      background: rgba(63, 185, 80, 0.10);
      border-color: rgba(63, 185, 80, 0.45);
    }
    .repo-chip.compared .chip-mark {
      display: inline-block;
      background: var(--c-positive);
    }
    .repo-chip .chip-meta {
      color: var(--text-muted);
      font-weight: 500;
      font-size: 0.78rem;
      font-variant-numeric: tabular-nums;
    }
    .repo-name-meta {
      display: block;
      color: var(--text-muted);
      font-size: 0.74rem;
      font-weight: 500;
      margin-top: 0.15rem;
      font-variant-numeric: tabular-nums;
    }
    .momentum-card {
      padding: 0.95rem 1.05rem;
    }
    .momentum-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }
    .momentum-cell {
      display: grid;
      gap: 0.25rem;
      padding: 0 1rem;
      border-left: 1px solid var(--border-soft);
    }
    .momentum-cell:first-child { padding-left: 0; border-left: none; }
    .momentum-label {
      color: var(--text-muted);
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }
    .momentum-label .moji { font-size: 0.95rem; }
    .momentum-value {
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
      font-variant-numeric: tabular-nums;
      font-size: 1.25rem;
      font-weight: 600;
      color: var(--text);
      letter-spacing: -0.01em;
      line-height: 1.1;
    }
    .momentum-meta {
      color: var(--text-muted);
      font-size: 0.78rem;
      font-variant-numeric: tabular-nums;
    }
    .momentum-value .repo-tag {
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
      font-size: 0.8rem;
      padding: 0.05rem 0.35rem;
      border-radius: 6px;
      background: var(--bg-card-2);
      border: 1px solid var(--border-soft);
      color: var(--text);
      margin-right: 0.4rem;
    }
    .repo-table-wrap, .table-wrap {
      overflow-x: auto;
      margin-top: 0.5rem;
      max-width: 100%;
    }
    .table-wrap td { vertical-align: top; }
    .table-wrap td:first-child {
      max-width: 0;
      width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .insights-list {
      list-style: none;
      display: grid;
      gap: 0.7rem;
      margin: 0;
      padding: 0;
    }
    .insight-item {
      border-radius: var(--radius);
      border: 1px solid var(--border-soft);
      background: var(--bg-card-2);
      padding: 0.85rem 0.95rem;
      color: var(--text);
      line-height: 1.5;
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 0.85rem;
      align-items: center;
      cursor: pointer;
      transition: border-color 150ms ease, background 150ms ease, transform 120ms ease;
    }
    .insight-item:hover {
      border-color: rgba(124, 106, 255, 0.55);
      background: rgba(124, 106, 255, 0.07);
    }
    .insight-item:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .insight-icon {
      width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      border-radius: 10px;
      font-size: 1rem;
      font-weight: 700;
      color: var(--icon-color, var(--text-muted));
      background: var(--icon-bg, rgba(139, 148, 158, 0.10));
      border: 1px solid var(--icon-border, rgba(139, 148, 158, 0.25));
    }
    .insight-item.up { --icon-color: var(--c-positive); --icon-bg: rgba(63, 185, 80, 0.12); --icon-border: rgba(63, 185, 80, 0.32); }
    .insight-item.down { --icon-color: var(--c-negative); --icon-bg: rgba(248, 81, 73, 0.12); --icon-border: rgba(248, 81, 73, 0.32); }
    .insight-item.neutral { --icon-color: var(--accent); --icon-bg: rgba(124, 106, 255, 0.12); --icon-border: rgba(124, 106, 255, 0.32); }
    .insight-body { min-width: 0; }
    .insight-headline {
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text);
      letter-spacing: -0.005em;
    }
    .insight-headline .repo {
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace;
      font-size: 0.85em;
      color: var(--text);
      background: var(--bg-raised);
      padding: 0.05rem 0.35rem;
      border-radius: 6px;
      border: 1px solid var(--border-soft);
    }
    .insight-meta {
      color: var(--text-muted);
      font-size: 0.82rem;
      margin-top: 0.2rem;
      font-variant-numeric: tabular-nums;
    }
    .insight-pct {
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
      font-size: 0.92rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--icon-color, var(--text-muted));
      white-space: nowrap;
    }
    table { width: 100%; border-collapse: collapse; }
    th {
      text-align: left;
      color: var(--text-muted);
      font-size: 0.76rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 0.7rem 0.75rem;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    th.num, td.num { text-align: right; }
    td {
      padding: 0.8rem 0.75rem;
      border-bottom: 1px solid var(--border-soft);
      font-size: 0.92rem;
      vertical-align: middle;
    }
    tr:last-child td { border-bottom: none; }
    .checkbox-col { width: 48px; text-align: center; }
    .repo-row {
      transition: background 120ms ease, opacity 120ms ease, transform 120ms ease;
      cursor: pointer;
    }
    .repo-row:hover { background: var(--row-hover, rgba(124, 106, 255, 0.06)); }
    .repo-row.selected {
      background: var(--row-selected, rgba(124, 106, 255, 0.10));
      box-shadow: inset 0 0 0 1px rgba(124, 106, 255, 0.35);
    }
    .repo-row.dimmed { opacity: 0.45; }
    .repo-row.compared { background: var(--row-compared, rgba(63, 185, 80, 0.08)); }
    .repo-name {
      font-weight: 600;
      color: var(--text);
      white-space: nowrap;
    }
    .repo-share {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .repo-bar-track {
      width: 110px;
      height: 6px;
      border-radius: 999px;
      background: var(--bg-card-2);
      overflow: hidden;
      border: 1px solid var(--border-soft);
    }
    .repo-bar {
      height: 100%;
      border-radius: 999px;
      background: var(--bar-color, linear-gradient(90deg, var(--c-views), var(--accent)));
      transition: width 240ms ease;
    }
    .repo-share-pct {
      font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
      font-variant-numeric: tabular-nums;
      font-size: 0.8rem;
      color: var(--text-muted);
      min-width: 3.4ch;
      text-align: right;
    }
    .repo-spark {
      width: 92px;
      height: 26px;
      display: block;
    }
    .repo-spark path.line { fill: none; stroke-width: 1.4; stroke-linecap: round; stroke-linejoin: round; }
    .repo-spark path.area { stroke: none; opacity: 0.18; }
    .repo-name-wrap {
      display: flex;
      align-items: center;
      gap: 0.55rem;
    }
    .repo-color-dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      flex: 0 0 auto;
      box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.04);
    }
    .repo-row:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: -2px;
    }
    .sortable {
      cursor: pointer;
      user-select: none;
      position: relative;
    }
    .sortable .arrow { opacity: 0.45; margin-left: 0.25rem; font-size: 0.7em; }
    .sortable.active .arrow { opacity: 1; color: var(--accent); }
    .empty-msg {
      color: #8b949e;
      font-style: italic;
      padding: 1rem 0;
    }
    .auth-copy {
      color: #8b949e;
      margin-bottom: 1rem;
      line-height: 1.5;
    }
    .auth-hidden-username {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .auth-form {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      align-items: center;
    }
    .auth-input {
      flex: 1 1 260px;
      min-width: 0;
      background: var(--bg-raised);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--text);
      padding: 0.8rem 0.9rem;
      font-size: 1rem;
    }
    .auth-input:focus {
      outline: 2px solid var(--accent);
      outline-offset: 1px;
    }
    .auth-button {
      border: none;
      border-radius: 12px;
      background: var(--c-positive);
      color: #ffffff;
      padding: 0.8rem 1rem;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
    }
    .auth-button:disabled {
      background: var(--border);
      color: var(--text-muted);
      cursor: not-allowed;
    }
    .auth-status {
      min-height: 1.2rem;
      margin-top: 0.9rem;
      font-size: 0.9rem;
    }
    .auth-status.pending { color: #d29922; }
    .auth-status.error { color: #f85149; }
    .update-notice {
      max-width: 980px;
      margin: 2rem auto 0;
      padding: 0.85rem 1rem;
      border: 1px solid var(--border-soft);
      border-radius: 8px;
      background: var(--bg-card-2);
      color: var(--text-muted);
      font-size: 0.9rem;
      line-height: 1.45;
    }
    .update-notice strong { color: var(--text); }
    .update-notice a {
      color: var(--accent);
      text-decoration: none;
      border-bottom: 1px dotted currentColor;
    }
    input[type="checkbox"] {
      width: 16px;
      height: 16px;
      accent-color: #3fb950;
      cursor: pointer;
    }
    footer {
      margin-top: 2.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border-soft);
      color: var(--text-dim);
      font-size: 0.82rem;
      text-align: center;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
      align-items: center;
    }
    footer .footer-line {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      flex-wrap: wrap;
      justify-content: center;
    }
    footer .dot { color: var(--border); }
    footer .footer-promises {
      font-size: 0.88rem;
      color: var(--text-muted);
    }
    footer .footer-promises b {
      color: var(--text);
      font-weight: 600;
    }
    footer a {
      color: var(--text-muted);
      text-decoration: none;
      border-bottom: 1px dotted transparent;
      transition: color 150ms ease, border-color 150ms ease;
    }
    footer a:hover { color: var(--accent); border-bottom-color: var(--accent); }
    @media (max-width: 980px) {
      .chart-grid, .section-grid { grid-template-columns: 1fr; }
      .section-grid.full { grid-template-columns: 1fr; }
      .chart-container.tall { height: 320px; }
    }
    @media (max-width: 720px) {
      body { padding: 1rem; }
      .hero { flex-direction: column; }
      .hero-toolbar { justify-content: flex-start; }
      .controls-card { flex-direction: column; }
      .auth-form { flex-direction: column; align-items: stretch; }
      .auth-button { width: 100%; }
      .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .stat-card { min-height: 132px; }
      .stat-value { font-size: 1.5rem; }
      .growth-model-grid { grid-template-columns: 1fr; }
      .insight-item { grid-template-columns: auto 1fr; }
      .insight-pct { grid-column: 2 / 3; justify-self: end; }
      .repo-spark { width: 64px; }
      .growth-cell { min-width: 150px; font-size: 0.82rem; }
      .growth-row {
        grid-template-columns: minmax(2.75rem, max-content) minmax(3.7rem, max-content) minmax(3.35rem, max-content);
        column-gap: 0.32rem;
      }
      .repo-strip-card { grid-template-columns: 1fr; gap: 0.5rem; }
      .repo-strip-hint { display: none; }
      .section-header { flex-direction: column; align-items: stretch; }
      .section-actions { justify-content: flex-start; }
      .metric-tabs { overflow-x: auto; max-width: 100%; }
      .chart-container { height: 280px; }
      .momentum-cell { padding: 0.5rem 0; border-left: none; border-top: 1px solid var(--border-soft); }
      .momentum-cell:first-child { padding-top: 0; border-top: none; }
    }
    @media (prefers-reduced-motion: reduce) {
      .stat-spark path.line { animation: none; }
      .pulse-dot { animation: none; }
      * { transition-duration: 0.001ms !important; }
    }
"""

APP_RUNTIME_JS = """
    // Categorical palette for the per-repo lines. Drawn from the
    // Okabe-Ito + Paul Tol palettes, designed to remain
    // distinguishable under protanopia / deuteranopia / tritanopia
    // and on both light and dark backgrounds. The first six entries
    // are the ones typical demos and small portfolios will hit; they
    // were ordered for maximum mutual contrast at the small-N
    // (≤ 6 repos) case.
    const palette = [
      '#56B4E9',  // sky blue
      '#E69F00',  // orange
      '#009E73',  // bluish green
      '#CC79A7',  // pink
      '#0072B2',  // dark blue
      '#D55E00',  // vermillion
      '#F0E442',  // yellow
      '#44AA99',  // teal
      '#AA4499',  // purple
      '#882255',  // mulberry
    ];
    // Dash patterns rotate alongside the palette so repos differ by
    // both hue *and* line texture — important when adjacent palette
    // entries (e.g. yellow-ochre vs red) are confusable for users
    // with red-green color deficiency.
    const DASH_PATTERNS = [
      [],            // solid
      [6, 4],        // long dash
      [2, 3],        // dotted
      [8, 3, 2, 3],  // dash-dot
      [4, 2],        // medium dash
    ];
    function dashForRepoIndex(idx) {
      return DASH_PATTERNS[idx % DASH_PATTERNS.length];
    }
    function getRepoDash(repoName) {
      const repos = state.payload?.repos || [];
      const idx = repos.findIndex((repo) => repo.name === repoName);
      return dashForRepoIndex(idx >= 0 ? idx : 0);
    }
    const METRICS = {
      views:    { key: 'views',         label: 'Views',         color: '#58a6ff' },
      uniques:  { key: 'uniques',       label: 'Visitors',      color: '#3fb950' },
      clones:   { key: 'clones',        label: 'Clones',        color: '#CC79A7' },
      cloners:  { key: 'clone_uniques', label: 'Unique Clones', color: '#ffa657' },
      stars:    { key: 'stars_delta',   label: 'Star Growth',   color: '#bf6a02', growth: true },
      subscribers: { key: 'subscribers_delta', label: 'Watcher Growth', color: '#1f6feb', growth: true },
      forks:    { key: 'forks_delta',   label: 'Fork Growth',   color: '#3fb950', growth: true }
    };
    const WINDOW_PRESETS = ['7', '14', '30', '90', 'all'];
    const DEFAULT_WINDOW = '14';
    const state = {
      payload: null,
      window: DEFAULT_WINDOW,
      minActivity: 1,
      selectedRepo: null,
      compareRepos: [],
      metric: 'views',
      repoSortKey: null,
      repoSortDir: null
    };
    function metricInfo(key) {
      const info = METRICS[key] || METRICS.views;
      return Object.assign({}, info, { color: themeMetricColor(info.key) || info.color });
    }
    function hexAlpha(hex, alpha) {
      const a = Math.round(Math.max(0, Math.min(1, alpha)) * 255).toString(16).padStart(2, '0');
      return hex + a;
    }
    function getThemeColor(varName, fallback) {
      try {
        const v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
        return v || fallback || '';
      } catch (_e) { return fallback || ''; }
    }
    function themeMetricColor(seriesKey) {
      const map = { views: '--c-views', uniques: '--c-uniques', clones: '--c-clones', clone_uniques: '--c-cloners', stars_delta: '--accent-2', subscribers_delta: '--accent', forks_delta: '--c-uniques' };
      return getThemeColor(map[seriesKey], '');
    }
    const THEME_KEY = 'gh-traffic-theme';
    function preferredTheme() {
      try {
        const saved = localStorage.getItem(THEME_KEY);
        if (saved === 'light' || saved === 'dark') return saved;
      } catch (_e) { /* ignore */ }
      try {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
      } catch (_e) { /* ignore */ }
      return 'dark';
    }
    function applyTheme(theme, persist) {
      const root = document.documentElement;
      if (theme === 'light') root.setAttribute('data-theme', 'light');
      else root.removeAttribute('data-theme');
      if (persist) {
        try { localStorage.setItem(THEME_KEY, theme); } catch (_e) { /* ignore */ }
      }
      const toggle = document.getElementById('themeToggle');
      if (toggle) {
        const icon = toggle.querySelector('.theme-icon');
        const label = toggle.querySelector('.theme-label');
        if (icon) icon.textContent = theme === 'light' ? '☀' : '☾';
        if (label) label.textContent = theme === 'light' ? 'Light' : 'Dark';
        toggle.setAttribute('aria-pressed', theme === 'light' ? 'true' : 'false');
      }
      refreshCharts();
    }
    function toggleTheme() {
      const next = (document.documentElement.getAttribute('data-theme') === 'light') ? 'dark' : 'light';
      applyTheme(next, true);
    }
    function refreshCharts() {
      // Skip work entirely until charts exist; the first updateDashboard()
      // will pick up theme colors from CSS vars on its own.
      if (!dailyChart && !weekdayChart && !stackedChart) return;
      const newOpts = chartOptions(false);
      if (dailyChart) {
        Object.assign(dailyChart.options, newOpts);
        dailyChart.update('none');
      }
      if (weekdayChart) {
        // weekday uses its own option block — patch the text/grid colors
        const tickColor = getThemeColor('--text-muted', '#8b949e');
        const gridColor = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
        const axisColor = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
        weekdayChart.options.scales.x.ticks.color = tickColor;
        weekdayChart.options.scales.y.ticks.color = tickColor;
        weekdayChart.options.scales.y.grid.color = gridColor;
        if (weekdayChart.options.scales.x.border) weekdayChart.options.scales.x.border.color = axisColor;
        if (weekdayChart.options.plugins?.tooltip) {
          weekdayChart.options.plugins.tooltip.backgroundColor = getThemeColor('--chart-tooltip-bg', 'rgba(17, 22, 29, 0.96)');
          weekdayChart.options.plugins.tooltip.borderColor = getThemeColor('--chart-tooltip-border', '#262d38');
          weekdayChart.options.plugins.tooltip.titleColor = getThemeColor('--text', '#e6edf3');
          weekdayChart.options.plugins.tooltip.bodyColor = getThemeColor('--text', '#e6edf3');
        }
        weekdayChart.update('none');
      }
      if (stackedChart) {
        const stackedOpts = chartOptions(true);
        // Preserve stack flag set elsewhere
        const wasStacked = stackedChart.options.scales?.y?.stacked;
        Object.assign(stackedChart.options, stackedOpts);
        if (stackedChart.options.scales && stackedChart.options.scales.y) {
          stackedChart.options.scales.y.stacked = !!wasStacked;
        }
        stackedChart.update('none');
      }
      if (state.payload) updateDashboard();
    }
    let dailyChart = null;
    let weekdayChart = null;
    let stackedChart = null;

    function formatNumber(value) {
      return Number(value || 0).toLocaleString();
    }

    function compactNumber(value) {
      const n = Number(value || 0);
      const abs = Math.abs(n);
      if (abs >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + 'M';
      if (abs >= 1_000) return (n / 1_000).toFixed(n >= 10_000 ? 0 : 1) + 'k';
      return String(Math.round(n));
    }

    function formatSigned(value) {
      const n = Number(value || 0);
      return (n >= 0 ? '+' : '') + formatNumber(n);
    }

    function sumArray(values) {
      return (values || []).reduce((total, value) => total + Number(value || 0), 0);
    }

    function buildSparklinePath(values, width, height) {
      const n = (values || []).length;
      if (!n) { return { line: '', area: '' }; }
      if (n === 1) {
        const y = height / 2;
        return { line: `M0 ${y.toFixed(2)} L${width} ${y.toFixed(2)}`, area: '' };
      }
      const max = Math.max(...values);
      const min = Math.min(...values);
      const range = max - min || 1;
      const pad = 2;
      const innerH = height - pad * 2;
      const pts = values.map((v, i) => {
        const x = (i / (n - 1)) * width;
        const y = pad + (1 - (Number(v || 0) - min) / range) * innerH;
        return [x, y];
      });
      const line = pts.map(([x, y], i) => (i === 0 ? 'M' : 'L') + x.toFixed(2) + ' ' + y.toFixed(2)).join(' ');
      const area = line + ` L${width} ${height} L0 ${height} Z`;
      return { line, area };
    }

    function renderSparkline(id, values, color) {
      const el = document.getElementById(id);
      if (!el) return;
      if (!values || values.length < 2) {
        el.innerHTML = '';
        return;
      }
      const { line, area } = buildSparklinePath(values, 100, 34);
      // pathLength="1" normalizes the path's apparent stroke length to 1
      // unit so the CSS draw-in animation (stroke-dasharray: 1) always
      // covers the entire line regardless of how spiky the underlying
      // data is. Without this, jagged metrics (Views, Visitors) had path
      // lengths that exceeded the dash and clipped the tail.
      el.innerHTML =
        `<path class="area" d="${area}" fill="${color}"></path>` +
        `<path class="line" d="${line}" stroke="${color}" pathLength="1"></path>`;
    }

    function splitWindow(series) {
      const dates = (series && series.dates) || [];
      if (dates.length < 2) return null;
      const mid = Math.ceil(dates.length / 2);
      const slice = (arr) => ({
        first: (arr || []).slice(0, mid),
        second: (arr || []).slice(mid)
      });
      return {
        views: slice(series.views),
        uniques: slice(series.uniques),
        clones: slice(series.clones),
        clone_uniques: slice(series.clone_uniques),
        firstDays: mid,
        secondDays: dates.length - mid
      };
    }

    function computeDelta(split, field) {
      if (!split) return null;
      const f = split[field];
      if (!f) return null;
      const prior = sumArray(f.first);
      const current = sumArray(f.second);
      if (prior === 0 && current === 0) return null;
      // Prior window had no data (brand-new repo, or first collection
      // window). Percentage is undefined; omit the pill rather than
      // pretending we know the delta.
      if (prior === 0) return null;
      const pct = ((current - prior) / prior) * 100;
      let direction = 'flat';
      if (pct > 2) direction = 'up';
      else if (pct < -2) direction = 'down';
      return { pct, direction, current, prior };
    }

    function renderDelta(id, delta) {
      const el = document.getElementById(id);
      if (!el) return;
      if (!delta) {
        el.className = 'stat-delta hidden';
        el.textContent = '';
        return;
      }
      let label;
      if (delta.pct === null) {
        label = delta.label || 'new';
      } else {
        const sign = delta.pct >= 0 ? '+' : '';
        const arrow = delta.direction === 'up' ? '▲' : delta.direction === 'down' ? '▼' : '•';
        const rounded = Math.abs(delta.pct) >= 100 ? Math.round(delta.pct) : delta.pct.toFixed(1);
        label = `${arrow} ${sign}${rounded}%`;
      }
      el.className = 'stat-delta ' + (delta.direction || 'flat');
      el.textContent = label;
    }

    function escapeHtml(text) {
      const d = document.createElement('div');
      d.appendChild(document.createTextNode(text == null ? '' : String(text)));
      return d.innerHTML;
    }

    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) {
        el.textContent = value;
      }
    }

    function getShortName(repoName) {
      if (!repoName) {
        return '';
      }
      const parts = String(repoName).split('/');
      return parts[parts.length - 1] || repoName;
    }

    function getRepoByName(repoName) {
      return getVisibleRepos().find((repo) => repo.name === repoName) || null;
    }

    function getRepoColor(repoName) {
      const repos = state.payload?.repos || [];
      const idx = repos.findIndex((repo) => repo.name === repoName);
      return palette[(idx >= 0 ? idx : 0) % palette.length];
    }

    function isComparing() {
      return state.compareRepos.length >= 2;
    }

    function normalizeWindow(value) {
      const raw = String(value || '').trim().toLowerCase();
      if (raw === 'recent') return DEFAULT_WINDOW;
      if (WINDOW_PRESETS.includes(raw)) return raw;
      return null;
    }

    function getDefaultWindow() {
      return (
        normalizeWindow(state.payload?.meta?.default_window) ||
        normalizeWindow(state.payload?.meta?.default_range) ||
        DEFAULT_WINDOW
      );
    }

    function getSelectedWindow() {
      return normalizeWindow(state.window) || getDefaultWindow();
    }

    function getWindowDays() {
      const selected = getSelectedWindow();
      return selected === 'all' ? null : Number(selected);
    }

    function getRangeLabel() {
      const days = getWindowDays();
      return days === null ? 'All retained data' : 'Last ' + days + ' collected days';
    }

    function parseIsoDate(value) {
      if (!value) {
        return null;
      }
      const parts = String(value).split('-').map(Number);
      if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) {
        return null;
      }
      return new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
    }

    function formatIsoDate(date) {
      return date.toISOString().slice(0, 10);
    }

    function getWindowCutoffDate() {
      const days = getWindowDays();
      if (days === null) {
        return null;
      }
      const dates = state.payload?.daily?.dates || [];
      if (!dates.length) {
        return null;
      }
      const latest = parseIsoDate(dates[dates.length - 1]);
      if (!latest) {
        return null;
      }
      const cutoff = new Date(latest.getTime());
      cutoff.setUTCDate(cutoff.getUTCDate() - (days - 1));
      return formatIsoDate(cutoff);
    }

    function seriesForRange(series) {
      if (!series) {
        return {
          dates: [],
          views: [],
          uniques: [],
          clones: [],
          clone_uniques: [],
          stars_delta: [],
          subscribers_delta: [],
          forks_delta: []
        };
      }
      if (getSelectedWindow() === 'all') {
        return series;
      }

      const cutoff = getWindowCutoffDate();
      if (!cutoff) {
        return series;
      }

      const windowed = {};
      Object.keys(series).forEach((key) => {
        windowed[key] = Array.isArray(series[key]) ? [] : series[key];
      });
      (series.dates || []).forEach((date, idx) => {
        if (date >= cutoff) {
          Object.keys(windowed).forEach((key) => {
            if (!Array.isArray(windowed[key])) return;
            windowed[key].push(key === 'dates' ? date : (series[key] || [])[idx] || 0);
          });
        }
      });
      if ('samples' in windowed) {
        windowed.samples = (windowed.dates || []).length;
      }
      return windowed;
    }

    function latestSeriesValue(series, key, fallback) {
      const values = (series && series[key]) || [];
      if (!values.length) return Number(fallback || 0);
      return Number(values[values.length - 1] || 0);
    }

    function seriesDelta(series, key, fallback) {
      const values = (series && series[key]) || [];
      if (values.length < 2) {
        return values.length === 1 ? 0 : Number(fallback || 0);
      }
      return Number(values[values.length - 1] || 0) - Number(values[0] || 0);
    }

    function buildRepoMetrics(repoName) {
      const series = seriesForRange(state.payload?.repo_series?.[repoName]);
      const growthRow = state.payload?.growth?.per_repo?.[repoName] || {};
      const deltas = growthRow.deltas || {};
      const growthSeries = seriesForRange(growthRow.series || {});
      const sum = (values) => (values || []).reduce((total, value) => total + Number(value || 0), 0);
      const starsDelta = seriesDelta(growthSeries, 'stargazers', deltas.stars_delta || deltas.stargazers_delta);
      const subscribersDelta = seriesDelta(growthSeries, 'subscribers', deltas.subscribers_delta);
      const forksDelta = seriesDelta(growthSeries, 'forks', deltas.forks_delta);
      return {
        name: repoName,
        views: sum(series.views),
        uniques: sum(series.uniques),
        clones: sum(series.clones),
        clone_uniques: sum(series.clone_uniques),
        stars_delta: starsDelta,
        subscribers_delta: subscribersDelta,
        forks_delta: forksDelta,
        stars: latestSeriesValue(growthSeries, 'stargazers', deltas.current_stars || deltas.current_stargazers),
        subscribers: latestSeriesValue(growthSeries, 'subscribers', deltas.current_subscribers),
        forks: latestSeriesValue(growthSeries, 'forks', deltas.current_forks),
        days: (series.dates || []).length,
        activity: sum(series.views) + sum(series.clones),
        series
      };
    }

    function getAllRepoMetrics() {
      return (state.payload?.repos || [])
        .map((repo) => buildRepoMetrics(repo.name))
        .sort((a, b) => (b.views - a.views) || (b.clones - a.clones) || a.name.localeCompare(b.name));
    }

    function getVisibleRepos() {
      return getAllRepoMetrics().filter((repo) => repo.activity >= state.minActivity);
    }

    function buildAggregateSeries(repos) {
      const byDate = new Map();
      repos.forEach((repo) => {
        const series = repo.series || {};
        (series.dates || []).forEach((date, idx) => {
          const current = byDate.get(date) || {
            views: 0,
            uniques: 0,
            clones: 0,
            clone_uniques: 0
          };
          current.views += Number(series.views[idx] || 0);
          current.uniques += Number(series.uniques[idx] || 0);
          current.clones += Number(series.clones[idx] || 0);
          current.clone_uniques += Number(series.clone_uniques[idx] || 0);
          byDate.set(date, current);
        });
      });
      const dates = [...byDate.keys()].sort();
      return {
        dates,
        views: dates.map((date) => byDate.get(date).views),
        uniques: dates.map((date) => byDate.get(date).uniques),
        clones: dates.map((date) => byDate.get(date).clones),
        clone_uniques: dates.map((date) => byDate.get(date).clone_uniques)
      };
    }

    function buildWeekdaySummaryFromSeries(seriesMap) {
      const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const totals = labels.map(() => ({ views: 0, uniques: 0, clones: 0, clone_uniques: 0, samples: 0 }));
      Object.values(seriesMap || {}).forEach((series) => {
        (series.dates || []).forEach((date, idx) => {
          const parsed = parseIsoDate(date);
          if (!parsed) return;
          const weekday = (parsed.getUTCDay() + 6) % 7;
          totals[weekday].views += Number(series.views[idx] || 0);
          totals[weekday].uniques += Number((series.uniques || [])[idx] || 0);
          totals[weekday].clones += Number(series.clones[idx] || 0);
          totals[weekday].clone_uniques += Number((series.clone_uniques || [])[idx] || 0);
          totals[weekday].samples += 1;
        });
      });
      const avg = (field) => totals.map((b) => b.samples ? Math.round((b[field] / b.samples) * 10) / 10 : 0);
      return {
        labels,
        views: avg('views'),
        uniques: avg('uniques'),
        clones: avg('clones'),
        clone_uniques: avg('clone_uniques')
      };
    }

    function getCurrentWindowData() {
      const repos = getVisibleRepos();
      const aggregate = buildAggregateSeries(repos);
      const totals = repos.reduce((acc, repo) => {
        acc.repo_count += 1;
        acc.total_views += repo.views;
        acc.total_uniques += repo.uniques;
        acc.total_clones += repo.clones;
        acc.total_clone_uniques += repo.clone_uniques;
        acc.total_stars_delta += repo.stars_delta;
        acc.total_subscribers_delta += repo.subscribers_delta;
        acc.total_forks_delta += repo.forks_delta;
        acc.total_stars += repo.stars;
        acc.total_subscribers += repo.subscribers;
        acc.total_forks += repo.forks;
        return acc;
      }, {
        repo_count: 0,
        total_views: 0,
        total_uniques: 0,
        total_clones: 0,
        total_clone_uniques: 0,
        total_stars_delta: 0,
        total_subscribers_delta: 0,
        total_forks_delta: 0,
        total_stars: 0,
        total_subscribers: 0,
        total_forks: 0
      });
      return {
        repos,
        totals,
        daily: aggregate,
        weekday: buildWeekdaySummaryFromSeries(
          Object.fromEntries(repos.map((repo) => [repo.name, repo.series]))
        )
      };
    }

    function aggregateSnapshotRows(rowsByRepo, selectedRepos, keyField) {
      const totals = new Map();
      selectedRepos.forEach((repoName) => {
        (rowsByRepo?.[repoName] || []).forEach((row) => {
          const key = row[keyField] || '';
          const current = totals.get(key) || { ...row, count: 0, uniques: 0 };
          current.count += Number(row.count || 0);
          current.uniques += Number(row.uniques || 0);
          totals.set(key, current);
        });
      });
      return [...totals.values()].sort((a, b) => (b.count - a.count) || String(a[keyField]).localeCompare(String(b[keyField])));
    }

    function getCurrentSnapshotRepoNames() {
      if (isComparing()) {
        return state.compareRepos;
      }
      if (state.selectedRepo) {
        return [state.selectedRepo];
      }
      return getVisibleRepos().map((repo) => repo.name);
    }

    function getCurrentReferrerRows() {
      return aggregateSnapshotRows(
        state.payload?.repo_referrers,
        getCurrentSnapshotRepoNames(),
        'referrer'
      );
    }

    function getCurrentPathRows() {
      return aggregateSnapshotRows(
        state.payload?.repo_paths,
        getCurrentSnapshotRepoNames(),
        'path'
      );
    }

    function sanitizeSelection() {
      const visibleRepoNames = new Set(getVisibleRepos().map((repo) => repo.name));
      if (state.selectedRepo && !visibleRepoNames.has(state.selectedRepo)) {
        state.selectedRepo = null;
      }
      state.compareRepos = state.compareRepos.filter((repoName) => visibleRepoNames.has(repoName));
    }

    function buildUpdatedText(payload) {
      const windowData = getCurrentWindowData();
      const base = 'Last updated: ' + (payload.generated_at || 'unknown');
      const rangeText = 'Window: ' + getRangeLabel();
      const repoText = 'Showing ' + formatNumber(windowData.totals.repo_count || 0) + ' repositories';
      const daysText = 'Tracking span: ' + formatNumber(payload.totals.days_tracked || 0) + ' collected days total';
      return [base, rangeText, repoText, daysText].join(' | ');
    }

    function formatTooltipDate(label) {
      try {
        const d = parseIsoDate(label);
        if (!d) return label;
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
      } catch (_e) {
        return label;
      }
    }

    function formatEventDate(iso) {
      const d = parseIsoDate(iso);
      if (!d) return iso;
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
    }

    function daysBetween(a, b) {
      const da = parseIsoDate(a);
      const db = parseIsoDate(b);
      if (!da || !db) return Infinity;
      return Math.round((da.getTime() - db.getTime()) / 86400000);
    }

    function computeMomentum() {
      const visible = getVisibleRepos();
      if (!visible.length) return null;
      const aggregate = buildAggregateSeries(visible);
      const dates = aggregate.dates || [];
      const views = aggregate.views || [];
      if (!dates.length) return null;

      let bestIdx = 0;
      for (let i = 1; i < views.length; i += 1) {
        if (Number(views[i] || 0) > Number(views[bestIdx] || 0)) bestIdx = i;
      }
      const bestDay = { date: dates[bestIdx], views: Number(views[bestIdx] || 0) };

      // Trailing-window median (last up-to-14 days, excluding the latest).
      const tailWindow = 14;
      const start = Math.max(0, views.length - tailWindow - 1);
      const tail = views.slice(start, Math.max(start, views.length - 1));
      let median = 0;
      if (tail.length) {
        const sorted = tail.slice().map(Number).sort((a, b) => a - b);
        median = sorted.length % 2
          ? sorted[(sorted.length - 1) >> 1]
          : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
      }

      // Current streak: consecutive trailing days with views > median.
      let streak = 0;
      for (let i = views.length - 1; i >= 0; i -= 1) {
        if (Number(views[i] || 0) > median) streak += 1;
        else break;
      }

      // Top single-repo single-day in the window.
      let topRepo = null;
      let topDay = -1;
      visible.forEach((repo) => {
        const series = repo.series;
        if (!series) return;
        (series.dates || []).forEach((date, idx) => {
          const v = Number((series.views || [])[idx] || 0);
          if (v > topDay) {
            topDay = v;
            topRepo = { name: repo.name, views: v, date };
          }
        });
      });

      // Days since the most recent peak (peak = best day).
      const latestDate = dates[dates.length - 1];
      const daysSincePeak = bestDay.date ? Math.max(0, daysBetween(latestDate, bestDay.date)) : null;

      return { bestDay, streak: { days: streak, median }, topRepo, daysSincePeak };
    }

    function renderMomentum() {
      const grid = document.getElementById('momentum-grid');
      const section = document.getElementById('momentum-section');
      if (!grid || !section) return;
      const m = computeMomentum();
      if (!m || !m.bestDay || !m.bestDay.date) {
        section.style.display = 'none';
        return;
      }
      section.style.display = 'block';
      const cells = [];

      // Hot streak
      if (m.streak.days >= 1) {
        cells.push(`
          <div class="momentum-cell">
            <span class="momentum-label"><span class="moji">🔥</span>Hot streak</span>
            <span class="momentum-value">${m.streak.days}d</span>
            <span class="momentum-meta">consecutive days above baseline (~${formatNumber(Math.round(m.streak.median))}/d)</span>
          </div>`);
      } else {
        cells.push(`
          <div class="momentum-cell">
            <span class="momentum-label"><span class="moji">🔥</span>Hot streak</span>
            <span class="momentum-value" style="color: var(--text-muted)">—</span>
            <span class="momentum-meta">no current streak above baseline (~${formatNumber(Math.round(m.streak.median))}/d)</span>
          </div>`);
      }

      // Best day
      const bestDateLabel = formatEventDate(m.bestDay.date);
      const sinceLabel = (m.daysSincePeak !== null && m.daysSincePeak !== undefined)
        ? (m.daysSincePeak === 0 ? 'today' : (m.daysSincePeak === 1 ? 'yesterday' : `${m.daysSincePeak}d ago`))
        : '';
      cells.push(`
        <div class="momentum-cell" title="Highest combined-views day across all visible repos">
          <span class="momentum-label"><span class="moji">⭐</span>Best overall day</span>
          <span class="momentum-value">${formatNumber(m.bestDay.views)} views</span>
          <span class="momentum-meta">${escapeHtml(bestDateLabel)}${sinceLabel ? ' · ' + escapeHtml(sinceLabel) : ''}</span>
        </div>`);

      // Top repo single-day
      if (m.topRepo) {
        cells.push(`
          <div class="momentum-cell" title="The single repo + day with the highest views in the window">
            <span class="momentum-label"><span class="moji">🏆</span>Best single-repo day</span>
            <span class="momentum-value"><span class="repo-tag">${escapeHtml(getShortName(m.topRepo.name))}</span>${formatNumber(m.topRepo.views)}</span>
            <span class="momentum-meta">${escapeHtml(formatEventDate(m.topRepo.date))}</span>
          </div>`);
      }

      grid.innerHTML = cells.join('');
    }

    function chartOptions(stacked) {
      const tick = getThemeColor('--text-muted', '#8b949e');
      const grid = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
      const axis = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
      const tipBg = getThemeColor('--chart-tooltip-bg', 'rgba(17, 22, 29, 0.96)');
      const tipBorder = getThemeColor('--chart-tooltip-border', '#262d38');
      const text = getThemeColor('--text', '#e6edf3');
      return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        animation: { duration: 320 },
        plugins: {
          legend: {
            display: !!stacked,
            position: 'bottom',
            labels: { color: tick, boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 14 }
          },
          tooltip: {
            backgroundColor: tipBg,
            borderColor: tipBorder,
            borderWidth: 1,
            titleColor: text,
            bodyColor: text,
            padding: 10,
            boxPadding: 4,
            usePointStyle: true,
            callbacks: {
              title: function(items) { return items.length ? formatTooltipDate(items[0].label) : ''; },
              label: function(ctx) {
                const value = ctx.parsed && typeof ctx.parsed.y === 'number' ? ctx.parsed.y : ctx.parsed;
                return ' ' + (ctx.dataset.label || '') + '  ' + Number(value || 0).toLocaleString();
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: tick, maxRotation: 0, autoSkipPadding: 18 },
            grid: { color: grid, drawTicks: false },
            border: { color: axis }
          },
          y: {
            beginAtZero: true,
            stacked: !!stacked,
            ticks: {
              color: tick,
              callback: function(value) { return compactNumber(value); }
            },
            grid: { color: grid, drawTicks: false },
            border: { display: false }
          }
        }
      };
    }

    function resetCheckboxes() {
      document.querySelectorAll('#repo-table input[type="checkbox"]').forEach((input) => {
        input.checked = false;
      });
    }

    function updateControls() {
      const thresholdInput = document.getElementById('thresholdInput');
      const thresholdValue = document.getElementById('thresholdValue');
      const rangeHint = document.getElementById('rangeHint');

      document.querySelectorAll('[data-window]').forEach((button) => {
        const isActive = button.dataset.window === getSelectedWindow();
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      });
      thresholdInput.value = String(state.minActivity);
      thresholdValue.textContent = formatNumber(state.minActivity);
      const days = getWindowDays();
      rangeHint.textContent = days === null
        ? 'All shows all data since dashboard collection began.'
        : 'Showing up to the latest ' + days + ' collected days. Switch to All for everything collected so far.';
    }

    function setWindow(nextWindow) {
      const normalized = normalizeWindow(nextWindow);
      if (!normalized || state.window === normalized) {
        return;
      }
      state.window = normalized;
      sanitizeSelection();
      updateDashboard();
    }

    function setMetric(nextMetric) {
      if (!METRICS[nextMetric] || state.metric === nextMetric) return;
      state.metric = nextMetric;
      updateDashboard();
    }

    function updateMetricTabs() {
      document.querySelectorAll('.metric-tab').forEach((btn) => {
        const isActive = btn.dataset.metric === state.metric;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
    }

    function setThreshold(nextValue) {
      const parsed = Number(nextValue);
      const safeValue = Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
      if (safeValue === state.minActivity) {
        return;
      }
      state.minActivity = safeValue;
      sanitizeSelection();
      updateDashboard();
    }

    function clearSelection() {
      state.selectedRepo = null;
      state.compareRepos = [];
      resetCheckboxes();
      updateDashboard();
    }

    function selectRepo(repoName) {
      if (state.selectedRepo === repoName) {
        state.selectedRepo = null;
      } else {
        state.selectedRepo = repoName;
      }
      state.compareRepos = [];
      resetCheckboxes();
      updateDashboard();
    }

    function activateRepo(repoName, modifier) {
      if (!repoName) return;
      if (modifier) {
        // ⌘/Ctrl/Shift-click: enter or extend compare mode.
        // If currently focused on a *different* repo, promote that focus
        // into the compare set so the user picks up where they left off.
        const inCompare = state.compareRepos.includes(repoName);
        if (state.selectedRepo && state.selectedRepo !== repoName) {
          const seed = state.selectedRepo;
          state.selectedRepo = null;
          if (!state.compareRepos.includes(seed)) {
            state.compareRepos = state.compareRepos.concat(seed);
          }
        } else if (state.selectedRepo === repoName) {
          // ⌘-click on the currently focused repo: just clear the focus.
          state.selectedRepo = null;
          resetCheckboxes();
          updateDashboard();
          return;
        }
        state.compareRepos = inCompare
          ? state.compareRepos.filter((n) => n !== repoName)
          : state.compareRepos.concat(repoName);
        // If we end up with only one repo in the compare set, treat it as a focus.
        if (state.compareRepos.length === 1) {
          state.selectedRepo = state.compareRepos[0];
          state.compareRepos = [];
        }
        resetCheckboxes();
        updateDashboard();
        return;
      }
      // Plain click → focus toggle, clear any compare state.
      selectRepo(repoName);
    }

    function toggleRepoCompare(repoName, checked) {
      if (checked) {
        if (!state.compareRepos.includes(repoName)) {
          state.compareRepos.push(repoName);
        }
      } else {
        state.compareRepos = state.compareRepos.filter((value) => value !== repoName);
      }
      if (isComparing()) {
        state.selectedRepo = null;
      }
      updateDashboard();
    }

    function updateToolbar() {
      const activeBadge = document.getElementById('activeBadge');
      const compareBadge = document.getElementById('compareBadge');
      const clearButton = document.getElementById('clearSelectionBtn');

      if (isComparing()) {
        activeBadge.classList.remove('visible');
        compareBadge.textContent = 'Comparing ' + state.compareRepos.length + ' repos';
        compareBadge.classList.add('visible');
        clearButton.classList.add('visible');
      } else if (state.selectedRepo) {
        compareBadge.classList.remove('visible');
        activeBadge.textContent = 'Focused: ' + getShortName(state.selectedRepo);
        activeBadge.classList.add('visible');
        clearButton.classList.add('visible');
      } else {
        activeBadge.classList.remove('visible');
        compareBadge.classList.remove('visible');
        clearButton.classList.remove('visible');
      }
    }

    function updateStats() {
      const windowData = getCurrentWindowData();
      const totals = windowData.totals || {};
      const focusedRepo = state.selectedRepo ? getRepoByName(state.selectedRepo) : null;
      const statsGrid = document.getElementById('stats-grid');
      const compareSummary = document.getElementById('compare-summary');

      if (isComparing()) {
        statsGrid.style.display = 'none';
        compareSummary.innerHTML = '';
        const metric = metricInfo(state.metric);
        const primaryKey = metric.key;
        const allRows = [
          { key: 'views', label: 'Views' },
          { key: 'uniques', label: 'Visitors' },
          { key: 'clones', label: 'Clones' },
          { key: 'clone_uniques', label: 'Unique Clones' },
          { key: 'stars_delta', label: 'Star Growth' },
          { key: 'subscribers_delta', label: 'Watcher Growth' },
          { key: 'forks_delta', label: 'Fork Growth' }
        ];
        state.compareRepos.forEach((repoName) => {
          const repo = getRepoByName(repoName);
          if (!repo) return;
          const repoColor = getRepoColor(repo.name);
          const card = document.createElement('div');
          card.className = 'compare-card';
          card.style.setProperty('--repo-color', repoColor);
          let rows = `
            <div class="compare-metric-row primary">
              <span class="compare-metric-label">${escapeHtml(metric.label)}</span>
              <span class="compare-metric-value">${primaryKey.endsWith('_delta') ? formatSigned(repo[primaryKey]) : formatNumber(repo[primaryKey])}</span>
            </div>`;
          allRows.filter((r) => r.key !== primaryKey).forEach((r) => {
            rows += `
              <div class="compare-metric-row">
                <span class="compare-metric-label">${escapeHtml(r.label)}</span>
                <span class="compare-metric-value muted">${r.key.endsWith('_delta') ? formatSigned(repo[r.key]) : formatNumber(repo[r.key])}</span>
              </div>`;
          });
          card.innerHTML = `
            <div class="compare-header">
              <span class="color-dot" style="background:${repoColor}"></span>
              <span>${escapeHtml(getShortName(repo.name))}</span>
            </div>
            ${rows}
          `;
          compareSummary.appendChild(card);
        });
        compareSummary.classList.add('visible');
        return;
      }

      compareSummary.classList.remove('visible');
      compareSummary.innerHTML = '';
      statsGrid.style.display = 'grid';

      const sparkSource = focusedRepo ? focusedRepo.series : windowData.daily;
      const split = splitWindow(sparkSource);

      if (focusedRepo) {
        setText('statRepos', '1');
        setText('statViews', formatNumber(focusedRepo.views));
        setText('statUniques', formatNumber(focusedRepo.uniques));
        setText('statClones', formatNumber(focusedRepo.clones));
        setText('statCloneUniques', formatNumber(focusedRepo.clone_uniques));
        setText('growthAttentionValue', formatNumber(focusedRepo.views) + ' / ' + formatNumber(focusedRepo.uniques));
        setText('growthAttentionContext', 'views / visitors in the selected window');
        setText('growthInterestValue', formatSigned(focusedRepo.stars_delta) + ' / ' + formatSigned(focusedRepo.subscribers_delta));
        setText('growthInterestContext', 'stars / watchers; now ' + formatNumber(focusedRepo.stars) + ' / ' + formatNumber(focusedRepo.subscribers));
        setText('growthAdoptionValue', formatNumber(focusedRepo.clones) + ' / ' + formatSigned(focusedRepo.forks_delta));
        setText('growthAdoptionContext', 'clones / forks; now ' + formatNumber(focusedRepo.forks) + ' forks');
      } else {
        setText('statRepos', formatNumber(totals.repo_count));
        setText('statViews', formatNumber(totals.total_views));
        setText('statUniques', formatNumber(totals.total_uniques));
        setText('statClones', formatNumber(totals.total_clones));
        setText('statCloneUniques', formatNumber(totals.total_clone_uniques));
        setText('growthAttentionValue', formatNumber(totals.total_views) + ' / ' + formatNumber(totals.total_uniques));
        setText('growthAttentionContext', 'views / visitors across visible repos');
        setText('growthInterestValue', formatSigned(totals.total_stars_delta) + ' / ' + formatSigned(totals.total_subscribers_delta));
        setText('growthInterestContext', 'stars / watchers; now ' + formatNumber(totals.total_stars) + ' / ' + formatNumber(totals.total_subscribers));
        setText('growthAdoptionValue', formatNumber(totals.total_clones) + ' / ' + formatSigned(totals.total_forks_delta));
        setText('growthAdoptionContext', 'clones / forks; now ' + formatNumber(totals.total_forks) + ' forks');
      }

      renderDelta('deltaRepos', null);
      renderDelta('deltaViews', computeDelta(split, 'views'));
      renderDelta('deltaUniques', computeDelta(split, 'uniques'));
      renderDelta('deltaClones', computeDelta(split, 'clones'));
      renderDelta('deltaCloneUniques', computeDelta(split, 'clone_uniques'));

      const src = sparkSource || { views: [], uniques: [], clones: [], clone_uniques: [] };
      renderSparkline('sparkRepos', (windowData.daily && windowData.daily.views) || [], getThemeColor('--accent', '#1f6feb'));
      renderSparkline('sparkViews', src.views || [], getThemeColor('--c-views', '#58a6ff'));
      renderSparkline('sparkUniques', src.uniques || [], getThemeColor('--c-uniques', '#3fb950'));
      renderSparkline('sparkClones', src.clones || [], getThemeColor('--c-clones', '#CC79A7'));
      renderSparkline('sparkCloneUniques', src.clone_uniques || [], getThemeColor('--c-cloners', '#ffa657'));
    }

    function ensureCharts() {
      if (!dailyChart) {
        dailyChart = new Chart(document.getElementById('dailyChart'), {
          type: 'line',
          data: { labels: [], datasets: [] },
          options: chartOptions(false)
        });
      }
      if (!weekdayChart) {
        const tick = getThemeColor('--text-muted', '#8b949e');
        const grid = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
        const axis = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
        const tipBg = getThemeColor('--chart-tooltip-bg', 'rgba(17, 22, 29, 0.96)');
        const tipBorder = getThemeColor('--chart-tooltip-border', '#262d38');
        const text = getThemeColor('--text', '#e6edf3');
        weekdayChart = new Chart(document.getElementById('weekdayChart'), {
          type: 'bar',
          data: { labels: [], datasets: [] },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 320 },
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: tipBg,
                borderColor: tipBorder,
                borderWidth: 1,
                titleColor: text,
                bodyColor: text,
                padding: 10,
                callbacks: {
                  label: function(ctx) {
                    return ' ' + (ctx.dataset.label || '') + '  ' + Number(ctx.parsed.y || 0).toLocaleString();
                  }
                }
              }
            },
            scales: {
              x: {
                ticks: { color: tick },
                grid: { display: false },
                border: { color: axis }
              },
              y: {
                beginAtZero: true,
                ticks: { color: tick, callback: function(v) { return compactNumber(v); } },
                grid: { color: grid, drawTicks: false },
                border: { display: false }
              }
            }
          }
        });
      }
      if (!stackedChart) {
        const opts = chartOptions(true);
        const repoFromDatasetLabel = function(label) {
          return (state.payload?.repos || []).find((r) => getShortName(r.name) === label)?.name || label;
        };
        const modifierFromEvent = function(event) {
          const native = event && (event.native || event);
          return !!(native && (native.metaKey || native.ctrlKey || native.shiftKey));
        };
        opts.onClick = function(event, elements, chart) {
          if (!elements || !elements.length) return;
          const ds = chart.data.datasets[elements[0].datasetIndex];
          if (!ds) return;
          // Match chip strip / table semantics: plain click = focus,
          // ⌘/Ctrl/Shift-click = enter or extend compare.
          activateRepo(repoFromDatasetLabel(ds.label), modifierFromEvent(event));
        };
        opts.onHover = function(event, elements, chart) {
          chart.canvas.style.cursor = (elements && elements.length) ? 'pointer' : 'default';
        };
        if (opts.plugins && opts.plugins.legend) {
          opts.plugins.legend.onClick = function(event, legendItem, legend) {
            const chart = legend.chart;
            const ds = chart.data.datasets[legendItem.datasetIndex];
            if (!ds) return;
            activateRepo(repoFromDatasetLabel(ds.label), modifierFromEvent(event));
          };
        }
        stackedChart = new Chart(document.getElementById('stackedChart'), {
          type: 'line',
          data: { labels: [], datasets: [] },
          options: opts
        });
      }
    }

    function buildAreaGradient(ctx, chartArea, color) {
      if (!chartArea) return hexAlpha(color, 0.15);
      const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
      g.addColorStop(0, hexAlpha(color, 0.42));
      g.addColorStop(1, hexAlpha(color, 0.02));
      return g;
    }

    function makeAreaDataset(label, data, color, options) {
      return {
        label,
        data,
        borderColor: color,
        borderWidth: 2.2,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBorderWidth: 2,
        pointHoverBackgroundColor: getThemeColor('--bg', '#0b0e13'),
        pointHoverBorderColor: color,
        tension: 0.32,
        fill: options && options.fill === false ? false : 'origin',
        backgroundColor: function(context) {
          const chart = context.chart;
          const { ctx, chartArea } = chart;
          return buildAreaGradient(ctx, chartArea, color);
        }
      };
    }

    function updateDailyChart() {
      const windowData = getCurrentWindowData();
      const title = document.getElementById('dailyChartTitle');
      const metric = metricInfo(state.metric);
      const datasets = [];

      if (isComparing()) {
        title.textContent = metric.label + ' across compared repos';
        const compareDates = [...new Set(
          state.compareRepos.flatMap((repoName) => (getRepoByName(repoName)?.series?.dates || []))
        )].sort();
        dailyChart.data.labels = compareDates;
        state.compareRepos.forEach((repoName) => {
          const series = getRepoByName(repoName)?.series;
          if (!series) return;
          const dateMap = {};
          const values = series[metric.key] || [];
          (series.dates || []).forEach((date, idx) => { dateMap[date] = values[idx] || 0; });
          const ds = makeAreaDataset(
            getShortName(repoName),
            compareDates.map((date) => dateMap[date] || 0),
            getRepoColor(repoName),
            { fill: false }
          );
          ds.borderDash = getRepoDash(repoName);
          datasets.push(ds);
        });
      } else if (state.selectedRepo) {
        const series = getRepoByName(state.selectedRepo)?.series;
        title.textContent = metric.label + ': ' + getShortName(state.selectedRepo);
        dailyChart.data.labels = series ? series.dates : [];
        datasets.push(makeAreaDataset(
          metric.label,
          series ? (series[metric.key] || []) : [],
          metric.color
        ));
      } else {
        title.textContent = metric.label + ' over time';
        dailyChart.data.labels = windowData.daily.dates || [];
        datasets.push(makeAreaDataset(
          metric.label,
          windowData.daily[metric.key] || [],
          metric.color
        ));
      }

      dailyChart.data.datasets = datasets;
      dailyChart.update();
    }

    function updateWeekdayChart() {
      const windowData = getCurrentWindowData();
      const title = document.getElementById('weekdayChartTitle');
      const metricLabel = document.getElementById('weekdayMetricLabel');
      const metric = metricInfo(state.metric);
      const defaultLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      let labels = defaultLabels;
      let datasets = [];

      if (metricLabel) metricLabel.textContent = metric.label.toLowerCase();

      if (isComparing()) {
        title.textContent = 'Weekday rhythm — ' + metric.label.toLowerCase();
        labels = windowData.weekday?.labels || defaultLabels;
        datasets = state.compareRepos.map((repoName) => ({
          label: getShortName(repoName),
          data: buildWeekdaySummaryFromSeries({
            [repoName]: getRepoByName(repoName)?.series || { dates: [], views: [], uniques: [], clones: [], clone_uniques: [], stars_delta: [], subscribers_delta: [], forks_delta: [] }
          })[metric.key] || labels.map(() => 0),
          backgroundColor: hexAlpha(getRepoColor(repoName), 0.85),
          borderRadius: 6,
          maxBarThickness: 22
        }));
      } else {
        const weekdayData = state.selectedRepo
          ? buildWeekdaySummaryFromSeries({
              [state.selectedRepo]: getRepoByName(state.selectedRepo)?.series || { dates: [], views: [], uniques: [], clones: [], clone_uniques: [], stars_delta: [], subscribers_delta: [], forks_delta: [] }
            })
          : windowData.weekday;
        title.textContent = state.selectedRepo
          ? 'Weekday rhythm: ' + getShortName(state.selectedRepo)
          : 'Weekday rhythm';
        labels = weekdayData?.labels || defaultLabels;
        datasets = [
          {
            label: 'Avg ' + metric.label.toLowerCase(),
            data: weekdayData?.[metric.key] || labels.map(() => 0),
            backgroundColor: hexAlpha(metric.color, 0.78),
            borderRadius: 6,
            maxBarThickness: 28
          }
        ];
      }

      weekdayChart.data.labels = labels;
      weekdayChart.data.datasets = datasets;
      weekdayChart.update();
    }

    function updateStackedChart() {
      const visibleRepos = getVisibleRepos();
      const card = document.getElementById('stacked-card');
      const title = document.getElementById('stackedChartTitle');
      if (!visibleRepos.length || visibleRepos.length <= 1) {
        card.style.display = 'none';
        return;
      }
      card.style.display = 'block';

      const metric = metricInfo(state.metric);
      const repoNames = visibleRepos.map((repo) => repo.name);
      const allDates = [...new Set(
        repoNames.flatMap((repoName) => (getRepoByName(repoName)?.series?.dates || []))
      )].sort();

      if (isComparing()) {
        title.textContent = metric.label + ' across compared repos';
        stackedChart.options.scales.y.stacked = false;
        stackedChart.data.labels = allDates;
        // Render all visible repos; compared ones get bold styling, others
        // are ghosted but still appear in the legend so the user can click
        // to add them to the compare set without leaving the chart.
        stackedChart.data.datasets = repoNames.map((repoName) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          const values = series?.[metric.key] || [];
          (series?.dates || []).forEach((date, idx) => { dateMap[date] = values[idx] || 0; });
          const color = getRepoColor(repoName);
          const inSet = state.compareRepos.includes(repoName);
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => dateMap[date] || 0),
            borderColor: inSet ? color : hexAlpha(color, 0.22),
            backgroundColor: 'transparent',
            borderDash: getRepoDash(repoName),
            fill: false,
            tension: 0,
            borderWidth: inSet ? 2 : 1,
            pointRadius: 0,
            pointHoverRadius: inSet ? 4 : 3
          };
        });
      } else if (state.selectedRepo) {
        const focusName = state.selectedRepo;
        title.textContent = metric.label + ' over time: ' + getShortName(focusName);
        stackedChart.options.scales.y.stacked = false;
        stackedChart.data.labels = allDates;
        // Render every visible repo so the legend stays interactive — the
        // focused repo gets full styling, the others fade to ghosts.
        stackedChart.data.datasets = repoNames.map((repoName) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          const values = series?.[metric.key] || [];
          (series?.dates || []).forEach((date, idx) => { dateMap[date] = values[idx] || 0; });
          const color = getRepoColor(repoName);
          const isFocus = repoName === focusName;
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => dateMap[date] || 0),
            borderColor: isFocus ? color : hexAlpha(color, 0.28),
            backgroundColor: isFocus ? hexAlpha(color, 0.32) : 'transparent',
            borderDash: getRepoDash(repoName),
            fill: isFocus ? 'origin' : false,
            tension: isFocus ? 0.28 : 0,
            borderWidth: isFocus ? 2.4 : 1,
            pointRadius: 0,
            pointHoverRadius: isFocus ? 4 : 3
          };
        });
      } else {
        title.textContent = metric.label + ' by repository';
        stackedChart.options.scales.y.stacked = true;
        stackedChart.data.labels = allDates;
        stackedChart.data.datasets = repoNames.map((repoName, idx) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          const values = series?.[metric.key] || [];
          (series?.dates || []).forEach((date, seriesIdx) => { dateMap[date] = values[seriesIdx] || 0; });
          const color = palette[idx % palette.length];
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => dateMap[date] || 0),
            borderColor: color,
            backgroundColor: hexAlpha(color, 0.55),
            borderDash: getRepoDash(repoName),
            fill: true,
            tension: 0,
            borderWidth: 1,
            pointRadius: 0,
            pointHoverRadius: 4
          };
        });
      }
      stackedChart.update();
    }

    function sortRows(rows, key, dir, labelKey) {
      const factor = dir === 'asc' ? 1 : -1;
      const numeric = key === 'count' || key === 'uniques' || key === 'share';
      return rows.slice().sort((a, b) => {
        const av = numeric ? Number(a[key] || 0) : String(a[labelKey] || '').toLowerCase();
        const bv = numeric ? Number(b[key] || 0) : String(b[labelKey] || '').toLowerCase();
        if (av < bv) return -1 * factor;
        if (av > bv) return 1 * factor;
        return 0;
      });
    }

    function renderSnapshotTable(elId, rows, options) {
      const el = document.getElementById(elId);
      if (!rows.length) {
        el.innerHTML = '<p class="empty-msg">' + escapeHtml(options.emptyMsg) + '</p>';
        return;
      }
      const labelKey = options.labelKey;
      const labelHeader = options.labelHeader;
      const sortKey = options.sortKey || 'count';
      const sortDir = options.sortDir || 'desc';

      const total = rows.reduce((acc, r) => acc + Number(r.count || 0), 0);
      const sorted = sortRows(rows, sortKey, sortDir, labelKey);
      const arrow = (k) => sortKey === k ? (sortDir === 'asc' ? '↑' : '↓') : '↕';
      const head = (k, label, num) => {
        const cls = ['sortable', sortKey === k ? 'active' : '', num ? 'num' : ''].filter(Boolean).join(' ');
        return `<th class="${cls}" data-sort="${k}"><span>${label}</span><span class="arrow">${arrow(k)}</span></th>`;
      };
      let html = '<div class="table-wrap"><table><thead><tr>' +
        head('label', labelHeader) +
        head('count', 'Views', true) +
        head('uniques', 'Uniques', true) +
        head('share', 'Share', true) +
        '</tr></thead><tbody>';

      sorted.forEach((row) => {
        const label = (options.formatLabel ? options.formatLabel(row) : row[labelKey]) || '';
        const sharePct = total > 0 ? (Number(row.count || 0) / total) * 100 : 0;
        html += '<tr>' +
          '<td title="' + escapeHtml(label) + '">' + escapeHtml(label) + '</td>' +
          '<td class="num mono">' + formatNumber(row.count) + '</td>' +
          '<td class="num mono">' + formatNumber(row.uniques) + '</td>' +
          '<td class="num mono">' + sharePct.toFixed(1) + '%</td>' +
          '</tr>';
      });
      html += '</tbody></table></div>';
      el.innerHTML = html;

      el.querySelectorAll('th.sortable').forEach((th) => {
        th.addEventListener('click', function() {
          const key = th.dataset.sort === 'label' ? 'label' : th.dataset.sort;
          options.onSort(key);
        });
      });
    }

    function renderReferrerTable(rows) {
      renderSnapshotTable('referrer-table', rows, {
        labelKey: 'referrer',
        labelHeader: 'Referrer',
        sortKey: state.referrerSortKey || 'count',
        sortDir: state.referrerSortDir || 'desc',
        emptyMsg: 'No referrer data yet — referrers appear after a few collection runs.',
        onSort: function(key) {
          if (state.referrerSortKey === key) {
            state.referrerSortDir = state.referrerSortDir === 'desc' ? 'asc' : 'desc';
          } else {
            state.referrerSortKey = key;
            state.referrerSortDir = key === 'label' ? 'asc' : 'desc';
          }
          updateDashboard();
        }
      });
    }

    function renderPathsTable(rows) {
      const el = document.getElementById('paths-table');
      if (!rows.length) {
        el.innerHTML = '<p class="empty-msg">No path data yet — popular pages appear after a few collection runs.</p>';
        return;
      }
      const sortKey = state.pathSortKey || 'count';
      const sortDir = state.pathSortDir || 'desc';
      const factor = sortDir === 'asc' ? 1 : -1;
      const total = rows.reduce((acc, r) => acc + Number(r.count || 0), 0);
      const sorted = rows.slice().sort((a, b) => {
        const numeric = sortKey === 'count' || sortKey === 'uniques' || sortKey === 'share';
        const av = numeric ? Number(a[sortKey] || 0) : String(a[sortKey] || '').toLowerCase();
        const bv = numeric ? Number(b[sortKey] || 0) : String(b[sortKey] || '').toLowerCase();
        if (av < bv) return -1 * factor;
        if (av > bv) return 1 * factor;
        return 0;
      });
      const arrow = (k) => sortKey === k ? (sortDir === 'asc' ? '↑' : '↓') : '↕';
      const head = (k, label, num) => {
        const cls = ['sortable', sortKey === k ? 'active' : '', num ? 'num' : ''].filter(Boolean).join(' ');
        return `<th class="${cls}" data-sort="${k}"><span>${label}</span><span class="arrow">${arrow(k)}</span></th>`;
      };
      let html = '<div class="table-wrap"><table><thead><tr>' +
        head('repo', 'Repository') +
        head('content', 'Content') +
        head('count', 'Views', true) +
        head('uniques', 'Uniques', true) +
        head('share', 'Share', true) +
        '</tr></thead><tbody>';
      sorted.forEach((row) => {
        const repo = row.repo || '';
        const content = row.content || row.title || row.path || '';
        const sharePct = total > 0 ? (Number(row.count || 0) / total) * 100 : 0;
        html += '<tr>' +
          '<td title="' + escapeHtml(repo) + '">' + escapeHtml(getShortName(repo)) + '</td>' +
          '<td title="' + escapeHtml(row.path || content) + '">' + escapeHtml(content) + '</td>' +
          '<td class="num mono">' + formatNumber(row.count) + '</td>' +
          '<td class="num mono">' + formatNumber(row.uniques) + '</td>' +
          '<td class="num mono">' + sharePct.toFixed(1) + '%</td>' +
          '</tr>';
      });
      html += '</tbody></table></div>';
      el.innerHTML = html;
      el.querySelectorAll('th.sortable').forEach((th) => {
        th.addEventListener('click', function() {
          const key = th.dataset.sort;
          if (state.pathSortKey === key) {
            state.pathSortDir = state.pathSortDir === 'desc' ? 'asc' : 'desc';
          } else {
            state.pathSortKey = key;
            state.pathSortDir = key === 'repo' || key === 'content' ? 'asc' : 'desc';
          }
          updateDashboard();
        });
      });
    }

    function classifyInsight(item) {
      if (item.kind === 'spike') {
        return item.direction === 'spiked' ? 'up' : 'down';
      }
      if (item.kind === 'trend') {
        if (item.pct === null || item.pct === undefined) return 'up';
        if (item.pct > 2) return 'up';
        if (item.pct < -2) return 'down';
        return 'neutral';
      }
      if (item.kind === 'growth') {
        return item.subtype === 'high_attention_low_interest' || item.subtype === 'traffic_without_downstream_growth'
          ? 'neutral'
          : 'up';
      }
      return 'neutral';
    }

    function renderInsights() {
      const container = document.getElementById('insights-list');
      if (!container) return;

      const structured = (state.payload && state.payload.insights_v2) || [];
      const fallback = (state.payload && state.payload.insights) || [];

      if (!structured.length && !fallback.length) {
        container.innerHTML = '<p class="empty-msg">Needs more data to surface a signal yet — check back after a few more collection runs.</p>';
        return;
      }

      const items = structured.length ? structured : fallback.map((text) => ({ kind: 'legacy', text }));
      const ul = document.createElement('ul');
      ul.className = 'insights-list';

      items.forEach((item) => {
        const li = document.createElement('li');
        const tone = classifyInsight(item);
        li.className = 'insight-item ' + tone;
        li.tabIndex = 0;

        const repo = item.repo || '';
        const shortRepo = getShortName(repo);
        const icon = tone === 'up' ? '▲' : tone === 'down' ? '▼' : '•';

        let headline = '';
        let meta = '';
        let pctLabel = '';

        if (item.kind === 'trend') {
          const verb = (item.pct === null || item.pct === undefined)
            ? 'started getting'
            : (item.pct > 0 ? 'is up on' : 'is down on');
          headline = `<span class="repo">${escapeHtml(shortRepo)}</span> ${verb} ${item.metric}`;
          const window = item.window_days || 7;
          meta = `${formatNumber(item.prior)} → ${formatNumber(item.current)} over ${window}d (${item.delta >= 0 ? '+' : ''}${formatNumber(item.delta)})`;
          if (item.pct === null || item.pct === undefined) {
            pctLabel = 'new';
          } else {
            const sign = item.pct >= 0 ? '+' : '';
            pctLabel = `${sign}${Math.round(item.pct)}%`;
          }
        } else if (item.kind === 'spike') {
          headline = `<span class="repo">${escapeHtml(shortRepo)}</span> ${item.metric} ${item.direction} versus baseline`;
          meta = `latest ${formatNumber(item.current)} vs trailing median ${formatNumber(Math.round(item.baseline))}`;
          pctLabel = item.direction === 'spiked' ? '↑ spike' : '↓ drop';
        } else if (item.kind === 'growth') {
          const growthText = escapeHtml(item.text || '').replace(/^`[^`]+`\\s*/, '');
          headline = '<span class="repo">' + escapeHtml(shortRepo) + '</span> ' + growthText;
          const parts = [];
          if (item.traffic !== undefined) parts.push(`${formatNumber(item.traffic)} views`);
          if (item.visitors !== undefined) parts.push(`${formatNumber(item.visitors)} visitors`);
          if (item.clones !== undefined) parts.push(`${formatNumber(item.clones)} clones`);
          if (item.downstream_delta !== undefined) parts.push(`${formatSigned(item.downstream_delta)} downstream`);
          if (item.delta !== undefined) parts.push(`${formatSigned(item.delta)} ${item.metric}`);
          meta = parts.join(' · ');
          pctLabel = item.subtype ? 'growth' : '';
        } else {
          headline = escapeHtml(item.text || '');
          meta = '';
          pctLabel = '';
        }

        li.innerHTML =
          `<div class="insight-icon" aria-hidden="true">${icon}</div>` +
          `<div class="insight-body"><div class="insight-headline">${headline}</div>` +
          (meta ? `<div class="insight-meta mono">${escapeHtml(meta)}</div>` : '') +
          `</div>` +
          (pctLabel ? `<div class="insight-pct">${escapeHtml(pctLabel)}</div>` : '');

        if (repo) {
          li.setAttribute('role', 'button');
          li.setAttribute('aria-label', `Focus on ${shortRepo}`);
          const focus = function() { selectRepo(repo); window.scrollTo({ top: 0, behavior: 'smooth' }); };
          li.addEventListener('click', focus);
          li.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); focus(); }
          });
        } else {
          li.style.cursor = 'default';
        }

        ul.appendChild(li);
      });

      container.innerHTML = '';
      container.appendChild(ul);
    }

    function buildRepoSparkSVG(values, color) {
      if (!values || values.length < 2) return '';
      const { line, area } = buildSparklinePath(values, 92, 26);
      return `<svg class="repo-spark" viewBox="0 0 92 26" preserveAspectRatio="none" aria-hidden="true">` +
        `<path class="area" d="${area}" fill="${color}"></path>` +
        `<path class="line" d="${line}" stroke="${color}"></path></svg>`;
    }

    function getRepoSortKey(repo, key) {
      if (key === 'name') return repo.name.toLowerCase();
      if (key === 'growth') return Number(repo.stars_delta || 0) + Number(repo.subscribers_delta || 0) + Number(repo.forks_delta || 0);
      return Number(repo[key] || 0);
    }

    function sortRepos(repos, key, dir) {
      const factor = dir === 'asc' ? 1 : -1;
      const out = repos.slice();
      out.sort((a, b) => {
        const av = getRepoSortKey(a, key);
        const bv = getRepoSortKey(b, key);
        if (av < bv) return -1 * factor;
        if (av > bv) return 1 * factor;
        return a.name.localeCompare(b.name);
      });
      return out;
    }

    function setRepoSort(key) {
      if (state.repoSortKey === key) {
        state.repoSortDir = state.repoSortDir === 'desc' ? 'asc' : 'desc';
      } else {
        state.repoSortKey = key;
        state.repoSortDir = key === 'name' ? 'asc' : 'desc';
      }
      renderRepoTable();
    }

    function renderRepoStrip() {
      const strip = document.getElementById('repo-strip');
      const card = document.getElementById('repo-strip-card');
      const hint = document.getElementById('repo-strip-hint');
      if (!strip || !card) return;

      const visible = getVisibleRepos();
      if (visible.length <= 1) {
        card.style.display = 'none';
        return;
      }
      card.style.display = 'grid';

      const maxDays = Math.max(...visible.map((r) => Number(r.days || 0)), 1);
      strip.innerHTML = '';

      visible.forEach((repo) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        const isSelected = state.selectedRepo === repo.name;
        const isCompared = state.compareRepos.includes(repo.name);
        chip.className = 'repo-chip' + (isSelected ? ' selected' : '') + (isCompared ? ' compared' : '');
        const color = getRepoColor(repo.name);
        chip.style.setProperty('--chip-color', color);
        chip.dataset.repo = repo.name;
        chip.setAttribute('aria-pressed', (isSelected || isCompared) ? 'true' : 'false');
        const showDays = Number(repo.days || 0) > 0 && Number(repo.days || 0) < maxDays;
        const meta = showDays ? `<span class="chip-meta">${repo.days}d</span>` : '';
        const mark = isCompared ? '✓' : (isSelected ? '◉' : '');
        chip.innerHTML =
          `<span class="chip-dot" aria-hidden="true"></span>` +
          `<span>${escapeHtml(getShortName(repo.name))}</span>` +
          meta +
          (mark ? `<span class="chip-mark" aria-hidden="true">${mark}</span>` : '');

        const onSelect = function(event) {
          const modifier = !!(event && (event.metaKey || event.ctrlKey || event.shiftKey));
          activateRepo(repo.name, modifier);
        };
        chip.addEventListener('click', onSelect);
        chip.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            activateRepo(repo.name, !!(e.metaKey || e.ctrlKey || e.shiftKey));
          }
        });
        strip.appendChild(chip);
      });

      if (hint) {
        if (isComparing()) hint.textContent = `Comparing ${state.compareRepos.length} · ⌘/Ctrl-click to add or remove`;
        else if (state.selectedRepo) hint.textContent = `Focused on ${getShortName(state.selectedRepo)} · click again to clear`;
        else hint.textContent = 'Click to focus · ⌘/Ctrl-click to compare';
      }
    }

    function renderRepoTable() {
      const container = document.getElementById('repo-table');
      const visible = getVisibleRepos();
      const section = document.getElementById('repo-section');
      if (!visible.length) {
        section.style.display = 'none';
        container.innerHTML = '<p class="empty-msg">No repository totals yet.</p>';
        return;
      }
      if (visible.length <= 1) {
        section.style.display = 'block';
      } else {
        section.style.display = 'block';
      }

      const metric = metricInfo(state.metric);
      const sortKey = state.repoSortKey || metric.key;
      const sortDir = state.repoSortDir || 'desc';
      const repos = sortRepos(visible, sortKey, sortDir);

      const totalForMetric = visible.reduce((acc, r) => acc + Number(r[metric.key] || 0), 0);
      const maxForMetric = Math.max(...visible.map((r) => Number(r[metric.key] || 0)), 1);
      const maxDays = Math.max(...visible.map((r) => Number(r.days || 0)), 1);

      const arrow = (key) => sortKey === key ? (sortDir === 'asc' ? '↑' : '↓') : '↕';
      const headCell = (key, label, numeric) => {
        const cls = ['sortable', sortKey === key ? 'active' : '', numeric ? 'num' : ''].filter(Boolean).join(' ');
        return `<th class="${cls}" data-sort="${key}"><span>${label}</span><span class="arrow">${arrow(key)}</span></th>`;
      };

      let html = '<div class="repo-table-wrap"><table><thead><tr>' +
        '<th class="checkbox-col"></th>' +
        headCell('name', 'Repository') +
        headCell('views', 'Views', true) +
        headCell('uniques', 'Visitors', true) +
        headCell('clones', 'Clones', true) +
        headCell('growth', 'Growth', true) +
        '<th>Trend</th>' +
        `<th>Share of ${escapeHtml(metric.label.toLowerCase())}</th>` +
        '</tr></thead><tbody>';

      repos.forEach((repo) => {
        const isSelected = state.selectedRepo === repo.name;
        const isCompared = state.compareRepos.includes(repo.name);
        const dimmed = state.selectedRepo && !isSelected;
        const rowClass = [
          'repo-row',
          isSelected ? 'selected' : '',
          isCompared ? 'compared' : '',
          dimmed ? 'dimmed' : ''
        ].filter(Boolean).join(' ');
        const checked = isCompared ? ' checked' : '';
        const value = Number(repo[metric.key] || 0);
        const sharePct = totalForMetric > 0 ? (value / totalForMetric) * 100 : 0;
        const barPct = Math.max(2, (value / maxForMetric) * 100);
        const repoColor = getRepoColor(repo.name);
        const sparkValues = (repo.series && repo.series[metric.key]) || [];
        const sparkSVG = buildRepoSparkSVG(sparkValues, metric.color);

        const showDaysMeta = Number(repo.days || 0) > 0 && Number(repo.days || 0) < maxDays;
        const daysMeta = showDaysMeta ? `<span class="repo-name-meta">tracked ${repo.days}d of ${maxDays}d</span>` : '';
        html += `
          <tr class="${rowClass}" data-repo="${repo.name}" tabindex="0" role="button" aria-pressed="${isSelected}" aria-label="Focus on ${escapeHtml(getShortName(repo.name))}">
            <td class="checkbox-col"><input type="checkbox" data-repo="${repo.name}"${checked} aria-label="Compare ${escapeHtml(getShortName(repo.name))}"></td>
            <td class="repo-name">
              <span class="repo-name-wrap">
                <span class="repo-color-dot" style="background:${repoColor}"></span>
                <span>${escapeHtml(repo.name)}${daysMeta}</span>
              </span>
            </td>
            <td class="num mono">${formatNumber(repo.views)}</td>
            <td class="num mono">${formatNumber(repo.uniques)}</td>
            <td class="num mono">${formatNumber(repo.clones)}</td>
            <td class="num mono">
              <span class="growth-cell">
                <span class="growth-row"><strong>${formatSigned(repo.stars_delta)}</strong><span class="growth-label">stars</span><span class="growth-total">(${formatNumber(repo.stars)})</span></span>
                <span class="growth-row"><strong>${formatSigned(repo.subscribers_delta)}</strong><span class="growth-label">watchers</span><span class="growth-total">(${formatNumber(repo.subscribers)})</span></span>
                <span class="growth-row"><strong>${formatSigned(repo.forks_delta)}</strong><span class="growth-label">forks</span><span class="growth-total">(${formatNumber(repo.forks)})</span></span>
              </span>
            </td>
            <td>${sparkSVG}</td>
            <td>
              <div class="repo-share">
                <div class="repo-bar-track" aria-hidden="true">
                  <div class="repo-bar" style="width:${barPct.toFixed(1)}%; background: linear-gradient(90deg, ${metric.color}, ${hexAlpha(metric.color, 0.6)});"></div>
                </div>
                <span class="repo-share-pct">${sharePct.toFixed(1)}%</span>
              </div>
            </td>
          </tr>`;
      });
      html += '</tbody></table></div>';
      container.innerHTML = html;

      container.querySelectorAll('tr[data-repo]').forEach((row) => {
        const select = function(event) {
          if (event && event.target && event.target.closest('input[type="checkbox"]')) return;
          const modifier = !!(event && (event.metaKey || event.ctrlKey || event.shiftKey));
          activateRepo(row.dataset.repo, modifier);
        };
        row.addEventListener('click', select);
        row.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(e); }
        });
      });
      container.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        input.addEventListener('click', function(event) { event.stopPropagation(); });
        input.addEventListener('change', function() { toggleRepoCompare(input.dataset.repo, input.checked); });
      });
      container.querySelectorAll('th.sortable').forEach((th) => {
        th.addEventListener('click', function() { setRepoSort(th.dataset.sort); });
      });
    }

    function syncUrlHash() {
      try {
        const params = new URLSearchParams();
        if (state.metric && state.metric !== 'views') params.set('metric', state.metric);
        if (getSelectedWindow() !== getDefaultWindow()) params.set('window', getSelectedWindow());
        if (state.minActivity && state.minActivity !== (state.payload?.meta?.default_min_activity || 1)) params.set('min', String(state.minActivity));
        if (state.selectedRepo) params.set('focus', getShortName(state.selectedRepo));
        if (state.compareRepos.length >= 2) params.set('compare', state.compareRepos.map(getShortName).join(','));
        const hash = params.toString();
        const next = hash ? '#' + hash : '';
        if (window.location.hash !== next) {
          history.replaceState(null, '', window.location.pathname + window.location.search + next);
        }
      } catch (_e) { /* ignore */ }
    }

    function applyUrlHash() {
      if (!state.payload) return;
      try {
        const raw = (window.location.hash || '').replace(/^#/, '');
        if (!raw) return;
        const params = new URLSearchParams(raw);
        const metric = params.get('metric');
        if (metric && METRICS[metric]) state.metric = metric;
        const windowParam = normalizeWindow(params.get('window'));
        if (windowParam) state.window = windowParam;
        const range = params.get('range');
        if (!windowParam && range === 'recent') state.window = DEFAULT_WINDOW;
        if (!windowParam && range === 'all') state.window = 'all';
        const min = Number(params.get('min'));
        if (Number.isFinite(min) && min >= 0) state.minActivity = Math.floor(min);

        const repoNames = (state.payload.repos || []).map((r) => r.name);
        const matchByShort = (short) => repoNames.find((n) => getShortName(n) === short) || null;

        const focus = params.get('focus');
        if (focus) {
          const m = matchByShort(focus);
          if (m) state.selectedRepo = m;
        }
        const compare = params.get('compare');
        if (compare) {
          const tokens = compare.split(',').map((s) => s.trim()).filter(Boolean);
          const matched = tokens.map(matchByShort).filter(Boolean);
          if (matched.length >= 2) {
            state.compareRepos = matched;
            state.selectedRepo = null;
          }
        }
      } catch (_e) { /* ignore */ }
    }

    function updateDashboard() {
      if (!state.payload) {
        return;
      }
      sanitizeSelection();
      syncUrlHash();
      const dashboardApp = document.getElementById('dashboard-app');
      dashboardApp.style.display = 'block';
      ensureCharts();
      updateControls();
      updateMetricTabs();
      setText('updated-text', buildUpdatedText(state.payload));
      updateToolbar();
      updateStats();
      updateDailyChart();
      updateWeekdayChart();
      updateStackedChart();
      renderReferrerTable(getCurrentReferrerRows());
      renderPathsTable(getCurrentPathRows());
      renderMomentum();
      renderInsights();
      renderRepoStrip();
      renderRepoTable();
    }

    function renderDashboard(payload) {
      state.payload = payload;
      state.window = getDefaultWindow();
      state.minActivity = payload.meta?.default_min_activity || 1;
      state.selectedRepo = null;
      state.compareRepos = [];
      const thresholdInput = document.getElementById('thresholdInput');
      if (thresholdInput) {
        thresholdInput.addEventListener('change', function() {
          setThreshold(thresholdInput.value);
        });
        thresholdInput.addEventListener('input', function() {
          document.getElementById('thresholdValue').textContent = formatNumber(Math.max(0, Math.floor(Number(thresholdInput.value || 0))));
        });
      }
      document.querySelectorAll('[data-window]').forEach((btn) => {
        btn.addEventListener('click', function() { setWindow(btn.dataset.window); });
      });
      document.querySelectorAll('.metric-tab').forEach((btn) => {
        btn.addEventListener('click', function() { setMetric(btn.dataset.metric); });
      });
      const themeToggle = document.getElementById('themeToggle');
      if (themeToggle) themeToggle.addEventListener('click', toggleTheme);
      // Sync the toggle button's icon/label with the bootstrap-applied theme.
      applyTheme(preferredTheme(), false);
      try {
        const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)');
        if (mq && mq.addEventListener) {
          mq.addEventListener('change', function() {
            try {
              const saved = localStorage.getItem(THEME_KEY);
              if (!saved) applyTheme(mq.matches ? 'light' : 'dark', false);
            } catch (_e) { /* ignore */ }
          });
        }
      } catch (_e) { /* ignore */ }
      applyUrlHash();
      window.addEventListener('hashchange', function() {
        applyUrlHash();
        updateDashboard();
      });
      updateDashboard();
    }
"""

SECURE_RUNTIME_JS = """
    const EXPECTED_PAYLOAD_VERSION = 1;
    const EXPECTED_CIPHER = 'AES-GCM';
    const EXPECTED_KDF_NAME = 'PBKDF2';
    const EXPECTED_KDF_HASH = 'SHA-256';
    const EXPECTED_KDF_ITERATIONS = __PBKDF2_ITERATIONS__;
    const EXPECTED_SALT_BYTES = 16;
    const EXPECTED_IV_BYTES = 12;

    const encryptedPayload = JSON.parse(
      document.getElementById('encrypted-payload').textContent
    );
    const authShell = document.getElementById('auth-shell');
    const unlockForm = document.getElementById('unlock-form');
    const dashboardKeyInput = document.getElementById('dashboard-key');
    const unlockButton = document.getElementById('unlock-button');
    const unlockStatus = document.getElementById('unlock-status');

    function setUnlockStatus(message, type) {
      unlockStatus.textContent = message;
      unlockStatus.className = 'auth-status' + (type ? ' ' + type : '');
    }

    function b64ToBytes(value) {
      if (typeof value !== 'string' || !value) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      const binary = atob(value);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
      }
      return bytes;
    }

    function validateEncryptedPayload(payload) {
      if (!payload || payload.version !== EXPECTED_PAYLOAD_VERSION) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      if (payload.cipher !== EXPECTED_CIPHER) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      if (
        !payload.kdf ||
        payload.kdf.name !== EXPECTED_KDF_NAME ||
        payload.kdf.hash !== EXPECTED_KDF_HASH ||
        payload.kdf.iterations !== EXPECTED_KDF_ITERATIONS
      ) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      const salt = b64ToBytes(payload.salt);
      const iv = b64ToBytes(payload.iv);
      const ciphertext = b64ToBytes(payload.ciphertext);
      if (
        salt.length !== EXPECTED_SALT_BYTES ||
        iv.length !== EXPECTED_IV_BYTES ||
        ciphertext.length === 0
      ) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      return { salt, iv, ciphertext };
    }

    async function decryptDashboardPayload(dashboardKey, payload) {
      const validatedPayload = validateEncryptedPayload(payload);
      const encoder = new TextEncoder();
      const keyMaterial = await crypto.subtle.importKey(
        'raw',
        encoder.encode(dashboardKey),
        'PBKDF2',
        false,
        ['deriveKey']
      );
      const key = await crypto.subtle.deriveKey(
        {
          name: EXPECTED_KDF_NAME,
          salt: validatedPayload.salt,
          iterations: EXPECTED_KDF_ITERATIONS,
          hash: EXPECTED_KDF_HASH
        },
        keyMaterial,
        { name: EXPECTED_CIPHER, length: 256 },
        false,
        ['decrypt']
      );
      const plaintext = await crypto.subtle.decrypt(
        { name: EXPECTED_CIPHER, iv: validatedPayload.iv },
        key,
        validatedPayload.ciphertext
      );
      return JSON.parse(new TextDecoder().decode(plaintext));
    }

    if (!window.crypto || !window.crypto.subtle) {
      unlockButton.disabled = true;
      setUnlockStatus(
        'This browser cannot decrypt the dashboard here. Open it over HTTPS or use the standalone artifact.',
        'error'
      );
    } else {
      dashboardKeyInput.focus();
    }

    unlockForm.addEventListener('submit', async function(event) {
      event.preventDefault();
      if (!dashboardKeyInput.value) {
        setUnlockStatus('Enter the dashboard key.', 'error');
        return;
      }

      unlockButton.disabled = true;
      setUnlockStatus('Unlocking dashboard...', 'pending');

      try {
        const payload = await decryptDashboardPayload(
          dashboardKeyInput.value,
          encryptedPayload
        );
        authShell.style.display = 'none';
        renderDashboard(payload);
        setUnlockStatus('', '');
      } catch (error) {
        unlockButton.disabled = false;
        dashboardKeyInput.select();
        setUnlockStatus('Wrong dashboard key or corrupted payload.', 'error');
      }
    });
"""


def _load_vendored_chart_js():
    """Load vendored Chart.js and escape closing script tags defensively."""
    with open(VENDORED_CHART_JS_PATH) as f:
        return f.read().replace("</script", "<\\/script")


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


def _build_font_face_styles() -> str:
    """Return self-contained @font-face rules for vendored dashboard fonts."""
    return (
        _font_face_rule("Inter", VENDORED_INTER_FONT_PATH, "100 900")
        + "\n"
        + _font_face_rule("JetBrains Mono", VENDORED_MONO_FONT_PATH, "100 800")
    )


def _publish_vendored_chart_js(output_path: str) -> str:
    """Copy vendored Chart.js beside the published dashboard."""
    asset_path = Path(output_path).parent / PUBLISHED_CHART_JS_PATH
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(VENDORED_CHART_JS_PATH, asset_path)
    return PUBLISHED_CHART_JS_PATH


def _load_access_mode():
    """Return the configured dashboard access mode."""
    mode = os.environ.get(ACCESS_MODE_ENV, ACCESS_MODE_PUBLIC).strip().lower()
    if not mode:
        mode = ACCESS_MODE_PUBLIC
    if mode == ACCESS_MODE_LEGACY_SHARED_SECRET:
        mode = ACCESS_MODE_ENCRYPTED
    if mode not in {ACCESS_MODE_PUBLIC, ACCESS_MODE_ENCRYPTED}:
        raise ValueError(
            f"Unsupported {ACCESS_MODE_ENV}={mode!r}. " +
            f"Use {ACCESS_MODE_PUBLIC!r} or {ACCESS_MODE_ENCRYPTED!r}."
        )
    return mode


def _build_repo_series(daily_rows):
    """Build per-repo daily series for drill-down and comparison modes."""
    by_repo = defaultdict(lambda: defaultdict(lambda: {
        "views": 0,
        "uniques": 0,
        "clones": 0,
        "clone_uniques": 0,
    }))

    for row in daily_rows:
        bucket = by_repo[row["repo"]][row["ts"]]
        bucket["views"] += int(row.get("views_count", 0))
        bucket["uniques"] += int(row.get("views_uniques", 0))
        bucket["clones"] += int(row.get("clones_count", 0))
        bucket["clone_uniques"] += int(row.get("clones_uniques", 0))

    series = {}
    for repo, values_by_date in by_repo.items():
        dates = sorted(values_by_date)
        series[repo] = {
          "dates": dates,
          "views": [values_by_date[date]["views"] for date in dates],
          "uniques": [values_by_date[date]["uniques"] for date in dates],
          "clones": [values_by_date[date]["clones"] for date in dates],
          "clone_uniques": [values_by_date[date]["clone_uniques"] for date in dates],
        }
    return series


def _build_weekday_summary(daily_rows):
    """Build average views/clones by weekday for a daily row collection."""
    daily_totals = defaultdict(lambda: {"views": 0, "clones": 0})
    weekday_totals = {
        label: {"views": 0, "clones": 0, "samples": 0}
        for label in WEEKDAY_LABELS
    }

    for row in daily_rows:
        bucket = daily_totals[row["ts"]]
        bucket["views"] += int(row.get("views_count", 0))
        bucket["clones"] += int(row.get("clones_count", 0))

    for ts, totals in daily_totals.items():
        weekday_label = WEEKDAY_LABELS[datetime.strptime(ts, "%Y-%m-%d").weekday()]
        bucket = weekday_totals[weekday_label]
        bucket["views"] += totals["views"]
        bucket["clones"] += totals["clones"]
        bucket["samples"] += 1

    return {
        "labels": WEEKDAY_LABELS,
        "views": [
            round(
                weekday_totals[label]["views"] / weekday_totals[label]["samples"],
                1,
            ) if weekday_totals[label]["samples"] else 0
            for label in WEEKDAY_LABELS
        ],
        "clones": [
            round(
                weekday_totals[label]["clones"] / weekday_totals[label]["samples"],
                1,
            ) if weekday_totals[label]["samples"] else 0
            for label in WEEKDAY_LABELS
        ],
    }


def _build_repo_weekday_summary(daily_rows):
    """Build per-repo average weekday summaries for focus/compare views."""
    rows_by_repo = defaultdict(list)
    for row in daily_rows:
        rows_by_repo[row["repo"]].append(row)
    return {
        repo: _build_weekday_summary(rows)
        for repo, rows in rows_by_repo.items()
    }


def _latest_snapshot_by_repo(rows):
    """Return latest snapshot rows grouped by repo for rolling snapshot families."""
    latest_by_repo = {}
    for row in rows:
        repo = row["repo"]
        captured_at = row.get("captured_at", "")
        if captured_at > latest_by_repo.get(repo, ""):
            latest_by_repo[repo] = captured_at

    grouped = defaultdict(list)
    for row in rows:
        if row.get("captured_at", "") == latest_by_repo.get(row["repo"], ""):
            grouped[row["repo"]].append(row)
    return dict(grouped)


def _build_payload(
    now,
    totals,
    dates,
    series,
    per_repo,
    referrers,
    paths,
    repo_series,
    weekday,
    repo_weekday,
    repo_referrers,
    repo_paths,
    growth,
    insights,
    insights_structured,
):
    """Build a JSON-safe dashboard payload shared by all output modes."""
    repos = []
    for row in per_repo:
        series_row = repo_series.get(row["repo"], {})
        repos.append({
            "name": row["repo"],
            "views": row["total_views"],
            "uniques": row["total_uniques"],
            "clones": row["total_clones"],
            "clone_uniques": row["total_clone_uniques"],
            "days": len(series_row.get("dates", [])),
        })

    return {
        "meta": {
            "recent_window_days": 14,
            "window_presets": [7, 14, 30, 90, "all"],
            "default_window": "14",
            "default_range": "recent",
            "default_min_activity": 1,
        },
        "generated_at": now,
        "totals": {
            "repo_count": len(totals["repos"]),
            "days_tracked": totals["days_tracked"],
            "total_views": totals["total_views"],
            "total_uniques": totals["total_uniques"],
            "total_clones": totals["total_clones"],
            "total_clone_uniques": totals["total_clone_uniques"],
        },
        "daily": {
            "dates": dates,
            "views": series["views"],
            "uniques": series["uniques"],
            "clones": series["clones"],
            "clone_uniques": series["clone_uniques"],
        },
        "weekday": weekday,
        "repos": repos,
        "repo_series": repo_series,
        "repo_weekday": repo_weekday,
        "referrers": referrers,
        "paths": paths,
        "repo_referrers": repo_referrers,
        "repo_paths": repo_paths,
        "growth": {
            "window_days": growth["window_days"],
            "cutoff": growth["cutoff"],
            "latest_date": growth["latest_date"],
            "totals": growth["totals"],
            "series": growth["series"],
            "per_repo": growth["per_repo"],
        },
        "insights": insights,
        "insights_v2": insights_structured,
    }


def _encrypt_payload(payload, dashboard_key):
    """Encrypt the dashboard payload for encrypted Pages mode."""
    salt = os.urandom(PBKDF2_SALT_BYTES)
    iv = os.urandom(AES_GCM_IV_BYTES)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = kdf.derive(dashboard_key.encode("utf-8"))
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(iv, plaintext, None)
    return {
        "version": 1,
        "cipher": "AES-GCM",
        "kdf": {
            "name": "PBKDF2",
            "hash": "SHA-256",
            "iterations": PBKDF2_ITERATIONS,
        },
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def _load_update_notice():
    raw = os.environ.get(UPDATE_NOTICE_ENV, "")
    if not raw:
        return None
    try:
        notice = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(notice, dict):
        return None
    version = str(notice.get("version") or "").strip()
    title = str(notice.get("title") or "").strip()
    url = str(notice.get("url") or "").strip()
    summary = str(notice.get("summary") or "").strip()
    if not version or not title or not url:
        return None
    return {"version": version, "title": title, "url": url, "summary": summary}


def _render_update_notice():
    notice = _load_update_notice()
    if not notice:
        return ""
    summary = f" {html.escape(notice['summary'])}" if notice["summary"] else ""
    return (
        '\n  <div class="update-notice" role="note">' +
        f"<strong>{html.escape(notice['title'])}</strong>" +
        f"{summary} " +
        f'<a href="{html.escape(notice["url"], quote=True)}">' +
        f'View {html.escape(notice["version"])}</a>.' +
        "</div>\n"
    )


def _build_dashboard_shell(updated_text, stat_values, hidden=False):
    """Build the shared dashboard markup used by public and secure pages."""
    hidden_attr = ' style="display:none;"' if hidden else ""
    return f"""
  <div id="dashboard-app"{hidden_attr}>
    <div class="hero">
      <div class="hero-copy">
        <p class="tagline"><span class="pulse-dot" aria-hidden="true"></span><span>A traffic report for your repos</span></p>
        <div class="brand-lockup">
          <h1 class="brand">reponomics<span class="accent">.</span></h1>
          <div class="brand-eyebrow">Dashboard</div>
        </div>
        <p class="updated" id="updated-text">{updated_text}</p>
      </div>
      <div class="hero-toolbar">
        <span class="status-badge active" id="activeBadge"></span>
        <span class="status-badge compare" id="compareBadge"></span>
        <button class="toolbar-button" id="clearSelectionBtn" type="button" onclick="clearSelection()">Clear selection</button>
        <button class="toolbar-button theme-toggle visible" id="themeToggle" type="button" aria-label="Toggle light/dark theme" title="Toggle theme">
          <span class="theme-icon" aria-hidden="true">◐</span>
          <span class="theme-label">Theme</span>
        </button>
      </div>
    </div>

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


def _wrap_html(body, chart_loader, runtime_js, extra_head=""):
    """Wrap page markup in the shared HTML shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reponomics Dashboard</title>
  {extra_head}
  {chart_loader}
  <style>
{_build_font_face_styles()}
{BASE_STYLES}
  </style>
  <script>
    (function() {{
      try {{
        var saved = localStorage.getItem('gh-traffic-theme');
        var theme = (saved === 'light' || saved === 'dark')
          ? saved
          : (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
        if (theme === 'light') document.documentElement.setAttribute('data-theme', 'light');
      }} catch (e) {{ /* ignore */ }}
    }})();
  </script>
</head>
<body>
{body}
{_render_update_notice()}

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
      <a href="https://github.com/hesreallyhim/github-traffic-report-template">Reponomics</a>
      <span class="dot">·</span>
      <span>Made for indie hackers shipping across many repos</span>
    </div>
  </footer>

  <script>
{runtime_js}
  </script>
</body>
</html>
"""


def _build_public_html(payload, chart_loader):
    """Build the standard published dashboard HTML."""
    totals = payload["totals"]
    shell = _build_dashboard_shell(
        (
            f"Last updated: {payload['generated_at']} | " +
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
    runtime_js = (
        APP_RUNTIME_JS
        + "\nconst dashboardPayload = "
        + json.dumps(payload, separators=(",", ":"))
        + ";\nrenderDashboard(dashboardPayload);\n"
    )
    return _wrap_html(shell, chart_loader, runtime_js)


def _build_encrypted_html(encrypted_payload, chart_loader):
    """Build the encrypted published dashboard HTML."""
    auth_card = """
  <div id="auth-shell">
    <div class="brand-lockup">
      <h1 class="brand">reponomics<span class="accent">.</span></h1>
      <div class="brand-eyebrow">Dashboard</div>
    </div>
    <p class="updated">Encrypted Pages mode for private growth analytics.</p>

    <div class="card" id="unlock-card">
      <h2>Unlock Dashboard</h2>
      <p class="auth-copy">
        Enter your dashboard key to decrypt the latest dashboard snapshot in
        this browser.
      </p>
      <form class="auth-form" id="unlock-form">
        <input
          class="auth-hidden-username"
          id="dashboard-username"
          type="text"
          name="username"
          autocomplete="username"
          value="encrypted-dashboard"
          tabindex="-1"
          aria-hidden="true"
        >
        <input
          class="auth-input"
          id="dashboard-key"
          type="password"
          name="dashboard-key"
          autocomplete="current-password"
          placeholder="Enter dashboard key"
        >
        <button class="auth-button" id="unlock-button" type="submit">Unlock</button>
      </form>
      <p class="auth-status" id="unlock-status"></p>
    </div>
  </div>
"""
    shell = _build_dashboard_shell(
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
    runtime_js = (APP_RUNTIME_JS + "\n" + SECURE_RUNTIME_JS).replace(
        "__PBKDF2_ITERATIONS__",
        str(PBKDF2_ITERATIONS),
    )
    encrypted_payload_json = json.dumps(encrypted_payload, separators=(",", ":"))
    body = (
        auth_card
        + shell
        + "\n  <script id=\"encrypted-payload\" type=\"application/json\">"
        + encrypted_payload_json
        + "</script>\n"
    )
    return _wrap_html(
        body,
        chart_loader,
        runtime_js,
        extra_head='<meta name="robots" content="noindex, nofollow">',
    )


def render():
    daily_rows = load_daily()
    referrer_rows = load_referrers()
    path_rows = load_paths()
    metric_rows = load_repo_metrics()

    access_mode = _load_access_mode()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    totals = aggregate_totals(daily_rows)
    dates, series = aggregate_by_date(daily_rows)
    per_repo = aggregate_per_repo(daily_rows)
    ref_list = top_referrers(referrer_rows)
    path_list = top_paths(path_rows)
    repo_series = _build_repo_series(daily_rows)
    weekday = _build_weekday_summary(daily_rows)
    repo_weekday = _build_repo_weekday_summary(daily_rows)
    repo_referrers = _latest_snapshot_by_repo(referrer_rows)
    repo_paths = _latest_snapshot_by_repo(path_rows)
    growth = growth_analytics(daily_rows, metric_rows)
    insights = actionable_insights(daily_rows, metric_rows, limit=3, growth=growth)
    insights_structured = actionable_insights_structured(daily_rows, metric_rows, limit=3, growth=growth)
    payload = _build_payload(
        now,
        totals,
        dates,
        series,
        per_repo,
        ref_list,
        path_list,
        repo_series,
        weekday,
        repo_weekday,
        repo_referrers,
        repo_paths,
        growth,
        insights,
        insights_structured,
    )

    if access_mode == ACCESS_MODE_ENCRYPTED:
        dashboard_key = (
            os.environ.get(DASHBOARD_KEY_ENV)
            or os.environ.get(LEGACY_PASSPHRASE_ENV, "")
        )
        if not dashboard_key:
            raise ValueError(
                f"{DASHBOARD_KEY_ENV} must be set when " +
                f"{ACCESS_MODE_ENV}={ACCESS_MODE_ENCRYPTED!r}."
            )
        published_html = _build_encrypted_html(
            _encrypt_payload(payload, dashboard_key),
            f'<script src="{_publish_vendored_chart_js(OUTPUT_PATH)}"></script>',
        )
    else:
        published_html = _build_public_html(
            payload,
            f'<script src="{_publish_vendored_chart_js(OUTPUT_PATH)}"></script>',
        )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(published_html)

    standalone_html = _build_public_html(
        payload,
        f"<script>{_load_vendored_chart_js()}</script>",
    )

    os.makedirs(os.path.dirname(STANDALONE_OUTPUT_PATH), exist_ok=True)
    with open(STANDALONE_OUTPUT_PATH, "w") as f:
        f.write(standalone_html)

    print(
        f"Dashboards written to {OUTPUT_PATH} and {STANDALONE_OUTPUT_PATH} " +
        f"(mode={access_mode}, {len(daily_rows)} daily rows, {len(dates)} dates, " +
        f"{len(ref_list)} referrers, {len(path_list)} paths)"
    )


if __name__ == "__main__":
    render()
