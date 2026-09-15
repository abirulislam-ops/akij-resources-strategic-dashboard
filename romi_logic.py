"""
Shared ROMI logic — turns raw campaign rows (computed + override columns)
into the effective A–S columns. Used by both Streamlit apps and the engine.

Effective value = override if set, else computed/derived.
"""

import html as _html


def _ov(row, ov_key, base):
    v = row.get(ov_key) if isinstance(row, dict) else getattr(row, ov_key, None)
    if v is None:
        return base
    return float(v)


def _romi(numerator, o):
    if not o:
        return 0.0
    return (numerator - o) / o


def compute_effective(row):
    """Return a dict of all effective column values for one campaign row."""
    def get(key):
        return row.get(key) if isinstance(row, dict) else getattr(row, key, None)

    def num(key):
        v = get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    f = _ov(row, "actual_rev_ov", num("actual_rev") or 0.0)
    gg = _ov(row, "organic_rev_ov", num("organic_rev") or 0.0)
    h = _ov(row, "sply_rev_ov", num("sply_rev") or 0.0)
    j = _ov(row, "gp_margin_ov", num("gp_margin") or 0.0)
    o = num("marketing_expense_total") or 0.0

    i = _ov(row, "incr_rev_ov", f - gg)
    k = _ov(row, "actual_profit_ov", f * j)
    l = _ov(row, "base_profit_ov", gg * j)
    m = _ov(row, "sply_profit_ov", h * j)
    n = _ov(row, "incr_profit_ov", i * j)
    p = _ov(row, "romi_top_ov", _romi(i, o))
    r = _ov(row, "romi_bottom_ov", _romi(n, o))

    return {
        # A-E (identity)
        "business_unit_id": get("business_unit_id"),
        "campaign_name": get("campaign_name"),
        "category": get("category"),
        "report_month": get("report_month"),
        "start_date": get("start_date"),
        "end_date": get("end_date"),
        # F-H
        "actual_rev": f,
        "organic_rev": gg,
        "sply_rev": h,
        # I
        "incr_rev": i,
        # J
        "gp_margin": j,
        # K-N
        "actual_profit": k,
        "base_profit": l,
        "sply_profit": m,
        "incr_profit": n,
        # O
        "marketing_expense": o,
        # P-R
        "romi_top": p,
        "romi_bottom": r,
        # transparency
        "spend_pool_total": num("spend_pool_total"),
        "n_months": get("n_months"),
        "as_of": get("as_of"),
        # identity extras
        "officer_name": get("officer_name"),
        "officer_enroll": get("officer_enroll"),
    }


def sbu_totals(effective_rows):
    """Aggregate effective rows -> SBU totals (top-line and bottom-line ROMI)."""
    total_i = sum(r["incr_rev"] or 0.0 for r in effective_rows)
    total_n = sum(r["incr_profit"] or 0.0 for r in effective_rows)
    total_o = sum(r["marketing_expense"] or 0.0 for r in effective_rows)
    total_rev = sum(r["actual_rev"] or 0.0 for r in effective_rows)
    return {
        "n_campaigns": len(effective_rows),
        "total_incr_rev": total_i,
        "total_incr_profit": total_n,
        "total_marketing": total_o,
        "total_actual_rev": total_rev,
        "total_romi_top": (total_i - total_o) / total_o if total_o else 0.0,
        "total_romi_bottom": (total_n - total_o) / total_o if total_o else 0.0,
    }


# Human-readable labels (order as in the ROMI template).
COLUMN_ORDER = [
    ("business_unit_id", "SBU"),
    ("campaign_name", "Campaign Name"),
    ("category", "Category"),
    ("report_month", "Report Month"),
    ("start_date", "Start Date"),
    ("end_date", "End Date"),
    ("actual_rev", "Actual Revenue (monthly avg)"),
    ("organic_rev", "Organic/Base Sales (6-mo avg)"),
    ("sply_rev", "SPLY Revenue (monthly avg)"),
    ("incr_rev", "Marketing Led Increment"),
    ("gp_margin", "GP Margin (%)"),
    ("actual_profit", "Actual Profit"),
    ("base_profit", "Base Profit"),
    ("sply_profit", "SPLY Profit"),
    ("incr_profit", "Marketing Led Profit"),
    ("marketing_expense", "Marketing Expense"),
    ("romi_top", "ROMI (Top Line)"),
    ("romi_bottom", "ROMI (Bottom Line)"),
]


def month_options(n=18):
    """Return a list of 'YYYY-MM' strings for the last n months (newest first)."""
    import datetime as dt
    today = dt.date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def current_month():
    import datetime as dt
    return f"{dt.date.today():%Y-%m}"


# ---------------------------------------------------------------------------
# Branch-mark (benchmark) comparison + hover table
# ---------------------------------------------------------------------------
def benchmark_rows(effective_rows, sbus):
    """Aggregate effective campaign rows by business unit and attach the
    branch-mark benchmark (top/bottom) plus its rationale note.

    Every benchmarked SBU (benchmark_top/bottom set) is included even when it
    has no campaign data yet, so the full branch-mark list is always visible.

    sbus: dict keyed by int(business_unit_id) -> SBU row dict.
    """
    def make_row(bu_id, t):
        s = sbus.get(int(bu_id), {}) if bu_id is not None else {}
        return {
            "business_unit_id": int(bu_id) if bu_id is not None else None,
            "code": s.get("code") or str(bu_id),
            "name": s.get("name") or "",
            "n_campaigns": t["n_campaigns"],
            "total_romi_top": t["total_romi_top"],
            "total_romi_bottom": t["total_romi_bottom"],
            "benchmark_top": s.get("benchmark_top"),
            "benchmark_bottom": s.get("benchmark_bottom"),
            "benchmark_note": s.get("benchmark_note") or "",
        }

    by_bu = {}
    for r in effective_rows:
        by_bu.setdefault(r.get("business_unit_id"), []).append(r)
    out = [make_row(bu_id, sbu_totals(rws)) for bu_id, rws in by_bu.items()]
    seen = {r["business_unit_id"] for r in out}

    empty = {"n_campaigns": 0, "total_romi_top": None, "total_romi_bottom": None}
    for bu_id, s in sbus.items():
        if (s.get("benchmark_top") is not None or s.get("benchmark_bottom") is not None) and bu_id not in seen:
            out.append(make_row(bu_id, empty))

    out.sort(key=lambda r: (-(r["total_romi_top"] if r["total_romi_top"] is not None else -1e18), r["code"]))
    return out


def _fmt_romi_x(v):
    return "—" if v is None else f"{float(v):,.2f}x"


BRANCHMARK_CSS = (
    "<style>"
    ".bm{width:100%;border-collapse:collapse;font-size:13px;}"
    ".bm th{color:#888;font-weight:600;text-align:left;padding:6px 8px;border-bottom:1px solid #ddd;}"
    ".bm td{padding:6px 8px;border-bottom:1px solid #eee;}"
    ".bm .n{text-align:right;font-variant-numeric:tabular-nums;}"
    ".bm .hit{color:#0a7d33;font-weight:700;}"
    ".bm .miss{color:#c0392b;font-weight:700;}"
    ".bm .nodata{color:#b45309;font-weight:700;}"
    ".bm .na{color:#999;}"
    ".bm .tip{position:relative;cursor:help;border-bottom:1px dotted #999;}"
    ".bm .tip .tooltip{visibility:hidden;opacity:0;position:absolute;bottom:130%;left:0;"
    "width:280px;background:#1e293b;color:#e2e8f0;padding:8px 10px;border-radius:6px;"
    "font-size:12px;line-height:1.4;z-index:999;transition:opacity .15s;"
    "text-align:left;font-weight:400;box-shadow:0 2px 8px rgba(0,0,0,.3);}"
    ".bm .tip:hover .tooltip{visibility:visible;opacity:1;}"
    "</style>"
)


def branchmark_table_html(rows):
    """HTML branch-mark table with hover tooltips explaining each mark."""
    head = (
        "<table class='bm'><thead><tr>"
        "<th>SBU</th><th>Campaigns</th>"
        "<th>ROMI Top</th><th>Mark Top</th>"
        "<th>ROMI Bottom</th><th>Mark Bottom</th><th>Status</th>"
        "</tr></thead><tbody>"
    )

    def mark_cell(v, note):
        if v is None:
            return "—"
        tip = _html.escape(note) if note else ""
        return (f"<span class='tip'>≥{float(v):,.2f}x"
                f"<span class='tooltip'>{tip}</span></span>")

    body = []
    for r in rows:
        bt, bb = r.get("benchmark_top"), r.get("benchmark_bottom")
        note = r.get("benchmark_note") or ""
        rt, rb = r.get("total_romi_top"), r.get("total_romi_bottom")
        has_bm = bt is not None or bb is not None
        has_data = rt is not None or rb is not None
        if not has_bm:
            status = "<span class='na'>—</span>"
        elif not has_data:
            status = "<span class='nodata'>NO DATA</span>"
        else:
            hit = ((rt or 0) >= (bt if bt is not None else -1e18)
                   and (rb or 0) >= (bb if bb is not None else -1e18))
            status = ("<span class='hit'>HITTING</span>" if hit
                      else "<span class='miss'>MISSING</span>")
        body.append(
            f"<tr><td>{_html.escape(r['code'])}</td>"
            f"<td class='n'>{r['n_campaigns']}</td>"
            f"<td class='n'>{_fmt_romi_x(rt)}</td><td class='n'>{mark_cell(bt, note)}</td>"
            f"<td class='n'>{_fmt_romi_x(rb)}</td><td class='n'>{mark_cell(bb, note)}</td>"
            f"<td>{status}</td></tr>"
        )
    return head + "".join(body) + "</tbody></table>"


def benchmark_chart_fig(bm_rows, which="top", log_y=True):
    """Return a Plotly grouped-bar figure: Actual (blue) vs Mark (amber).

    which: "top" | "bottom". log_y uses a logarithmic axis so the branch marks
    (2–8x) stay visible next to large/outlier actual ROMI values.
    """
    import plotly.graph_objects as go

    codes = [r["code"] for r in bm_rows]
    if which == "bottom":
        actual = [r["total_romi_bottom"] for r in bm_rows]
        mark = [r["benchmark_bottom"] for r in bm_rows]
        title = "Bottom-line ROMI — actual vs mark"
    else:
        actual = [r["total_romi_top"] for r in bm_rows]
        mark = [r["benchmark_top"] for r in bm_rows]
        title = "Top-line ROMI — actual vs mark"

    if log_y:
        # Log axes cannot render non-positive values; drop them here (they
        # still appear as MISSING in the branch-mark table below).
        actual = [v if (v is not None and v > 0) else None for v in actual]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Actual", x=codes, y=actual, marker_color="#2563eb"))
    fig.add_trace(go.Bar(name="Mark (≥)", x=codes, y=mark, marker_color="#f59e0b",
                         marker_line_color="#7c2d12", marker_line_width=1.5))
    fig.update_layout(
        title=title,
        barmode="group",
        height=400,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis_title="ROMI (x)",
        xaxis_tickangle=-45,
    )
    if log_y:
        fig.update_yaxes(type="log")
    return fig


def top_campaigns(effective_rows, n=10):
    """Return campaigns sorted by top-line ROMI (desc), skipping rows with no
    marketing expense or no computable ROMI."""
    valid = [r for r in effective_rows
             if (r.get("marketing_expense") or 0) > 0 and r.get("romi_top") is not None]
    valid.sort(key=lambda r: -(r["romi_top"] or 0))
    return valid[:n]
