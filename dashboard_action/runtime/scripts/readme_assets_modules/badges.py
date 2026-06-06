"""Small static SVG badge rendering."""

from __future__ import annotations

import html

from .theme import estimate_text_width, responsive_svg


def svg_version_badge(label: str, value: str, color: str, height: int = 22) -> str:
    """Generate a small static SVG badge for GitHub README rendering."""
    label = label.strip()
    value = value.strip()
    label_width = max(72, estimate_text_width(label, 11) + 18)
    value_width = max(56, estimate_text_width(value, 11) + 18)
    width = label_width + value_width
    label_text_x = label_width // 2
    value_text_x = label_width + (value_width // 2)
    safe_label = html.escape(label)
    safe_value = html.escape(value)
    safe_color = html.escape(color, quote=True)
    inner = f"""  <rect width="{width}" height="{height}" fill="#555"/>
  <rect x="{label_width}" width="{value_width}" height="{height}" fill="{safe_color}"/>
  <rect x="{label_width}" width="4" height="{height}" fill="{safe_color}"/>
  <text x="{label_text_x}" y="15" text-anchor="middle" fill="#fff"
        font-size="11" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">{safe_label}</text>
  <text x="{value_text_x}" y="15" text-anchor="middle" fill="#fff"
        font-size="11" font-weight="600" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">{safe_value}</text>"""
    return responsive_svg(inner, width, height)
