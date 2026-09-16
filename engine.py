"""
Compute engine — derives the ROMI base metrics (F, G, H, J, O_M) and the
formula columns (I, K, L, M, N, P, R) for one campaign, on a MONTHLY basis.

Template-faithful (matches "ROMI tamplate and formula.xlsx", "Automation
Sample": I=F-G, T=(M-S)/S, V=(R-S)/S):

  F  actual revenue  = revenue in the reporting month (the still-running
                       current month is extrapolated to a full-month estimate).
  G  organic/base    = plain average monthly revenue over the 6 months BEFORE
                       the campaign start date (no marketing filter).
  G_SPLY             = the same 6-month lookback, one year earlier (reference).
  H  SPLY revenue    = revenue in the reporting month, one year earlier.
  O_M marketing spend = GL campaign-able marketing for the SBU in the
                       reporting month (the ROMI denominator).
  Increment = F - G.

A campaign is scored only for the month it is ACTIVE (start <= month end and
end >= month start); long campaigns are re-scored each month they run.
"""

import calendar
import datetime as dt

import dwh


def _cfg():
    """Safe config access (config.py is git-ignored, may be absent on cloud)."""
    try:
        import config as cfg
        return cfg
    except Exception:
        pass

    class _C:
        ORGANIC_LOOKBACK_MONTHS = 6
        GP_MARGIN_FY_START = "2025-07-01"
        GP_MARGIN_FY_END = "2026-07-01"
    return _C


config = _cfg()


def _baseline(g, h, g_sply):
    """Organic baseline (B) = the 6-month organic average G.

    Matches the ROMI template: Incremental = F - G (cell "=F5-G5").
    H (SPLY) is informational only. Falls back to H, then 0.
    """
    if g and g > 0:
        return g
    return h or 0.0


def _previous_month_key(today=None):
    """year*100+month of the most recently completed month."""
    today = today or dt.date.today()
    y, m = today.year, today.month
    m -= 1
    if m == 0:
        m = 12
        y -= 1
    return y * 100 + m


def _to_key(report_month):
    """Normalize report_month (int key / 'YYYY-MM' / 'YYYYMM') to a key."""
    if report_month is None:
        return None
    if isinstance(report_month, int):
        return report_month
    s = str(report_month).strip()
    if len(s) == 7 and s[4] == "-":
        return int(s[:4]) * 100 + int(s[5:7])
    if len(s) == 6:
        return int(s[:4]) * 100 + int(s[4:6])
    raise ValueError(f"Unrecognized report_month: {report_month!r}")


def _extrapolate_current_month(rev, camp_months, today=None):
    """Scale the still-running current month's revenue up to a full-month
    estimate, so a partially-elapsed month is not under-counted as a full month."""
    if today is None:
        today = dt.date.today()
    cur = today.year * 100 + today.month
    if cur in camp_months and rev.get(cur):
        days_total = calendar.monthrange(today.year, today.month)[1]
        if 0 < today.day < days_total:
            rev = dict(rev)
            rev[cur] = rev[cur] * days_total / today.day
    return rev


def compute_metrics(bu_id, start_date, end_date, gp_margin=None, report_month=None):
    """Monthly ROMI metrics for a single reporting month.

    report_month = the month being scored ('YYYY-MM' / 'YYYYMM' / int key).
    Defaults to the previous calendar month (the most recent fully-elapsed
    month, whose DWH figures are complete).

    A campaign is scored only for the month it is ACTIVE (start <= month end
    and end >= month start); long campaigns are re-scored each month they run.

      F  actual revenue = revenue in the reporting month (extrapolated to a
         full month if it is the still-running current month).
      G  organic/base  = plain 6-month average revenue before campaign start.
      H  SPLY revenue  = the same reporting month, one year earlier.
      O_M  = GL campaign-able marketing spend for the SBU in the reporting
             month (the ROMI denominator — same scale as revenue).
      Increment = F - G   (template formula =F-G).
    """
    m_key = _to_key(report_month) if report_month is not None else _previous_month_key()
    m_start = dwh.key_to_date(m_key)
    m_end = dwh.key_after(m_key)

    active = (start_date < m_end) and (end_date >= m_start)

    # ---- F: reporting-month revenue (current month extrapolated) ----
    rev = dwh.revenue_monthly(bu_id, m_start, m_end)
    rev = _extrapolate_current_month(rev, [m_key])
    f = rev.get(m_key, 0.0)

    # ---- H: SPLY revenue (same month, one year earlier) ----
    h_key = dwh.shift_ym(m_key, -12)
    rev_sply = dwh.revenue_monthly(bu_id, dwh.key_to_date(h_key), dwh.key_after(h_key))
    h = rev_sply.get(h_key, 0.0)

    # ---- G: organic/base = plain 6-month average before campaign start ----
    start_key = dwh.parse_ym(start_date)
    lookback_keys = [dwh.shift_ym(start_key, -i)
                     for i in range(1, config.ORGANIC_LOOKBACK_MONTHS + 1)]
    lb_from = dwh.key_to_date(min(lookback_keys))
    lb_to = dwh.key_after(max(lookback_keys))
    rev_lb = dwh.revenue_monthly(bu_id, lb_from, lb_to)
    g = sum(rev_lb.get(k, 0.0) for k in lookback_keys) / config.ORGANIC_LOOKBACK_MONTHS

    # ---- G_SPLY: same 6-month lookback, one year earlier (trend denominator) ----
    sply_lb_keys = [dwh.shift_ym(k, -12) for k in lookback_keys]
    slb_from = dwh.key_to_date(min(sply_lb_keys))
    slb_to = dwh.key_after(max(sply_lb_keys))
    rev_slb = dwh.revenue_monthly(bu_id, slb_from, slb_to)
    g_sply = sum(rev_slb.get(k, 0.0) for k in sply_lb_keys) / config.ORGANIC_LOOKBACK_MONTHS

    # ---- J: GP margin (fixed per SBU) ----
    if gp_margin is None:
        gp_margin = dwh.gp_margin(bu_id, config.GP_MARGIN_FY_START, config.GP_MARGIN_FY_END)

    # ---- O_M: GL campaign-able marketing spend in the reporting month ----
    _, pool = dwh.marketing_monthly(bu_id, m_start, m_end)
    o_monthly = pool.get(m_key, 0.0)

    baseline = _baseline(g, h, g_sply)
    incr = f - baseline

    return {
        "f": f,
        "g": g,
        "g_sply": g_sply,
        "h": h,
        "j": gp_margin,
        "o_monthly": o_monthly,
        "n_months": 1,
        "active": active,
        "baseline": baseline,
        "incr_rev": incr,
        "short_campaign": (end_date - start_date).days < 15,
    }


def derive_formulas(m, o):
    """Compute the formula columns from base metrics (m) + marketing expense (o).

    Monthly: the increment is F - G for the single reporting month and the
    denominator o is the reporting-month marketing spend.
    """
    f = m["f"]
    g = m["g"]
    g_sply = m.get("g_sply")
    h = m["h"]
    j = (m["j"] or 0.0)

    baseline = _baseline(g, h, g_sply)
    i = f - baseline           # marketing-led increment (reporting month)
    k = f * j                  # actual profit
    l = g * j                  # base profit
    m2 = h * j                 # SPLY profit
    n = i * j                  # marketing-led profit (reporting month)
    p = _romi(i, o)            # top-line ROMI
    r = _romi(n, o)            # bottom-line ROMI

    return {
        "incr_rev": i,
        "actual_profit": k,
        "base_profit": l,
        "sply_profit": m2,
        "incr_profit": n,
        "romi_top": p,
        "romi_bottom": r,
    }


def _romi(numerator, o):
    if not o:
        return 0.0
    return (numerator - o) / o
