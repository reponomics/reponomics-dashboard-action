"""Hero stats README SVG rendering."""

from __future__ import annotations

from .theme import DARK, FONT_STYLE, Theme, empty_state_svg, format_compact, responsive_svg


def trend_arrow(
    current: int | float, previous: int | float, theme: Theme = DARK,
) -> tuple[str, str]:
    """Return (arrow_text, color) for a trend indicator."""
    if previous <= 0:
        return ("", theme.text_muted)
    pct = (current - previous) / previous
    if pct > 0.05:
        return (f"+{pct:.0%}", theme.accent_green)
    if pct < -0.05:
        return (f"{pct:.0%}", theme.accent_red)
    return ("~0%", theme.text_muted)


def svg_hero_stats(
    total_views: int,
    total_uniques: int,
    total_clones: int,
    total_clone_uniques: int,
    repo_count: int,
    days_tracked: int,
    trend_views: int | None = None,
    prev_views: int | None = None,
    width: int = 520,
    theme: Theme = DARK,
) -> str:
    """Generate an SVG hero stat banner with 4 key metrics."""
    if total_views == 0 and total_clones == 0:
        return empty_state_svg("No traffic data yet.", width=width, height=100, theme=theme)

    height = 120
    col_w = width // 4
    metric_blocks = _metric_blocks(
        [
            ("VIEWS", total_views, theme.accent_blue),
            ("VISITORS", total_uniques, theme.accent_green),
            ("CLONES", total_clones, theme.accent_purple),
            ("CLONERS", total_clone_uniques, theme.accent_yellow),
        ],
        col_w,
        theme,
    )
    inner = f"""{FONT_STYLE}
  <rect width="100%" height="100%" fill="{theme.bg}" rx="10"/>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="none" stroke="{theme.border}" rx="10" stroke-opacity="0.6"/>
  {''.join(metric_blocks)}
  {''.join(_separator_dots(col_w, theme))}
  {_trend_svg(trend_views, prev_views, col_w, theme)}
  {_footer_svg(repo_count, days_tracked, width, theme)}"""
    return responsive_svg(inner, width, height)


def _metric_blocks(metrics: list[tuple[str, int, str]], col_w: int, theme: Theme) -> list[str]:
    blocks = []
    for i, (label, value, color) in enumerate(metrics):
        cx = col_w * i + col_w // 2
        bar_w = 32
        delay = f"{i * 0.12:.2f}s"
        blocks.extend(
            [
                f'<rect x="{cx - bar_w // 2}" y="16" width="{bar_w}" height="3" fill="{color}" rx="1.5" opacity="0.7"/>',
                (
                    f'<text x="{cx}" y="56" text-anchor="middle" font-size="26" '
                    + f'font-weight="700" fill="{color}" letter-spacing="-0.03em" opacity="0">'
                    + f"{format_compact(value)}"
                    + '<animate attributeName="opacity" values="0;1;1;0" '
                    + 'keyTimes="0;0.03;0.92;1" dur="12s" '
                    + f'begin="{delay}" repeatCount="indefinite"/></text>'
                ),
                (
                    f'<text x="{cx}" y="76" text-anchor="middle" font-size="10" '
                    + f'fill="{theme.text_muted}" font-weight="600" letter-spacing="0.08em">{label}</text>'
                ),
            ]
        )
    return blocks


def _separator_dots(col_w: int, theme: Theme) -> list[str]:
    return [
        f'<circle cx="{col_w * i}" cy="50" r="1.5" fill="{theme.border}"/>'
        for i in range(1, 4)
    ]


def _trend_svg(
    trend_views: int | None,
    prev_views: int | None,
    col_w: int,
    theme: Theme,
) -> str:
    if trend_views is None or prev_views is None or prev_views <= 0:
        return ""
    arrow_text, arrow_color = trend_arrow(trend_views, prev_views, theme=theme)
    if not arrow_text:
        return ""
    return (
        f'<text x="{col_w // 2 + 48}" y="58" font-size="11" '
        + f'fill="{arrow_color}" font-weight="600">{arrow_text}</text>'
    )


def _footer_svg(repo_count: int, days_tracked: int, width: int, theme: Theme) -> str:
    footer_text = f"{repo_count} repos \u00b7 {days_tracked} days"
    return (
        f'<text x="{width // 2}" y="104" text-anchor="middle" '
        + f'font-size="11" fill="{theme.text_faint}">{footer_text}</text>'
    )
