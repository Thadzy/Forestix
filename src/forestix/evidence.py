"""Evidence generation: crisp SVG time-series charts with Cutoff & Break Date markers (FR-04)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import pandas as pd

_STATUS_COLORS: dict[str, tuple[str, str]] = {
    "GREEN": ("#16a34a", "#dcfce7"),
    "AMBER": ("#d97706", "#fef3c7"),
    "RED": ("#dc2626", "#fee2e2"),
}


def _ym_to_float(ym: str) -> float:
    return int(ym[:4]) + (int(ym[5:7]) - 0.5) / 12.0


def generate_evidence(
    plot_id: str,
    s2_plot: pd.DataFrame,
    s1_plot: pd.DataFrame,
    triage_status: str,
    module_a_out: dict[str, Any],
    module_b_out: dict[str, Any],
    geom_info: dict[str, Any],
    spec: dict[str, Any],
    output_dir: str | Path,
    max_yield_quota_kg: float | None = None,
) -> dict[str, Path]:
    """Generate a self-contained SVG time-series evidence chart for a plot.

    Displays Sentinel-2 NDVI/NBR (top panel) and Sentinel-1 VH Asc/Desc (bottom panel),
    with vertical Cutoff (2020-12-31) and detected Break Date lines plus triage summary.

    Serves: FR-04.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / f"{plot_id}_evidence.svg"

    w, h = 760, 400
    pad_l, pad_r = 56, 24
    cw = w - pad_l - pad_r
    x_min, x_max = 2018.0, 2026.0
    mx = lambda t: pad_l + ((t - x_min) / (x_max - x_min)) * cw

    # Panel 1 (Optical NDVI/NBR): y in [58, 205]
    p1_top, p1_bot = 58, 205
    my_opt = lambda v: p1_bot - ((max(-0.2, min(1.0, v)) - (-0.2)) / 1.2) * (p1_bot - p1_top)

    # Panel 2 (SAR VH dB): y in [235, 362]
    p2_top, p2_bot = 235, 362
    my_sar = lambda v: p2_bot - ((max(-24.0, min(-6.0, v)) - (-24.0)) / 18.0) * (p2_bot - p2_top)

    fg_col, bg_col = _STATUS_COLORS.get(triage_status, ("#475569", "#f1f5f9"))
    cutoff_t = 2021.0  # 2020-12-31
    bdate = module_b_out.get("break_date")
    break_t = _ym_to_float(bdate[:7]) if bdate else None

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        'style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; background:#0f172a;">',
        f'<rect width="{w}" height="{h}" fill="#0f172a" rx="10"/>',
        # Header
        f'<text x="20" y="28" fill="#f8fafc" font-size="15" font-weight="700">Forestix Evidence: {escape(str(plot_id))}</text>',
        f'<rect x="{w - 132}" y="11" width="112" height="24" rx="12" fill="{bg_col}"/>',
        f'<text x="{w - 76}" y="27" text-anchor="middle" fill="{fg_col}" font-size="12" font-weight="700">{escape(triage_status)}</text>',
        f'<text x="20" y="46" fill="#94a3b8" font-size="11">'
        f'Area: {geom_info.get("area_rai", 0):.2f} rai ({geom_info.get("pure_pixels", 0)} pure px) | '
        f'ModA: {escape(str(module_a_out.get("predicted_class")))} ({module_a_out.get("confidence", 0):.2f}) | '
        f'Break: {escape(str(bdate or "none"))} ({escape(str(module_b_out.get("trigger_sensor", "none")))})'
        + (f' | Yield Cap: {max_yield_quota_kg:,.0f} kg' if max_yield_quota_kg is not None else "")
        + "</text>",
    ]

    # Grid lines + axis labels
    for y_val in (0.0, 0.3, 0.6, 0.9):
        yy = my_opt(y_val)
        parts.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{w - pad_r}" y2="{yy:.1f}" stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" fill="#64748b" font-size="10">{y_val:.1f}</text>')
    parts.append(f'<text x="{pad_l + 6}" y="{p1_top + 12}" fill="#cbd5e1" font-size="11" font-weight="600">Sentinel-2 Optical (NDVI green / NBR sky)</text>')

    for db_val in (-22, -18, -14, -10):
        yy = my_sar(db_val)
        parts.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{w - pad_r}" y2="{yy:.1f}" stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" fill="#64748b" font-size="10">{db_val} dB</text>')
    parts.append(f'<text x="{pad_l + 6}" y="{p2_top + 12}" fill="#cbd5e1" font-size="11" font-weight="600">Sentinel-1 SAR VH (ASC amber / DESC violet — separate orbits)</text>')

    for yr in range(2018, 2026):
        xx = mx(float(yr))
        parts.append(f'<line x1="{xx:.1f}" y1="{p1_top}" x2="{xx:.1f}" y2="{p2_bot}" stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="{xx:.1f}" y="{h - 14}" text-anchor="middle" fill="#94a3b8" font-size="10">{yr}</text>')

    # Cutoff vertical line
    cx = mx(cutoff_t)
    parts.append(f'<line x1="{cx:.1f}" y1="{p1_top}" x2="{cx:.1f}" y2="{p2_bot}" stroke="#f43f5e" stroke-width="1.5" stroke-dasharray="5,4"/>')
    parts.append(f'<text x="{cx + 4:.1f}" y="{p1_bot - 4}" fill="#f43f5e" font-size="10">Cutoff 2020-12-31</text>')

    # Break Date vertical line
    if break_t is not None:
        bx = mx(break_t)
        parts.append(f'<line x1="{bx:.1f}" y1="{p1_top}" x2="{bx:.1f}" y2="{p2_bot}" stroke="#facc15" stroke-width="1.8" stroke-dasharray="3,3"/>')
        parts.append(f'<text x="{bx + 4:.1f}" y="{p2_bot - 4}" fill="#facc15" font-size="10">Break {escape(str(bdate))}</text>')

    def _polyline(df: pd.DataFrame, col: str, y_fn, color: str) -> str:
        sub = df.dropna(subset=[col]).sort_values("ym")
        if sub.empty:
            return ""
        pts = " ".join(f"{mx(_ym_to_float(str(r['ym']))):.1f},{y_fn(float(r[col])):.1f}" for _, r in sub.iterrows())
        return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'

    s2_c = s2_plot.copy()
    s2_c["ndvi"] = pd.to_numeric(s2_c["ndvi"], errors="coerce")
    s2_c["nbr"] = pd.to_numeric(s2_c["nbr"], errors="coerce")
    parts.append(_polyline(s2_c, "ndvi", my_opt, "#22c55e"))
    parts.append(_polyline(s2_c, "nbr", my_opt, "#38bdf8"))

    s1_c = s1_plot.copy()
    s1_c["vh"] = pd.to_numeric(s1_c["vh"], errors="coerce")
    parts.append(_polyline(s1_c[s1_c["orbit"] == "ASCENDING"], "vh", my_sar, "#f59e0b"))
    parts.append(_polyline(s1_c[s1_c["orbit"] == "DESCENDING"], "vh", my_sar, "#c084fc"))

    parts.append("</svg>")
    svg_path.write_text("\n".join(parts), encoding="utf-8")
    return {"timeseries_plot": svg_path}
