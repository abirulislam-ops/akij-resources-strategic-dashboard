"""
DWH (main database) access layer — read-only queries for ROMI computation.

All revenue / spend / COGS numbers come from fin.tblAccountingJournalArc,
keyed by intBusinessUnitId (the "SBU" a marketing officer selects).

Sign convention in the journal:
  * Revenue (3010001 / 3010002) is CREDIT -> stored negative.
  * Marketing (4210001) and COGS (4810001) are DEBIT -> stored positive,
    but COGS can carry negative reversal entries (so it is netted, not abs'd).
"""

import datetime as dt

import pyodbc

import config


def _conn():
    d = config.DWH
    return pyodbc.connect(
        f"DRIVER={d['driver']};SERVER={d['server']};DATABASE={d['database']};"
        f"UID={d['user']};PWD={d['password']};"
        "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=60;"
    )


def _monthly_series(bu_id, gl_codes, start_date, end_date, mode):
    """Return {year*100+month: amount} summed over a (inclusive) date range.

    mode:
      'credit'  -> revenue  : filter numAmount<0, return -numAmount (positive)
      'debit'   -> marketing: filter numAmount>0, return  numAmount (positive)
      'net'     -> COGS     : return  numAmount (signed, reversals net out)
    """
    placeholders = ",".join("?" for _ in gl_codes)
    if mode == "credit":
        expr = "SUM(-numAmount)"
        extra = "AND numAmount < 0"
    elif mode == "debit":
        expr = "SUM(numAmount)"
        extra = "AND numAmount > 0"
    else:  # net
        expr = "SUM(numAmount)"
        extra = ""

    sql = f"""
        SELECT YEAR(dteTransactionDate) y, MONTH(dteTransactionDate) m, {expr}
        FROM fin.tblAccountingJournalArc
        WHERE intBusinessUnitId = ?
          AND strGeneralLedgerCode IN ({placeholders})
          AND isActive = 1
          {extra}
          AND dteTransactionDate >= ?
          AND dteTransactionDate < ?
        GROUP BY YEAR(dteTransactionDate), MONTH(dteTransactionDate)
    """
    params = [bu_id] + list(gl_codes) + [start_date, end_date]
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        out = {}
        for y, m, amt in cur.fetchall():
            key = y * 100 + m
            out[key] = out.get(key, 0.0) + (float(amt or 0))
        return out
    finally:
        conn.close()


def revenue_monthly(bu_id, start_date, end_date):
    """Monthly sales revenue (positive values)."""
    return _monthly_series(bu_id, config.GL_REVENUE, start_date, end_date, "credit")


def cogs_monthly(bu_id, start_date, end_date):
    """Monthly cost of goods sold (signed; reversals net out)."""
    return _monthly_series(bu_id, config.GL_COGS, start_date, end_date, "net")


def marketing_monthly(bu_id, start_date, end_date):
    """Monthly marketing spend (debit only), split into full total and
    campaign-able "pool" (excludes non-campaign sub-GL categories)."""
    excl = " OR ".join(
        [f"LOWER(strSubGLName) LIKE ?" for _ in config.NON_CAMPAIGN_SUBGL_KEYWORDS]
    )
    sql = f"""
        SELECT YEAR(dteTransactionDate) y, MONTH(dteTransactionDate) m,
               SUM(numAmount) amt,
               SUM(CASE WHEN ({excl}) THEN 0 ELSE numAmount END) pool
        FROM fin.tblAccountingJournalArc
        WHERE intBusinessUnitId = ?
          AND strGeneralLedgerCode = ?
          AND numAmount > 0 AND isActive = 1
          AND dteTransactionDate >= ?
          AND dteTransactionDate < ?
        GROUP BY YEAR(dteTransactionDate), MONTH(dteTransactionDate)
    """
    likes = ["%" + k + "%" for k in config.NON_CAMPAIGN_SUBGL_KEYWORDS]
    params = likes + [bu_id, config.GL_MARKETING, start_date, end_date]
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        full, pool = {}, {}
        for y, m, amt, p in cur.fetchall():
            key = y * 100 + m
            full[key] = full.get(key, 0.0) + float(amt or 0)
            pool[key] = pool.get(key, 0.0) + float(p or 0)
        return full, pool
    finally:
        conn.close()


def gp_margin(bu_id, start_date, end_date):
    """Gross profit margin over a period = (Revenue - COGS) / Revenue."""
    rev = sum(revenue_monthly(bu_id, start_date, end_date).values())
    cogs = sum(cogs_monthly(bu_id, start_date, end_date).values())
    if not rev:
        return None
    return (rev - cogs) / rev


def list_sbus(active_only=True):
    """Business units from dco.tblbusinessunitArc -> [(id, code, name, active)]."""
    sql = """
        SELECT intBusinessUnitId, strBusinessUnitCode, strBusinessUnitName, isActive
        FROM dco.tblbusinessunitArc
        ORDER BY strBusinessUnitName
    """
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = []
        for bu, code, name, active in cur.fetchall():
            if active_only and not active:
                continue
            rows.append((int(bu), (code or "").strip(), (name or "").strip(), bool(active)))
        return rows
    finally:
        conn.close()


def month_key(year, month):
    return year * 100 + month


def parse_ym(d):
    return d.year * 100 + d.month


def shift_ym(key, delta_months):
    """Shift a year*100+month key by delta_months."""
    y, m = divmod(key, 100)
    m += delta_months
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return y * 100 + m


def key_to_date(key, month_end=False):
    """year*100+month -> date (first day, or last day if month_end)."""
    y, m = divmod(key, 100)
    if month_end:
        return dt.date(y, m, 1) + dt.timedelta(days=32)
    return dt.date(y, m, 1)


def key_after(key):
    """First day of the month AFTER key (exclusive upper bound)."""
    nxt = shift_ym(key, 1)
    return key_to_date(nxt)
