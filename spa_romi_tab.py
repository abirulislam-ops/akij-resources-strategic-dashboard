"""
SPA Dashboard — "ROMI Analysis" tab (admin).

Read-only analytics + full admin editability:
  * correct any manual input (name/category/dates/O),
  * override computed values (F/G/H/J) AND formula outputs (I/K/L/M/N/P/R),
  * "reset to auto" clears overrides,
  * delete campaigns,
  * reconciliation (spend pool vs entered expense) and benchmark deviation.

Integrate into SPA Shared Dashboard/app.py:
    1. ensure this file + config.py + supabase_client.py + romi_logic.py
       are importable (same folder or sys.path).
    2. add "ROMI Analysis" to the sidebar radio list.
    3. add:  elif page == "ROMI Analysis": import spa_romi_tab; spa_romi_tab.page_romi()

This module talks to Supabase with the SERVICE-ROLE key (server-side), so it
is admin-only by design (the officer portal has no edit/delete controls).
"""

import datetime as dt

import pandas as pd
import streamlit as st

import romi_logic
import supabase_client as sc


def fmt_money(v):
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1e7:
        return f"{v/1e7:,.2f} Cr"
    if abs(v) >= 1e5:
        return f"{v/1e5:,.2f} L"
    return f"{v:,.0f}"


def fmt_pct(v):
    return "—" if v is None else f"{float(v)*100:,.2f}%"


def fmt_romi(v):
    return "—" if v is None else f"{float(v):,.2f}x"


OVERRIDE_FIELDS = [
    ("actual_rev", "Actual Revenue (F)", "money"),
    ("organic_rev", "Organic/Base Sales (G)", "money"),
    ("sply_rev", "SPLY Revenue (H)", "money"),
    ("gp_margin", "GP Margin % (J)", "pct"),
    ("incr_rev", "Incremental Revenue (I)", "money"),
    ("actual_profit", "Actual Profit (K)", "money"),
    ("base_profit", "Base Profit (L)", "money"),
    ("sply_profit", "SPLY Profit (M)", "money"),
    ("incr_profit", "Incremental Profit (N)", "money"),
    ("romi_top", "ROMI Top Line (P)", "romi"),
    ("romi_bottom", "ROMI Bottom Line (R)", "romi"),
]


def _effective_df():
    campaigns = sc.fetch_campaigns()
    if not campaigns:
        return None, [], {}
    sbus = {int(s["business_unit_id"]): s for s in sc.fetch_sbus()}
    rows = [romi_logic.compute_effective(c) for c in campaigns]
    return campaigns, rows, sbus


def page_romi():
    st.title("ROMI Analysis")
    st.caption("Marketing campaign ROI per SBU. Edit any value to override the "
               "auto-computed figure; 'reset' returns it to automatic.")

    campaigns, rows, sbus = _effective_df()
    if not campaigns:
        st.info("No campaigns yet — officers add them via the ROMI Officer Portal.")
        return

    label_by_id = {i: f"{s['code']} — {s['name']}" for i, s in sbus.items()}

    # ============================================================
    # 0. Month/Year filter (all months visible by default)
    # ============================================================
    months_list = sorted({c.get("report_month") for c in campaigns if c.get("report_month")}, reverse=True)
    years = sorted({m[:4] for m in months_list}, reverse=True)
    f1, f2 = st.columns(2)
    with f1:
        year_sel = st.selectbox("Year", ["All years"] + years, index=0)
    with f2:
        month_sel = st.selectbox(
            "Month", ["All months"] + list(range(1, 13)),
            index=0, format_func=lambda m: "All months" if m == "All months"
            else dt.date(2020, int(m), 1).strftime("%B"))

    def _month_match(c):
        rm = c.get("report_month")
        if not rm:
            # legacy rows without a month only show in the full "All" view
            return year_sel == "All years" and month_sel == "All months"
        y_ok = year_sel == "All years" or rm[:4] == year_sel
        m_ok = month_sel == "All months" or rm[5:7] == f"{int(month_sel):02d}"
        return y_ok and m_ok

    keep = [i for i, c in enumerate(campaigns) if _month_match(c)]
    campaigns = [campaigns[i] for i in keep]
    rows = [rows[i] for i in keep]

    if not rows:
        st.info("No campaigns match the selected filter.")
        return

    # ============================================================
    # 1. Overview KPIs
    # ============================================================
    tot = romi_logic.sbu_totals(rows)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Campaigns", tot["n_campaigns"])
    c2.metric("Total Incremental Revenue", fmt_money(tot["total_incr_rev"]))
    c3.metric("Total Marketing Expense", fmt_money(tot["total_marketing"]))
    c4.metric("Total ROMI (Top Line)", fmt_romi(tot["total_romi_top"]))

    # ============================================================
    # 2. Campaign table
    # ============================================================
    st.subheader("Campaigns")
    df = pd.DataFrame(rows)
    df["SBU"] = df["business_unit_id"].map(label_by_id)
    df["pending"] = df["actual_rev"].isna()
    df["GP Margin %"] = df["gp_margin"].apply(fmt_pct)
    for c in ["actual_rev", "organic_rev", "sply_rev", "incr_rev", "actual_profit",
              "base_profit", "sply_profit", "incr_profit", "marketing_expense"]:
        df[c] = df[c].apply(fmt_money)
    df["ROMI Top"] = df["romi_top"].apply(fmt_romi)
    df["ROMI Bottom"] = df["romi_bottom"].apply(fmt_romi)
    show_cols = ["SBU", "report_month", "campaign_name", "category", "start_date", "end_date",
                 "actual_rev", "organic_rev", "sply_rev", "incr_rev", "GP Margin %",
                 "incr_profit", "marketing_expense", "ROMI Top", "ROMI Bottom", "pending"]
    st.dataframe(df[show_cols], use_container_width=True, height=400)

    # CSV export
    csv = df[show_cols].to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "romi_campaigns.csv", "text/csv")

    # ============================================================
    # 3. SBU totals + benchmark deviation
    # ============================================================
    st.divider()
    st.subheader("SBU-wise Totals & Benchmark")
    by_bu = {}
    for r in rows:
        by_bu.setdefault(r["business_unit_id"], []).append(r)
    tot_rows = []
    for bu_id, rws in by_bu.items():
        t = romi_logic.sbu_totals(rws)
        s = sbus.get(bu_id, {})
        t["SBU"] = label_by_id.get(bu_id, str(bu_id))
        t["benchmark_top"] = s.get("benchmark_top")
        t["benchmark_bottom"] = s.get("benchmark_bottom")
        tot_rows.append(t)
    tot_df = pd.DataFrame(tot_rows)
    if not tot_df.empty:
        tot_df["deviation_top"] = tot_df.apply(
            lambda r: (r["total_romi_top"] - r["benchmark_top"]) if r["benchmark_top"] is not None else None, axis=1)
        tot_df["deviation_bottom"] = tot_df.apply(
            lambda r: (r["total_romi_bottom"] - r["benchmark_bottom"]) if r["benchmark_bottom"] is not None else None, axis=1)
        disp = tot_df[["SBU", "n_campaigns", "total_romi_top", "benchmark_top", "deviation_top",
                       "total_romi_bottom", "benchmark_bottom", "deviation_bottom"]].copy()
        disp.columns = ["SBU", "Campaigns", "ROMI Top", "Benchmark Top", "Deviation Top",
                        "ROMI Bottom", "Benchmark Bottom", "Deviation Bottom"]
        disp["ROMI Top"] = disp["ROMI Top"].apply(fmt_romi)
        disp["ROMI Bottom"] = disp["ROMI Bottom"].apply(fmt_romi)
        disp["Deviation Top"] = disp["Deviation Top"].apply(lambda v: fmt_romi(v) if v is not None else "—")
        disp["Deviation Bottom"] = disp["Deviation Bottom"].apply(lambda v: fmt_romi(v) if v is not None else "—")
        st.dataframe(disp, use_container_width=True)

    # ============================================================
    # 4. Reconciliation (pool vs entered expense)
    # ============================================================
    st.divider()
    st.subheader("Spend Reconciliation")
    st.caption("Flags campaigns where the entered marketing expense differs "
               "markedly from the ledger-derived campaign-spend pool.")
    rec = []
    for c in campaigns:
        pool = c.get("spend_pool_monthly")
        o = c.get("marketing_expense_monthly")
        if pool is None:
            continue
        pool, o = float(pool), float(o or 0)
        denom = max(pool, o, 1.0)
        rec.append({
            "SBU": label_by_id.get(c["business_unit_id"], str(c["business_unit_id"])),
            "Campaign": c["campaign_name"],
            "Entered O (monthly)": o,
            "Spend Pool (monthly)": pool,
            "Diff %": (o - pool) / denom * 100,
        })
    if rec:
        rec_df = pd.DataFrame(rec)
        rec_df["Entered O (monthly)"] = rec_df["Entered O (monthly)"].apply(fmt_money)
        rec_df["Spend Pool (monthly)"] = rec_df["Spend Pool (monthly)"].apply(fmt_money)
        rec_df["Diff %"] = rec_df["Diff %"].apply(lambda v: f"{v:,.0f}%")
        st.dataframe(rec_df, use_container_width=True)
    else:
        st.info("No reconciled spend yet (run refresh.py on-premise).")

    # ============================================================
    # 5. Edit / override
    # ============================================================
    st.divider()
    st.subheader("Edit a Campaign (admin)")
    options = {f"#{c['id']} — {label_by_id.get(c['business_unit_id'])} — {c['campaign_name']}": c
               for c in campaigns}
    sel = st.selectbox("Select campaign", list(options.keys()))
    c = options[sel]
    eff = romi_logic.compute_effective(c)

    with st.form("edit_form"):
        st.markdown("#### Manual fields")
        m1, m2 = st.columns(2)
        with m1:
            campaign_name = st.text_input("Campaign Name", value=c["campaign_name"])
            category = st.selectbox("Category", ["ATL", "BTL", "Other"],
                                    index=["ATL", "BTL", "Other"].index(c.get("category") or "Other"))
            rm_options = list(dict.fromkeys([c.get("report_month")] + romi_logic.month_options()))
            report_month = st.selectbox("Reporting Month", rm_options,
                                        index=rm_options.index(c.get("report_month")) if c.get("report_month") in rm_options else 0)
        with m2:
            start_date = st.date_input("Start Date", value=dt.date.fromisoformat(c["start_date"]) if isinstance(c["start_date"], str) else c["start_date"])
            end_date = st.date_input("End Date", value=dt.date.fromisoformat(c["end_date"]) if isinstance(c["end_date"], str) else c["end_date"])
        marketing_expense = st.number_input("Marketing Expense (monthly, BDT) — O",
                                            value=float(eff["marketing_expense"] or 0), step=1000.0, format="%.0f")

        st.markdown("#### Override computed / formula values")
        st.caption("Tick 'Override' and edit the value to force a figure; "
                   "leave unticked to keep automatic.")
        apply_ov = {}
        ov_vals = {}
        for col, label, kind in OVERRIDE_FIELDS:
            default = eff[col]
            auto_disp = (f"{default*100:.2f}%" if kind == "pct"
                         else (f"{default:,.4f}x" if kind == "romi" else fmt_money(default)))
            is_overridden = (c.get(f"{col}_ov") is not None)
            c1, c2 = st.columns([1, 3])
            with c1:
                apply_ov[col] = st.checkbox("Override", value=is_overridden,
                                            key=f"apply_{c['id']}_{col}")
            with c2:
                if kind == "pct":
                    ov_vals[col] = st.number_input(f"{label}  (auto: {auto_disp})",
                                                   value=float(default or 0), step=0.001, format="%.4f",
                                                   key=f"val_{c['id']}_{col}")
                elif kind == "romi":
                    ov_vals[col] = st.number_input(f"{label}  (auto: {auto_disp})",
                                                   value=float(default or 0), step=0.01, format="%.4f",
                                                   key=f"val_{c['id']}_{col}")
                else:
                    ov_vals[col] = st.number_input(f"{label}  (auto: {auto_disp})",
                                                   value=float(default or 0), step=1000.0, format="%.0f",
                                                   key=f"val_{c['id']}_{col}")

        save = st.form_submit_button("Save changes", use_container_width=True)

    c_reset, c_del = st.columns(2)
    with c_reset:
        if st.button("Reset all overrides to auto", use_container_width=True):
            sc.update_campaign(c["id"], {f"{k}_ov": None for k, _, _ in OVERRIDE_FIELDS})
            st.rerun()
    with c_del:
        if st.button("Delete campaign", use_container_width=True):
            sc.delete_campaign(c["id"])
            st.rerun()

    if save:
        updates = {
            "campaign_name": campaign_name,
            "category": category,
            "report_month": report_month,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "marketing_expense_monthly": float(marketing_expense),
            "edited_by": "admin",
            "edited_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        for col, _, _ in OVERRIDE_FIELDS:
            if apply_ov.get(col):
                updates[f"{col}_ov"] = float(ov_vals[col])
            else:
                updates[f"{col}_ov"] = None  # reset to auto
        try:
            sc.update_campaign(c["id"], updates)
            st.success("Saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")
