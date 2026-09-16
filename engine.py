"""
Compute engine — derives the ROMI base metrics (F, G, H, J, spend pool)
and the formula columns (I, K, L, M, N, P, R) for one campaign.

Template-faithful, MONTHLY basis (matches "ROMI tamplate and formula.xlsx"):

  F  actual revenue  = average *monthly* revenue over the campaign period.
  G  organic/base    = average monthly revenue over the 6 months BEFORE the
                       campaign start date (plain average, no marketing filter).
  H  SPLY revenue    = average monthly revenue of the same campaign months,
                       one year earlier.
  O  marketing expense = the campaign's expense entered by the officer.

The campaign period is capped at the reporting month, so a campaign whose
end date lies in the future is only scored over the months that have
actually elapsed (monthly reporting scope).
"""

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


def _months_between(start_date, end_date):
    """Ordered list of year*100+month keys spanned by the campaign (inclusive)."""
    keys = []
    y, m = start_date.year, start_date.month
    ey, em = end_date.year, end_date.month
    while (y, m) <= (ey, em):
        keys.append(y * 100 + m)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return keys


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


def compute_metrics(bu_id, start_date, end_date, gp_margin=None, report_month=None):
    """Compute F (actual), G (organic), H (SPLY), J (gp margin) and spend pool."""
    camp_months = _months_between(start_date, end_date)
    cap = _to_key(report_month)
    if cap is not None:
        camp_months = [k for k in camp_months if k <= cap]
    n_months = max(len(camp_months), 1)

    camp_from = dwh.key_to_date(camp_months[0])
    camp_to = dwh.key_after(camp_months[-1])

    # ---- F: monthly-average campaign revenue ----
    rev = dwh.revenue_monthly(bu_id, camp_from, camp_to)
    f = sum(rev.get(k, 0.0) for k in camp_months) / n_months

    # ---- H: monthly-average SPLY (same months, one year earlier) ----
    sply_months = [dwh.shift_ym(k, -12) for k in camp_months]
    sply_from = dwh.key_to_date(min(sply_months))
    sply_to = dwh.key_after(max(sply_months))
    rev_sply = dwh.revenue_monthly(bu_id, sply_from, sply_to)
    h = sum(rev_sply.get(k, 0.0) for k in sply_months) / n_months

    # ---- G: organic/base = plain average of the 6 months before campaign start ----
    start_key = camp_months[0]
    lookback_keys = [dwh.shift_ym(start_key, -i)
                     for i in range(1, config.ORGANIC_LOOKBACK_MONTHS + 1)]
    lb_from = dwh.key_to_date(min(lookback_keys))
    lb_to = dwh.key_after(max(lookback_keys))
    rev_lb = dwh.revenue_monthly(bu_id, lb_from, lb_to)
    g = sum(rev_lb.get(k, 0.0) for k in lookback_keys) / config.ORGANIC_LOOKBACK_MONTHS

    # ---- J: GP margin (fixed per SBU; compute FY on demand if not supplied) ----
    if gp_margin is None:
        gp_margin = dwh.gp_margin(bu_id, config.GP_MARGIN_FY_START, config.GP_MARGIN_FY_END)

    # ---- Spend pool: campaign-able marketing over the campaign window ----
    _, pool = dwh.marketing_monthly(bu_id, camp_from, camp_to)
    pool_total = sum(pool.get(k, 0.0) for k in camp_months)

    return {
        "f": f,
        "g": g,
        "h": h,
        "j": gp_margin,
        "pool_total": pool_total,
        "n_months": n_months,
        "campaign_months": camp_months,
    }


def derive_formulas(m, o):
    """Compute the formula columns from base metrics (m) + campaign expense (o)."""
    f = m["f"]
    g = m["g"]
    h = m["h"]
    j = (m["j"] or 0.0)

    i = f - g                # marketing led increment (monthly)
    k = f * j                # actual profit
    l = g * j                # base profit
    m2 = h * j               # SPLY profit
    n = i * j                # marketing led profit
    p = _romi(i, o)          # top-line ROMI
    r = _romi(n, o)          # bottom-line ROMI

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
