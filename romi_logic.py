"""
Shared ROMI logic — turns raw campaign rows (computed + override columns)
into the effective A–S columns. Used by both Streamlit apps and the engine.

Effective value = override if set, else computed/derived.
"""


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
        "organic_months_used": get("organic_months_used"),
        "organic_mode": get("organic_mode"),
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
    ("actual_rev", "Actual Revenue (full)"),
    ("organic_rev", "Organic/Base Sales (full)"),
    ("sply_rev", "SPLY Revenue (full)"),
    ("incr_rev", "Incremental Revenue"),
    ("gp_margin", "GP Margin (%)"),
    ("actual_profit", "Actual Profit"),
    ("base_profit", "Base Profit"),
    ("sply_profit", "SPLY Profit"),
    ("incr_profit", "Incremental Profit"),
    ("marketing_expense", "Marketing Expense (full)"),
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
