"""
Refresh engine — recompute ROMI base metrics for all campaigns from the DWH
and write results back to Supabase.

Invoked from the SPA dashboard "ROMI Analysis" tab via the "Refresh from DWH"
button, and also runnable on-premise (needs DWH + ODBC access):

    python refresh.py

Preserves admin overrides: only the computed columns are rewritten; the
*_ov override columns are never touched.
"""

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dwh
import engine
import supabase_client as sc


def refresh_one(campaign, gp_margin_by_bu):
    bu_id = int(campaign["business_unit_id"])
    start = campaign["start_date"]
    end = campaign["end_date"]
    if isinstance(start, str):
        start = dt.date.fromisoformat(start)
    if isinstance(end, str):
        end = dt.date.fromisoformat(end)

    gp_margin = gp_margin_by_bu.get(bu_id)
    report_month = campaign.get("report_month")
    m = engine.compute_metrics(
        bu_id, start, end, gp_margin=gp_margin, report_month=report_month
    )

    updates = {
        "actual_rev": m["f"],
        "organic_rev": m["g"],
        "organic_rev_sply": m["g_sply"],
        "sply_rev": m["h"],
        "gp_margin": m["j"],
        "spend_pool_total": m["pool_total"],
        "n_months": m["n_months"],
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    warnings = []
    name = campaign.get("campaign_name") or campaign.get("id")
    if m.get("short_campaign"):
        days = max(1, (end - start).days)
        warnings.append(
            f"{name}: campaign spans only {days} day(s) — monthly ROMI "
            "attribution is unreliable for such short events."
        )
    o = campaign.get("marketing_expense_total")
    pool = m["pool_total"]
    if pool and o:
        dev = (float(o) - pool) / max(pool, float(o), 1.0)
        if abs(dev) > 0.2:
            warnings.append(
                f"{name}: entered expense (O) differs from the DWH spend pool "
                f"by {dev*100:+,.0f}% — please reconcile."
            )

    return updates, warnings


def refresh_all(verbose=False):
    """Refresh every campaign. Returns {total, updated, errors, warnings}."""
    if verbose:
        print("  Fetching SBU list...", flush=True)
    sbus = sc.fetch_sbus()
    gp_margin_by_bu = {int(s["business_unit_id"]): s.get("gp_margin") for s in sbus}

    if verbose:
        print("  Fetching campaigns...", flush=True)
    campaigns = sc.fetch_campaigns()
    updated = 0
    errors = []
    warnings = []
    for i, c in enumerate(campaigns, 1):
        try:
            if verbose:
                print(f"  [{i}/{len(campaigns)}] {c.get('campaign_name')}", flush=True)
            updates, warns = refresh_one(c, gp_margin_by_bu)
            sc.update_campaign(c["id"], updates)
            updated += 1
            warnings.extend(warns)
        except Exception as e:
            errors.append(f"{c.get('campaign_name') or c.get('id')}: {e}")
    return {"total": len(campaigns), "updated": updated,
            "errors": errors, "warnings": warnings}


if __name__ == "__main__":
    r = refresh_all()
    print(f"Refreshing {r['total']} campaign(s) from DWH...")
    for w in r["warnings"]:
        print(f"  [warn] {w}")
    for e in r["errors"]:
        print(f"  [skip] {e}")
    print(f"Done. Updated {r['updated']} campaign(s).")
