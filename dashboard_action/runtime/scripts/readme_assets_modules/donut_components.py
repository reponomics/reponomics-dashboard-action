"""Donut chart SVG component fragments."""

from __future__ import annotations

from .donut_geometry import DonutLayout, SliceSpec
from .theme import Theme, format_compact


def slice_path(index: int, spec: SliceSpec) -> str:
    slice_delay = index * 0.08 / 12
    return (
        f'<path d="{spec.path}" fill="{spec.color}" opacity="0">'
        + '<animate attributeName="opacity" values="0;0.9;0.9;0" '
        + f'keyTimes="0;{slice_delay + 0.03:.3f};0.92;1" dur="12s" '
        + 'repeatCount="indefinite"/>'
        + f"<title>{spec.original_label}: {spec.value:,.0f} ({spec.pct:.1%})</title></path>"
    )


def legend_item(index: int, spec: SliceSpec, layout: DonutLayout, theme: Theme) -> str:
    ly = index * layout.legend_row_height + 10
    pct_str = f"{spec.pct:.1%}" if spec.pct >= 0.01 else "&lt;1%"
    return (
        f'<circle cx="{layout.legend_x + 6}" cy="{ly + 4}" r="5" fill="{spec.color}"/>'
        + f'<text x="{layout.legend_x + 18}" y="{ly + 8}" font-size="10" '
        + f'fill="{theme.text_primary}" font-weight="600" '
        + f'font-variant-numeric="tabular-nums">{pct_str}</text>'
        + f'<text x="{layout.legend_x + 56}" y="{ly + 8}" font-size="{layout.legend_font}" '
        + f'fill="{theme.text_muted}">{spec.display_label}</text>'
    )


def center_svg(total: int, layout: DonutLayout, theme: Theme) -> str:
    center_label = format_compact(total)
    return (
        f'<text x="{layout.center}" y="{layout.center - 2}" text-anchor="middle" '
        + f'font-size="18" font-weight="700" fill="{theme.text_primary}">{center_label}</text>'
        + f'<text x="{layout.center}" y="{layout.center + 14}" text-anchor="middle" '
        + f'font-size="9" fill="{theme.text_faint}">total views</text>'
    )
