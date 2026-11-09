"""
Live ERP (iBOSDDD) access layer — read-only ROMI queries via the
enterprise-api-gateway MCP endpoint.

The retired DWH (pyodbc -> 203.202.241.211) is gone. All revenue / spend /
COGS numbers now come from fin.tblAccountingJournal in the live ERP, keyed by
intBusinessUnitId (the "SBU" a marketing officer selects).

Sign convention in the journal:
  * Revenue (3010001 / 3010002) is CREDIT -> stored negative.
  * Marketing (4210001) and COGS (4810001) are DEBIT -> stored positive,
    but COGS can carry negative reversal entries (so it is netted, not abs'd).
"""

import datetime as dt
import json
import os

import requests


def _config():
    """Resolve gateway + GL settings without hard-requiring config.py (which is
    git-ignored because it holds secrets). Order: env vars -> Streamlit
    secrets -> config.py -> defaults."""
    try:
        import config as cfg
    except Exception:
        cfg = None

    def env_or(key, fallback):
        v = os.environ.get(key)
        if v:
            return v
        try:
            import streamlit as st
            v = st.secrets.get(key)
            if v:
                return v
        except Exception:
            pass
        return fallback

    gw = (getattr(cfg, "GATEWAY", {}) if cfg else {}) or {}
    return {
        "GATEWAY": {
            "url": env_or(
                "GATEWAY_URL", gw.get("url", "https://enterprise-api-gateway.ibos.agency/mcp")
            ),
            "token": env_or("GATEWAY_TOKEN", gw.get("token", "")),
            "device_id": env_or("GATEWAY_DEVICE_ID", gw.get("device_id", "")),
            "timeout": int(gw.get("timeout", 300)),
        },
        "GL_REVENUE": getattr(cfg, "GL_REVENUE", ["3010001", "3010002"]),
        "GL_COGS": getattr(cfg, "GL_COGS", ["4810001"]),
        "GL_MARKETING": getattr(cfg, "GL_MARKETING", "4210001"),
        "NON_CAMPAIGN_SUBGL_KEYWORDS": getattr(cfg, "NON_CAMPAIGN_SUBGL_KEYWORDS", [
            "commission", "discount", "salary", "allowence", "bonus",
            "provident", "gratuity", "leave", "overtime", "utility",
            "it expenses", "bad debt", "mro", "telephone", "transportation",
            "fooding", "loading", "insurance",
        ]),
    }


_cfg = _config()
_GW_ID = [0]


def _lit(value):
    """Render a Python value as a SQL literal (gateway takes raw SQL, no binds)."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return "'" + value.isoformat() + "'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(f"unsupported SQL param type: {type(value)!r}")


def _query(sql):
    """Run one read-only SELECT against the live ERP; return rows as dicts."""
    gw = _cfg["GATEWAY"]
    _GW_ID[0] += 1
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {gw['token']}",
        "X-Device-Id": gw["device_id"],
    }
    body = {
        "jsonrpc": "2.0",
        "id": _GW_ID[0],
        "method": "tools/call",
        "params": {
            "name": "execute_readonly_query",
            "arguments": {"sql": sql, "limit": 500},
        },
    }
    r = requests.post(gw["url"], headers=headers, json=body, timeout=gw["timeout"])
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(
            f"gateway error {payload['error'].get('code')}: {payload['error'].get('message')}"
        )
    result = payload.get("result") or {}
    if result.get("isError"):
        raise RuntimeError("gateway tool error")
    content = result.get("content") or []
    if not content:
        return []
    data = json.loads(content[0].get("text", "{}"))
    return data.get("rows") or []


def _monthly_series(bu_id, gl_codes, start_date, end_date, mode):
    """Return {year*100+month: amount} summed over a (inclusive) date range.

    mode:
      'credit'  -> revenue  : filter numAmount<0, return -numAmount (positive)
      'debit'   -> marketing: filter numAmount>0, return  numAmount (positive)
      'net'     -> COGS     : return  numAmount (signed, reversals net out)
    """
    inlist = ",".join(_lit(c) for c in gl_codes)
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
        SELECT YEAR(dteTransactionDate) AS y, MONTH(dteTransactionDate) AS m,
               {expr} AS amt
        FROM fin.tblAccountingJournal
        WHERE intBusinessUnitId = {_lit(bu_id)}
          AND strGeneralLedgerCode IN ({inlist})
          AND isActive = 1
          {extra}
          AND dteTransactionDate >= {_lit(start_date)}
          AND dteTransactionDate < {_lit(end_date)}
        GROUP BY YEAR(dteTransactionDate), MONTH(dteTransactionDate)
    """
    out = {}
    for row in _query(sql):
        key = int(row["y"]) * 100 + int(row["m"])
        out[key] = out.get(key, 0.0) + (float(row["amt"] or 0))
    return out


def revenue_monthly(bu_id, start_date, end_date):
    """Monthly sales revenue (positive values)."""
    return _monthly_series(bu_id, _cfg["GL_REVENUE"], start_date, end_date, "credit")


def cogs_monthly(bu_id, start_date, end_date):
    """Monthly cost of goods sold (signed; reversals net out)."""
    return _monthly_series(bu_id, _cfg["GL_COGS"], start_date, end_date, "net")


def marketing_monthly(bu_id, start_date, end_date):
    """Monthly marketing spend (debit only), split into full total and
    campaign-able "pool" (excludes non-campaign sub-GL categories)."""
    excl = " OR ".join(
        [f"LOWER(strSubGLName) LIKE {_lit('%' + k + '%')}"
         for k in _cfg["NON_CAMPAIGN_SUBGL_KEYWORDS"]]
    )
    sql = f"""
        SELECT YEAR(dteTransactionDate) AS y, MONTH(dteTransactionDate) AS m,
               SUM(numAmount) AS amt,
               SUM(CASE WHEN ({excl}) THEN 0 ELSE numAmount END) AS pool
        FROM fin.tblAccountingJournal
        WHERE intBusinessUnitId = {_lit(bu_id)}
          AND strGeneralLedgerCode = {_lit(_cfg["GL_MARKETING"])}
          AND numAmount > 0 AND isActive = 1
          AND dteTransactionDate >= {_lit(start_date)}
          AND dteTransactionDate < {_lit(end_date)}
        GROUP BY YEAR(dteTransactionDate), MONTH(dteTransactionDate)
    """
    full, pool = {}, {}
    for row in _query(sql):
        key = int(row["y"]) * 100 + int(row["m"])
        full[key] = full.get(key, 0.0) + float(row["amt"] or 0)
        pool[key] = pool.get(key, 0.0) + float(row["pool"] or 0)
    return full, pool


def gp_margin(bu_id, start_date, end_date):
    """Gross profit margin over a period = (Revenue - COGS) / Revenue."""
    rev = sum(revenue_monthly(bu_id, start_date, end_date).values())
    cogs = sum(cogs_monthly(bu_id, start_date, end_date).values())
    if not rev:
        return None
    return (rev - cogs) / rev


def list_sbus(active_only=True):
    """Business units from dco.tblBusinessUnit -> [(id, code, name, active)]."""
    sql = """
        SELECT intBusinessUnitId AS id, strBusinessUnitCode AS code,
               strBusinessUnitName AS name, isActive AS active
        FROM dco.tblBusinessUnit
        ORDER BY strBusinessUnitName
    """
    rows = []
    for r in _query(sql):
        if active_only and not r["active"]:
            continue
        rows.append((
            int(r["id"]),
            (r["code"] or "").strip(),
            (r["name"] or "").strip(),
            bool(r["active"]),
        ))
    return rows


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
