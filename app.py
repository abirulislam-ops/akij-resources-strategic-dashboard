"""
Akij Resources — SPA Shared Dashboard (Streamlit)

Colleagues access from anywhere. Requires login (Supabase Auth).
Reads the Supabase branch. Includes SBU filters, month/year range,
SBU full analysis, SBU Strategic Gap Analysis, and manual SQL.

Deploy to Streamlit Cloud with secrets:
    SUPABASE_URL, SUPABASE_ANON_KEY,
    READER_DB_HOST, READER_DB_PORT, READER_DB_DATABASE,
    READER_DB_USER, READER_DB_PASSWORD
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
from datetime import datetime

import supabase_data as sd

st.set_page_config(
    page_title="SPA — Strategic Planning Dashboard",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# HELPERS
# ============================================================
def format_currency(val):
    if val is None:
        return "—"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    if v != v:  # NaN
        return "—"
    if abs(v) >= 10000000:
        return f"{v/10000000:,.2f} Cr"
    if abs(v) >= 100000:
        return f"{v/100000:,.2f} L"
    return f"{v:,.0f}"


def to_excel_bytes(dfs: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        for name, df in dfs.items():
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=str(name)[:31], index=False)
    return buf.getvalue()


def _download(df, label, filename):
    if df is not None and not df.empty:
        st.download_button(
            label, data=to_excel_bytes({"data": df}),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def _bu_list(session):
    """Return the business_unit DataFrame, cached in session state."""
    if "bu_df" not in st.session_state:
        st.session_state["bu_df"] = sd.fetch_all(session, "business_unit")
    return st.session_state["bu_df"]


def _bu_label(bu_df):
    """Map short_code -> 'CODE (active)' or 'CODE (inactive)'."""
    def lbl(row):
        code = row["short_code"] or str(row["business_unit_id"])
        tag = "active" if row["is_active"] else "inactive"
        return f"{code} ({tag})"
    bu_df["label"] = bu_df.apply(lbl, axis=1)
    return bu_df


def sidebar_filters(session):
    """Shared month/year range + SBU multi-select (select-all) filters."""
    bu_df = _bu_label(_bu_list(session))
    codes = sorted(bu_df["short_code"].dropna().unique().tolist())

    st.sidebar.markdown("### Filters")

    # Month/year range
    st.sidebar.markdown("**Date range (month/year)**")
    yc1, mc1 = st.sidebar.columns(2)
    with yc1:
        start_year = st.selectbox("From Year", list(range(2026, 2019, -1)), index=0, key="f_start_year")
    with mc1:
        start_month = st.selectbox("From Month", list(range(1, 13)), index=0, key="f_start_month",
                                   format_func=lambda m: datetime(2020, m, 1).strftime("%b"))
    yc2, mc2 = st.sidebar.columns(2)
    with yc2:
        end_year = st.selectbox("To Year", list(range(2026, 2019, -1)), index=0, key="f_end_year")
    with mc2:
        end_month = st.selectbox("To Month", list(range(1, 13)), index=11, key="f_end_month",
                                 format_func=lambda m: datetime(2020, m, 1).strftime("%b"))

    # SBU multi-select with select-all
    st.sidebar.markdown("**SBU filter**")
    all_on = st.sidebar.toggle("Select all SBUs", value=True, key="f_all_sbu")
    if all_on:
        selected = codes
    else:
        selected = st.sidebar.multiselect("SBUs", codes, default=codes[:10], key="f_sbu")
    if not selected:
        selected = []

    return {
        "bu_df": bu_df,
        "codes": selected,
        "start": (start_year, start_month),
        "end": (end_year, end_month),
    }


def _in_month_range(df, year_col, month_col, start, end):
    sy, sm = start
    ey, em = end
    start_key = sy * 100 + sm
    end_key = ey * 100 + em
    key = df[year_col].astype(int) * 100 + df[month_col].astype(int)
    return df[(key >= start_key) & (key <= end_key)]


# ============================================================
# LOGIN
# ============================================================
def login_screen():
    st.markdown("# 🔐 SPA — Strategic Planning Dashboard")
    st.markdown("Sign in with your Akij Resources account to continue.")
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        email = st.text_input("Email", placeholder="you@akijresource.com")
        password = st.text_input("Password", type="password")
        if st.button("Sign in", use_container_width=True):
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                session, err = sd.sign_in(email.strip(), password)
                if err:
                    st.error(err)
                else:
                    st.session_state["session"] = session
                    st.session_state["email"] = email.strip()
                    st.rerun()


# ============================================================
# MAIN APP
# ============================================================
def main_app():
    session = st.session_state["session"]

    st.sidebar.title("SPA Dashboard")
    page = st.sidebar.radio(
        "Navigate",
        ["Overview", "SBU Analysis", "Financial", "Inventory", "Sales", "Budget",
         "Employees", "Production", "SBU Strategic Gap Analysis", "Manual SQL"],
    )

    st.sidebar.divider()
    st.sidebar.markdown(f"Signed in as **{st.session_state.get('email', '')}**")
    if st.sidebar.button("Sign out"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    filters = sidebar_filters(session)

    if page == "Overview":
        page_overview(session, filters)
    elif page == "SBU Analysis":
        page_sbu_analysis(session, filters)
    elif page == "Financial":
        page_financial(session, filters)
    elif page == "Inventory":
        page_inventory(session, filters)
    elif page == "Sales":
        page_sales(session, filters)
    elif page == "Budget":
        page_budget(session, filters)
    elif page == "Employees":
        page_employees(session, filters)
    elif page == "Production":
        page_production(session, filters)
    elif page == "SBU Strategic Gap Analysis":
        page_gap_analysis(session)
    elif page == "Manual SQL":
        page_manual_sql()


# ============================================================
# PAGES
# ============================================================
def page_overview(session, f):
    st.markdown("## Overview")
    st.caption("Company-wise totals from the branch database.")

    bu = f["bu_df"]
    emp_count = sd.fetch_count(session, "employee")
    active_count = sd.fetch_count(session, "employee", filters={"is_active": "true"})

    c1, c2, c3 = st.columns(3)
    c1.metric("Business Units", len(bu))
    c2.metric("Employees", f"{emp_count:,}")
    c3.metric("Active Employees", f"{active_count:,}")

    st.divider()
    st.markdown("### Employees by Company (active vs inactive)")
    emp = sd.fetch_all(session, "employee", columns="business_unit_id,is_active")
    if not emp.empty and not bu.empty:
        bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
        emp["company"] = emp["business_unit_id"].map(bmap)
        emp["status"] = emp["is_active"].map({True: "Active", False: "Inactive"})
        counts = emp.groupby(["company", "status"]).size().reset_index(name="Employees")
        counts = counts.sort_values("Employees", ascending=False)
        fig = px.bar(counts, x="company", y="Employees", color="status",
                     title="Employees by Company", barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Business Unit list")
    show = bu[["short_code", "business_unit", "is_active"]].rename(
        columns={"short_code": "Code", "business_unit": "Business Unit", "is_active": "Active"})
    st.dataframe(show, use_container_width=True, height=400)


def page_financial(session, f):
    st.markdown("## Financial Performance (Monthly)")
    df = sd.fetch_all(session, "summary_finance_monthly", max_rows=200000)
    if df.empty:
        st.info("No financial summary data yet.")
        return
    if f["codes"]:
        df = df[df["company"].isin(f["codes"])]
    df = _in_month_range(df, "year", "month", f["start"], f["end"])

    trend = df.groupby(["year", "month"], as_index=False)["total_amount"].sum()
    trend["period"] = trend["year"].astype(str) + "-" + trend["month"].astype(str).str.zfill(2)
    fig = px.line(trend, x="period", y="total_amount", title="Total Amount by Month")
    st.plotly_chart(fig, use_container_width=True)

    by_isgroup = df.groupby("is_group", as_index=False)["total_amount"].sum().sort_values("total_amount")
    fig2 = px.bar(by_isgroup, x="total_amount", y="is_group", orientation="h", title="Total by IS Group")
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df, use_container_width=True)
    _download(df, "Download Financial (Excel)", f"financial_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_inventory(session, f):
    st.markdown("## Inventory (Monthly Summary)")
    df = sd.fetch_all(session, "summary_inventory_monthly", max_rows=200000)
    if df.empty:
        st.info("No inventory data yet.")
        return
    if f["codes"]:
        df = df[df["company"].isin(f["codes"])]
    df = _in_month_range(df, "year", "month", f["start"], f["end"])

    d = df.groupby(["year", "month"], as_index=False)[["total_qty", "total_value"]].sum()
    d["period"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    fig = px.bar(d, x="period", y="total_value", title="Inventory Value by Month")
    st.plotly_chart(fig, use_container_width=True)

    by_type = df.groupby("stock_type", as_index=False)["total_value"].sum().sort_values("total_value", ascending=False)
    fig2 = px.pie(by_type, names="stock_type", values="total_value", title="Value by Stock Type")
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df, use_container_width=True)
    _download(df, "Download Inventory (Excel)", f"inventory_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_sales(session, f):
    st.markdown("## Sales (Monthly Summary)")
    df = sd.fetch_all(session, "summary_sales_monthly", max_rows=200000)
    if df.empty:
        st.info("No sales data yet.")
        return
    if f["codes"]:
        df = df[df["company"].isin(f["codes"])]
    df = _in_month_range(df, "year", "month", f["start"], f["end"])

    d = df.groupby(["year", "month"], as_index=False).agg(
        {"order_count": "sum", "total_order_value": "sum"})
    d["period"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    fig = px.bar(d, x="period", y="total_order_value", title="Sales Value by Month")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
    _download(df, "Download Sales (Excel)", f"sales_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_budget(session, f):
    st.markdown("## Budget")
    df = sd.fetch_all(session, "budget_row", columns="business_unit_id,year_id,month_id,amount", max_rows=300000)
    if df.empty:
        st.info("No budget data yet.")
        return
    bu = f["bu_df"]
    bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
    df["company"] = df["business_unit_id"].map(bmap)
    if f["codes"]:
        df = df[df["company"].isin(f["codes"])]
    df = _in_month_range(df, "year_id", "month_id", f["start"], f["end"])

    d = df.groupby(["year_id", "month_id"], as_index=False)["amount"].sum()
    d["period"] = d["year_id"].astype(str) + "-" + d["month_id"].astype(str).str.zfill(2)
    fig = px.bar(d, x="period", y="amount", title="Budget by Month")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
    _download(df, "Download Budget (Excel)", f"budget_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_employees(session, f):
    st.markdown("## Employees")
    emp = sd.fetch_all(session, "employee", max_rows=50000)
    if emp.empty:
        st.info("No employee data yet.")
        return
    det = sd.fetch_all(session, "employee_details", max_rows=50000)
    dept = sd.fetch_all(session, "department")
    desig = sd.fetch_all(session, "designation")
    sec = sd.fetch_all(session, "section")
    bu = f["bu_df"]

    # Merge details
    if not det.empty:
        det = det.drop_duplicates(subset="employee_id", keep="first")
        emp = emp.merge(det, on="employee_id", how="left", suffixes=("", "_d"))

    # Maps
    bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
    dmap = dict(zip(dept["department_id"], dept["department"]))
    gmap = dict(zip(desig["designation_id"], desig["designation"]))
    smap = dict(zip(sec["section_id"], sec["section_name"]))
    emp["company"] = emp["business_unit_id"].map(bmap)
    emp["department"] = emp["department_id"].map(dmap)
    emp["designation"] = emp["designation_id"].map(gmap)
    emp["section"] = emp["section_id"].map(smap)

    # Filters row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        f_sbu = st.selectbox("SBU", ["All"] + sorted(emp["company"].dropna().unique().tolist()))
    with c2:
        f_dept = st.selectbox("Department", ["All"] + sorted(emp["department"].dropna().unique().tolist()))
    with c3:
        f_pay = st.selectbox("Salary unit (payroll)", ["All"] + sorted(emp["payroll_group"].dropna().unique().tolist()))
    with c4:
        f_status = st.selectbox("Status", ["All", "Active", "Inactive"])

    q = st.text_input("Search by name / code / email")

    show = emp.copy()
    if f_sbu != "All":
        show = show[show["company"] == f_sbu]
    if f_dept != "All":
        show = show[show["department"] == f_dept]
    if f_pay != "All":
        show = show[show["payroll_group"] == f_pay]
    if f_status == "Active":
        show = show[show["is_active"] == True]
    elif f_status == "Inactive":
        show = show[show["is_active"] == False]
    if q:
        q = q.lower()
        show = show[
            show["employee_name"].astype(str).str.lower().str.contains(q, na=False)
            | show["employee_code"].astype(str).str.lower().str.contains(q, na=False)
            | show["office_mail"].astype(str).str.lower().str.contains(q, na=False)
        ]

    cols = ["employee_code", "employee_name", "company", "department", "designation", "section",
            "joining_date", "office_mail", "office_mobile", "personal_mobile",
            "payroll_group", "employee_status", "is_active"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True, height=500)
    _download(show[cols], "Download Employees (Excel)", f"employees_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_production(session, f):
    st.markdown("## Production Orders")
    df = sd.fetch_all(session, "production_order", max_rows=150000)
    if df.empty:
        st.info("No production data yet.")
        return
    bu = f["bu_df"]
    bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
    df["company"] = df["business_unit_id"].map(bmap)
    if f["codes"]:
        df = df[df["company"].isin(f["codes"])]

    d = df.groupby("company", as_index=False)["order_qty"].sum().sort_values("order_qty", ascending=False)
    fig = px.bar(d, x="company", y="order_qty", title="Total Order Quantity by Company")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
    _download(df, "Download Production (Excel)", f"production_{datetime.now():%Y%m%d_%H%M}.xlsx")


# ============================================================
# SBU FULL ANALYSIS (Phase C)
# ============================================================
def page_sbu_analysis(session, f):
    st.markdown("## SBU Full Analysis")
    bu = _bu_label(f["bu_df"])
    options = sorted(bu["label"].dropna().unique().tolist())
    sel = st.selectbox("Select an SBU", options)
    code = sel.split(" (")[0]
    bu_row = bu[bu["short_code"] == code]
    bu_id = int(bu_row["business_unit_id"].iloc[0]) if not bu_row.empty else None

    st.markdown(f"### {code} — Full Analysis")

    # 1. Activeness
    st.markdown("#### 1. Activeness in database")
    checks = [
        ("Employees", sd.fetch_count(session, "employee", {"business_unit_id": str(bu_id)})),
        ("Financial summary", sd.fetch_count(session, "summary_finance_monthly", {"company": code})),
        ("Sales summary", sd.fetch_count(session, "summary_sales_monthly", {"company": code})),
        ("Inventory summary", sd.fetch_count(session, "summary_inventory_monthly", {"company": code})),
        ("Budget rows", sd.fetch_count(session, "budget_row", {"business_unit_id": str(bu_id)})),
        ("Production orders", sd.fetch_count(session, "production_order", {"business_unit_id": str(bu_id)})),
    ]
    act_df = pd.DataFrame(checks, columns=["Dataset", "Rows"])
    st.dataframe(act_df, use_container_width=True)

    # 2. Financial
    st.markdown("#### 2. Financial condition")
    fin = sd.fetch_all(session, "summary_finance_monthly", filters={"company": code}, max_rows=100000)
    if not fin.empty:
        fin = _in_month_range(fin, "year", "month", f["start"], f["end"])
        t = fin.groupby(["year", "month"], as_index=False)["total_amount"].sum()
        t["period"] = t["year"].astype(str) + "-" + t["month"].astype(str).str.zfill(2)
        fig = px.line(t, x="period", y="total_amount", title="Financial trend (all IS groups)")
        st.plotly_chart(fig, use_container_width=True)

        ig = fin.groupby("is_group", as_index=False)["total_amount"].sum()
        ig = ig[ig["total_amount"].notna()].sort_values("total_amount")
        fig2 = px.bar(ig, x="total_amount", y="is_group", orientation="h", title="By IS group")
        st.plotly_chart(fig2, use_container_width=True)

        # Revenue / COGS / Opex / Net margin summary
        rev = ig[ig["is_group"] == "Revenue"]["total_amount"].sum()
        cogs = ig[ig["is_group"] == "Cost Of Goods Sold"]["total_amount"].sum()
        opex = ig[ig["is_group"] == "Operating Expenses"]["total_amount"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Revenue", format_currency(rev))
        c2.metric("COGS", format_currency(cogs))
        c3.metric("Operating Expenses", format_currency(opex))
    else:
        st.info("No financial data.")

    # 3. Employee
    st.markdown("#### 3. Employee analysis")
    emp = sd.fetch_all(session, "employee", filters={"business_unit_id": str(bu_id)}, max_rows=50000)
    if not emp.empty:
        active = int(emp["is_active"].sum())
        c1, c2 = st.columns(2)
        c1.metric("Total Employees", len(emp))
        c2.metric("Active", active)
        dept = sd.fetch_all(session, "department")
        dmap = dict(zip(dept["department_id"], dept["department"]))
        emp["department"] = emp["department_id"].map(dmap)
        dc = emp.groupby("department").size().reset_index(name="Employees").sort_values("Employees", ascending=False)
        fig = px.bar(dc, x="Employees", y="department", orientation="h", title="Employees by department")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No employee data.")

    # 4. Inventory
    st.markdown("#### 4. Inventory management")
    inv = sd.fetch_all(session, "summary_inventory_monthly", filters={"company": code}, max_rows=100000)
    if not inv.empty:
        inv = _in_month_range(inv, "year", "month", f["start"], f["end"])
        iv = inv.groupby(["year", "month"], as_index=False)["total_value"].sum()
        iv["period"] = iv["year"].astype(str) + "-" + iv["month"].astype(str).str.zfill(2)
        fig = px.bar(iv, x="period", y="total_value", title="Inventory value by month")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No inventory data.")

    # 5. Sales
    st.markdown("#### 5. Sales analysis")
    sal = sd.fetch_all(session, "summary_sales_monthly", filters={"company": code}, max_rows=100000)
    if not sal.empty:
        sal = _in_month_range(sal, "year", "month", f["start"], f["end"])
        sv = sal.groupby(["year", "month"], as_index=False)["total_order_value"].sum()
        sv["period"] = sv["year"].astype(str) + "-" + sv["month"].astype(str).str.zfill(2)
        fig = px.bar(sv, x="period", y="total_order_value", title="Sales value by month")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No sales data.")

    # 6. Budget
    st.markdown("#### 6. Budget analysis")
    bud = sd.fetch_all(session, "budget_row", filters={"business_unit_id": str(bu_id)},
                       columns="business_unit_id,year_id,month_id,amount", max_rows=200000)
    if not bud.empty:
        bud = _in_month_range(bud, "year_id", "month_id", f["start"], f["end"])
        bv = bud.groupby(["year_id", "month_id"], as_index=False)["amount"].sum()
        bv["period"] = bv["year_id"].astype(str) + "-" + bv["month_id"].astype(str).str.zfill(2)
        fig = px.bar(bv, x="period", y="amount", title="Budget by month")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No budget data.")

    # 7. Production vs Sales
    st.markdown("#### 7. Production vs Sales")
    prod = sd.fetch_all(session, "production_order", filters={"business_unit_id": str(bu_id)}, max_rows=100000)
    if not prod.empty and not sal.empty:
        prod["year"] = pd.to_datetime(prod["start_date"]).dt.year
        prod["month"] = pd.to_datetime(prod["start_date"]).dt.month
        pq = prod.groupby(["year", "month"], as_index=False)["order_qty"].sum()
        pq["period"] = pq["year"].astype(str) + "-" + pq["month"].astype(str).str.zfill(2)
        merged = pq.merge(sv[["period", "total_order_value"]], on="period", how="outer").fillna(0)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=merged["period"], y=merged["order_qty"], name="Production Qty"), secondary_y=False)
        fig.add_trace(go.Scatter(x=merged["period"], y=merged["total_order_value"], name="Sales Value", mode="lines+markers"), secondary_y=True)
        fig.update_layout(title="Production quantity vs Sales value")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Insufficient production/sales data for comparison.")

    # 8. Employee vs Sales (productivity)
    st.markdown("#### 8. Employee vs Sales (performance)")
    if not emp.empty and not sal.empty:
        total_sales = sal["total_order_value"].sum()
        emp_cnt = len(emp)
        per_emp = total_sales / emp_cnt if emp_cnt else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Employees", f"{emp_cnt:,}")
        c2.metric("Total Sales Value", format_currency(total_sales))
        c3.metric("Sales per Employee", format_currency(per_emp))
    else:
        st.info("Insufficient data for employee productivity.")


# ============================================================
# SBU STRATEGIC GAP ANALYSIS (Phase D)
# ============================================================
def page_gap_analysis(session):
    st.markdown("## SBU Strategic Gap Analysis")
    st.caption("5-Year plan evaluation — imported from the Excel analysis file.")

    summary = sd.fetch_all(session, "sbu_gap_summary", max_rows=50000)
    if summary.empty:
        st.warning("Gap analysis data not yet imported. Use the 'Refresh to branch Database' script in the office.")
        return

    # Summary section
    st.markdown("### Summary")
    disp = summary.copy()
    num_cols = ["baseline_fy26_rev", "fy27_strategy_rev", "first_year_jump", "five_yr_cagr",
                "np_margin_ramp", "strategy_vs_budget"]
    for c in num_cols:
        if c in disp.columns:
            disp[c] = pd.to_numeric(disp[c], errors="coerce")
    st.dataframe(disp, use_container_width=True, height=450)

    # Severity chart
    sev = summary["severity"].value_counts().reset_index()
    sev.columns = ["Severity", "Count"]
    fig = px.pie(sev, names="Severity", values="Count", title="Gap severity distribution")
    st.plotly_chart(fig, use_container_width=True)

    _download(summary, "Download Gap Summary (Excel)", f"gap_summary_{datetime.now():%Y%m%d_%H%M}.xlsx")

    st.divider()
    st.markdown("### Per-SBU Gap Report")
    sbus = sorted(summary["sbu"].dropna().unique().tolist())
    sel = st.selectbox("Select an SBU", sbus)

    if sel:
        row = summary[summary["sbu"] == sel]
        if not row.empty:
            r = row.iloc[0]
            st.markdown(f"#### {r.get('business_unit', sel)} ({sel})")
            st.markdown(f"**Severity:** {r.get('severity')} | **Needs Evaluation:** {r.get('needs_eval')}")
            if r.get("key_findings"):
                st.markdown(f"**Key findings:** {r['key_findings']}")
            if r.get("reason"):
                st.markdown(f"**Reason:** {r['reason']}")
            if r.get("solution"):
                st.markdown(f"**Solution:** {r['solution']}")

        detail = sd.fetch_all(session, "sbu_gap_detail", filters={"sbu": sel}, max_rows=5000)
        if not detail.empty:
            st.markdown("#### Detailed metrics")
            for section in detail["section"].dropna().unique():
                sub = detail[detail["section"] == section]
                st.markdown(f"**{section}**")
                st.dataframe(sub.drop(columns=["section", "sbu"], errors="ignore"), use_container_width=True)


# ============================================================
# MANUAL SQL
# ============================================================
def page_manual_sql():
    st.markdown("## Manual SQL Query")
    st.caption("Run a read-only SQL query against the branch database. Only SELECT is allowed.")
    with st.expander("Available tables"):
        st.markdown("\n".join(f"- `{t}` — {desc}" for t, desc in sd.list_tables()))
    sql = st.text_area("SQL query (SELECT only)", height=120,
                       placeholder="SELECT company, year, month, total_amount FROM summary_finance_monthly WHERE company = 'ACCL' LIMIT 100;")
    c1, c2 = st.columns([1, 3])
    with c1:
        run = st.button("Run query", use_container_width=True)
    with c2:
        limit = st.number_input("Max rows", min_value=10, max_value=20000, value=5000, step=500)
    if run and sql.strip():
        with st.spinner("Running..."):
            df, err = sd.manual_query(sql, limit=limit)
        if err:
            st.error(err)
        else:
            st.success(f"Returned {len(df)} rows")
            st.dataframe(df, use_container_width=True)
            _download(df, "Download Results (Excel)", f"query_result_{datetime.now():%Y%m%d_%H%M}.xlsx")


# ============================================================
# ENTRY
# ============================================================
def main():
    if "session" in st.session_state and st.session_state["session"] is not None:
        main_app()
    else:
        login_screen()


if __name__ == "__main__":
    main()
