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

# Units used throughout (per dataset).
UNIT_AMOUNT = "BDT"       # financial / budget / sales value amounts
UNIT_QTY = "qty"          # inventory quantity / production quantity
UNIT_VALUE = "BDT"        # inventory value


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


def _bu_list(token):
    if "bu_df" not in st.session_state:
        st.session_state["bu_df"] = sd.fetch_all(token, "business_unit")
    return st.session_state["bu_df"]


def _bu_label(bu_df):
    def lbl(row):
        code = row["short_code"] or str(row["business_unit_id"])
        tag = "active" if row["is_active"] else "inactive"
        return f"{code} ({tag})"
    bu_df = bu_df.copy()
    bu_df["label"] = bu_df.apply(lbl, axis=1)
    return bu_df


def _bu_full(bu_df, code):
    """Full business unit name for a short code."""
    row = bu_df[bu_df["short_code"] == code]
    if row.empty:
        return code
    return row.iloc[0]["business_unit"] or code


def _bu_id(bu_df, code):
    row = bu_df[bu_df["short_code"] == code]
    return int(row.iloc[0]["business_unit_id"]) if not row.empty else None


def sidebar_filters(token):
    bu_df = _bu_label(_bu_list(token))
    codes = sorted(bu_df["short_code"].dropna().unique().tolist())

    st.sidebar.markdown("### Filters")

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

    # SBU multi-select (with select-all)
    st.sidebar.markdown("**SBU filter**")
    col_all, col_clear = st.sidebar.columns(2)
    with col_all:
        if st.button("Select all", key="f_sel_all", use_container_width=True):
            st.session_state["f_sbu_sel"] = codes
    with col_clear:
        if st.button("Clear", key="f_sel_clear", use_container_width=True):
            st.session_state["f_sbu_sel"] = []

    if "f_sbu_sel" not in st.session_state:
        st.session_state["f_sbu_sel"] = codes
    selected = st.sidebar.multiselect(
        "SBUs", codes, default=st.session_state["f_sbu_sel"], key="f_sbu_sel",
    )

    return {
        "bu_df": bu_df,
        "codes": selected,
        "all_codes": codes,
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


def _sbu_filter_widget(f, key_prefix):
    """In-page SBU multi-select (with select-all) for comparison tabs."""
    codes = f["all_codes"]
    c1, c2 = st.columns([4, 1])
    with c1:
        sel = st.multiselect("Select SBUs to compare", codes, default=codes, key=f"{key_prefix}_sbu")
    with c2:
        st.caption("")  # spacing
        if st.button("All", key=f"{key_prefix}_all"):
            sel = codes
    return sel


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
                token, err = sd.sign_in(email.strip(), password)
                if err:
                    st.error(err)
                else:
                    st.session_state["token"] = token
                    st.session_state["email"] = email.strip()
                    st.rerun()


# ============================================================
# MAIN APP
# ============================================================
def main_app():
    token = st.session_state["token"]

    st.sidebar.title("SPA Dashboard")
    page = st.sidebar.radio(
        "Navigate",
        ["Overview", "SBU Analysis", "Financial", "Inventory", "Sales", "Budget",
         "Employees", "Production", "Sales Performance", "SBU Strategic Gap Analysis",
         "ROMI Analysis", "Manual SQL"],
    )

    st.sidebar.divider()
    st.sidebar.markdown(f"Signed in as **{st.session_state.get('email', '')}**")
    if st.sidebar.button("Sign out"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    filters = sidebar_filters(token)

    if page == "Overview":
        page_overview(token, filters)
    elif page == "SBU Analysis":
        page_sbu_analysis(token, filters)
    elif page == "Financial":
        page_financial(token, filters)
    elif page == "Inventory":
        page_inventory(token, filters)
    elif page == "Sales":
        page_sales(token, filters)
    elif page == "Budget":
        page_budget(token, filters)
    elif page == "Employees":
        page_employees(token, filters)
    elif page == "Production":
        page_production(token, filters)
    elif page == "Sales Performance":
        page_sales_performance(token, filters)
    elif page == "SBU Strategic Gap Analysis":
        page_gap_analysis(token)
    elif page == "ROMI Analysis":
        import spa_romi_tab
        spa_romi_tab.page_romi()
    elif page == "Manual SQL":
        page_manual_sql()


# ============================================================
# PAGES
# ============================================================
def page_overview(token, f):
    st.markdown("## Overview")
    st.caption("Company-wise totals from the branch database.")

    bu = f["bu_df"]
    emp_count = sd.fetch_count(token, "employee")
    active_count = sd.fetch_count(token, "employee", filters={"is_active": "true"})

    c1, c2, c3 = st.columns(3)
    c1.metric("Business Units", len(bu))
    c2.metric("Employees", f"{emp_count:,}")
    c3.metric("Active Employees", f"{active_count:,}")

    st.divider()

    # Active / Inactive SBU lists in separate tabs
    tab_active, tab_inactive = st.tabs(["Active SBUs", "Inactive SBUs"])
    active_bu = bu[bu["is_active"] == True][["short_code", "business_unit"]].rename(
        columns={"short_code": "Code", "business_unit": "Business Unit"})
    inactive_bu = bu[bu["is_active"] == False][["short_code", "business_unit"]].rename(
        columns={"short_code": "Code", "business_unit": "Business Unit"})
    with tab_active:
        st.markdown(f"**{len(active_bu)} active SBUs**")
        st.dataframe(active_bu, use_container_width=True, height=400)
    with tab_inactive:
        st.markdown(f"**{len(inactive_bu)} inactive SBUs**")
        st.dataframe(inactive_bu, use_container_width=True, height=400)

    st.divider()

    # Cross-SBU comparisons
    st.markdown("### Cross-SBU Comparisons")

    st.markdown("#### Employees by Company (active vs inactive)")
    emp = sd.fetch_all(token, "employee", columns="business_unit_id,is_active")
    if not emp.empty:
        bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
        emp["company"] = emp["business_unit_id"].map(bmap)
        emp["status"] = emp["is_active"].map({True: "Active", False: "Inactive"})
        counts = emp.groupby(["company", "status"]).size().reset_index(name="Employees")
        counts = counts.sort_values("Employees", ascending=False)
        fig = px.bar(counts, x="company", y="Employees", color="status",
                     title="Employees by Company (persons)", barmode="stack")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Revenue by Company (BDT, total across selected period)")
    fin = sd.fetch_all(token, "summary_finance_monthly", columns="company,is_group,total_amount", max_rows=200000)
    if not fin.empty:
        rev = fin[fin["is_group"] == "Revenue"].groupby("company", as_index=False)["total_amount"].sum()
        rev = rev.sort_values("total_amount", ascending=False)
        fig = px.bar(rev, x="company", y="total_amount", title="Revenue by Company (BDT)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Sales Value by Company (BDT)")
    sal = sd.fetch_all(token, "summary_sales_monthly", columns="company,total_order_value", max_rows=200000)
    if not sal.empty:
        sv = sal.groupby("company", as_index=False)["total_order_value"].sum().sort_values("total_order_value", ascending=False)
        fig = px.bar(sv, x="company", y="total_order_value", title="Sales Value by Company (BDT)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Budget by Company (BDT)")
    bud = sd.fetch_all(token, "budget_row", columns="business_unit_id,amount", max_rows=300000)
    if not bud.empty:
        bud["company"] = bud["business_unit_id"].map(bmap)
        bv = bud.groupby("company", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
        fig = px.bar(bv, x="company", y="amount", title="Budget by Company (BDT)")
        st.plotly_chart(fig, use_container_width=True)


def page_financial(token, f):
    st.markdown("## Financial Performance (Monthly)")
    df = sd.fetch_all(token, "summary_finance_monthly", max_rows=200000)
    if df.empty:
        st.info("No financial summary data yet.")
        return
    sel = _sbu_filter_widget(f, "fin")
    if sel:
        df = df[df["company"].isin(sel)]
    df = _in_month_range(df, "year", "month", f["start"], f["end"])

    # Multi-SBU comparison trend
    st.markdown("### Monthly total by SBU (BDT)")
    t = df.groupby(["company", "year", "month"], as_index=False)["total_amount"].sum()
    t["period"] = t["year"].astype(str) + "-" + t["month"].astype(str).str.zfill(2)
    fig = px.line(t, x="period", y="total_amount", color="company",
                  title="Monthly total by SBU (BDT)")
    st.plotly_chart(fig, use_container_width=True)

    # IS group breakdown
    by_isgroup = df.groupby("is_group", as_index=False)["total_amount"].sum().sort_values("total_amount")
    fig2 = px.bar(by_isgroup, x="total_amount", y="is_group", orientation="h",
                  title="Total by IS Group (BDT)")
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df, use_container_width=True)
    _download(df, "Download Financial (Excel)", f"financial_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_inventory(token, f):
    st.markdown("## Inventory (Monthly Summary)")
    df = sd.fetch_all(token, "summary_inventory_monthly", max_rows=200000)
    if df.empty:
        st.info("No inventory data yet.")
        return
    sel = _sbu_filter_widget(f, "inv")
    if sel:
        df = df[df["company"].isin(sel)]
    df = _in_month_range(df, "year", "month", f["start"], f["end"])

    st.markdown("### Monthly inventory value by SBU (BDT)")
    d = df.groupby(["company", "year", "month"], as_index=False)["total_value"].sum()
    d["period"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    fig = px.line(d, x="period", y="total_value", color="company",
                  title="Inventory value by SBU (BDT)")
    st.plotly_chart(fig, use_container_width=True)

    by_type = df.groupby("stock_type", as_index=False)["total_value"].sum().sort_values("total_value", ascending=False)
    fig2 = px.pie(by_type, names="stock_type", values="total_value", title="Value by Stock Type (BDT)")
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df, use_container_width=True)
    _download(df, "Download Inventory (Excel)", f"inventory_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_sales(token, f):
    st.markdown("## Sales (Monthly Summary)")
    df = sd.fetch_all(token, "summary_sales_monthly", max_rows=200000)
    if df.empty:
        st.info("No sales data yet.")
        return
    sel = _sbu_filter_widget(f, "sal")
    if sel:
        df = df[df["company"].isin(sel)]
    df = _in_month_range(df, "year", "month", f["start"], f["end"])

    st.markdown("### Monthly sales value by SBU (BDT)")
    d = df.groupby(["company", "year", "month"], as_index=False)["total_order_value"].sum()
    d["period"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    fig = px.line(d, x="period", y="total_order_value", color="company",
                  title="Sales value by SBU (BDT)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Order count by SBU (number of orders)")
    d2 = df.groupby(["company", "year", "month"], as_index=False)["order_count"].sum()
    d2["period"] = d2["year"].astype(str) + "-" + d2["month"].astype(str).str.zfill(2)
    fig2 = px.line(d2, x="period", y="order_count", color="company",
                   title="Order count by SBU (orders)")
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df, use_container_width=True)
    _download(df, "Download Sales (Excel)", f"sales_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_budget(token, f):
    st.markdown("## Budget")
    df = sd.fetch_all(token, "budget_row", max_rows=300000)
    if df.empty:
        st.info("No budget data yet.")
        return
    bu = f["bu_df"]
    bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
    bfull = dict(zip(bu["business_unit_id"], bu["business_unit"]))
    df["company"] = df["business_unit_id"].map(bmap)
    df["business_unit"] = df["business_unit_id"].map(bfull)

    sel = _sbu_filter_widget(f, "bud")
    if sel:
        df = df[df["company"].isin(sel)]
    df = _in_month_range(df, "year_id", "month_id", f["start"], f["end"])

    st.markdown("### Budget by SBU over months (BDT)")
    d = df.groupby(["company", "year_id", "month_id"], as_index=False)["amount"].sum()
    d["period"] = d["year_id"].astype(str) + "-" + d["month_id"].astype(str).str.zfill(2)
    fig = px.line(d, x="period", y="amount", color="company", title="Budget by SBU (BDT)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Budget by GL account (BDT)")
    by_gl = df.groupby("gl_name", as_index=False)["amount"].sum().sort_values("amount", ascending=False).head(20)
    fig2 = px.bar(by_gl, x="amount", y="gl_name", orientation="h", title="Top 20 GL accounts (BDT)")
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### Budget by IS group (BDT)")
    by_grp = df.groupby("is_group", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
    fig3 = px.bar(by_grp, x="is_group", y="amount", title="Budget by IS Group (BDT)")
    st.plotly_chart(fig3, use_container_width=True)

    # Detailed table with names instead of raw IDs
    cols = ["company", "business_unit", "gl_name", "is_group", "year_id", "month_id", "amount"]
    cols = [c for c in cols if c in df.columns]
    st.dataframe(df[cols], use_container_width=True)
    _download(df[cols], "Download Budget (Excel)", f"budget_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_employees(token, f):
    st.markdown("## Employees")
    emp = sd.fetch_all(token, "employee", max_rows=50000)
    if emp.empty:
        st.info("No employee data yet.")
        return
    det = sd.fetch_all(token, "employee_details", max_rows=50000)
    dept = sd.fetch_all(token, "department")
    desig = sd.fetch_all(token, "designation")
    sec = sd.fetch_all(token, "section")
    bu = f["bu_df"]

    if not det.empty:
        det = det.drop_duplicates(subset="employee_id", keep="first")
        emp = emp.merge(det, on="employee_id", how="left", suffixes=("", "_d"))

    bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
    bfull = dict(zip(bu["business_unit_id"], bu["business_unit"]))
    dmap = dict(zip(dept["department_id"], dept["department"]))
    gmap = dict(zip(desig["designation_id"], desig["designation"]))
    smap = dict(zip(sec["section_id"], sec["section_name"]))
    emp["company"] = emp["business_unit_id"].map(bmap)
    emp["business_unit"] = emp["business_unit_id"].map(bfull)
    emp["department"] = emp["department_id"].map(dmap)
    emp["designation"] = emp["designation_id"].map(gmap)
    emp["section"] = emp["section_id"].map(smap)

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

    cols = ["employee_code", "employee_name", "company", "business_unit", "department",
            "designation", "section", "joining_date", "office_mail", "office_mobile",
            "personal_mobile", "payroll_group", "employee_status", "is_active"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True, height=500)
    _download(show[cols], "Download Employees (Excel)", f"employees_{datetime.now():%Y%m%d_%H%M}.xlsx")


def page_production(token, f):
    st.markdown("## Production Orders")
    df = sd.fetch_all(token, "production_order", max_rows=150000)
    if df.empty:
        st.info("No production data yet.")
        return
    bu = f["bu_df"]
    bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
    df["company"] = df["business_unit_id"].map(bmap)
    sel = _sbu_filter_widget(f, "prod")
    if sel:
        df = df[df["company"].isin(sel)]

    d = df.groupby("company", as_index=False)["order_qty"].sum().sort_values("order_qty", ascending=False)
    fig = px.bar(d, x="company", y="order_qty", title="Total Order Quantity by Company (qty)")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
    _download(df, "Download Production (Excel)", f"production_{datetime.now():%Y%m%d_%H%M}.xlsx")


# ============================================================
# SBU FULL ANALYSIS (Phase C)
# ============================================================
def page_sbu_analysis(token, f):
    st.markdown("## SBU Full Analysis")
    bu = _bu_label(f["bu_df"])
    options = sorted(bu["label"].dropna().unique().tolist())
    sel = st.selectbox("Select an SBU", options)
    code = sel.split(" (")[0]
    full = _bu_full(bu, code)
    bu_id = _bu_id(bu, code)

    st.markdown(f"### {full} ({code}) — Full Analysis")

    # 1. Activeness (with units)
    st.markdown("#### 1. Activeness in database")
    checks = [
        ("Employees", sd.fetch_count(token, "employee", {"business_unit_id": str(bu_id)}), "person"),
        ("Financial summary", sd.fetch_count(token, "summary_finance_monthly", {"company": code}), "rows"),
        ("Sales summary", sd.fetch_count(token, "summary_sales_monthly", {"company": code}), "rows"),
        ("Inventory summary", sd.fetch_count(token, "summary_inventory_monthly", {"company": code}), "rows"),
        ("Budget rows", sd.fetch_count(token, "budget_row", {"business_unit_id": str(bu_id)}), "rows"),
        ("Production orders", sd.fetch_count(token, "production_order", {"business_unit_id": str(bu_id)}), "orders"),
    ]
    act_df = pd.DataFrame(checks, columns=["Dataset", "Count", "Unit"])
    st.dataframe(act_df, use_container_width=True)

    # 2. Financial
    st.markdown("#### 2. Financial condition (BDT)")
    fin = sd.fetch_all(token, "summary_finance_monthly", filters={"company": code}, max_rows=100000)
    if not fin.empty:
        fin = _in_month_range(fin, "year", "month", f["start"], f["end"])
        t = fin.groupby(["year", "month"], as_index=False)["total_amount"].sum()
        t["period"] = t["year"].astype(str) + "-" + t["month"].astype(str).str.zfill(2)
        fig = px.line(t, x="period", y="total_amount", title="Financial trend (BDT)")
        st.plotly_chart(fig, use_container_width=True)

        ig = fin.groupby("is_group", as_index=False)["total_amount"].sum()
        ig = ig[ig["total_amount"].notna()].sort_values("total_amount")
        fig2 = px.bar(ig, x="total_amount", y="is_group", orientation="h", title="By IS group (BDT)")
        st.plotly_chart(fig2, use_container_width=True)

        rev = ig[ig["is_group"] == "Revenue"]["total_amount"].sum()
        cogs = ig[ig["is_group"] == "Cost Of Goods Sold"]["total_amount"].sum()
        opex = ig[ig["is_group"] == "Operating Expenses"]["total_amount"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Revenue (BDT)", format_currency(rev))
        c2.metric("COGS (BDT)", format_currency(cogs))
        c3.metric("Operating Expenses (BDT)", format_currency(opex))
    else:
        st.info("No financial data.")

    # 3. Employee
    st.markdown("#### 3. Employee analysis")
    emp = sd.fetch_all(token, "employee", filters={"business_unit_id": str(bu_id)}, max_rows=50000)
    if not emp.empty:
        active = int(emp["is_active"].sum())
        c1, c2 = st.columns(2)
        c1.metric("Total Employees", f"{len(emp):,} persons")
        c2.metric("Active", f"{active:,} persons")
        dept = sd.fetch_all(token, "department")
        dmap = dict(zip(dept["department_id"], dept["department"]))
        emp["department"] = emp["department_id"].map(dmap)
        dc = emp.groupby("department").size().reset_index(name="Employees").sort_values("Employees", ascending=False)
        fig = px.bar(dc, x="Employees", y="department", orientation="h", title="Employees by department (persons)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No employee data.")

    # 4. Inventory
    st.markdown("#### 4. Inventory management (BDT)")
    inv = sd.fetch_all(token, "summary_inventory_monthly", filters={"company": code}, max_rows=100000)
    if not inv.empty:
        inv = _in_month_range(inv, "year", "month", f["start"], f["end"])
        iv = inv.groupby(["year", "month"], as_index=False)["total_value"].sum()
        iv["period"] = iv["year"].astype(str) + "-" + iv["month"].astype(str).str.zfill(2)
        fig = px.bar(iv, x="period", y="total_value", title="Inventory value by month (BDT)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No inventory data.")

    # 5. Sales
    st.markdown("#### 5. Sales analysis (BDT)")
    sal = sd.fetch_all(token, "summary_sales_monthly", filters={"company": code}, max_rows=100000)
    if not sal.empty:
        sal = _in_month_range(sal, "year", "month", f["start"], f["end"])
        sv = sal.groupby(["year", "month"], as_index=False)["total_order_value"].sum()
        sv["period"] = sv["year"].astype(str) + "-" + sv["month"].astype(str).str.zfill(2)
        fig = px.bar(sv, x="period", y="total_order_value", title="Sales value by month (BDT)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No sales data.")

    # 6. Budget
    st.markdown("#### 6. Budget analysis (BDT)")
    bud = sd.fetch_all(token, "budget_row", filters={"business_unit_id": str(bu_id)}, max_rows=200000)
    if not bud.empty:
        bud = _in_month_range(bud, "year_id", "month_id", f["start"], f["end"])
        bv = bud.groupby(["year_id", "month_id"], as_index=False)["amount"].sum()
        bv["period"] = bv["year_id"].astype(str) + "-" + bv["month_id"].astype(str).str.zfill(2)
        fig = px.bar(bv, x="period", y="amount", title="Budget by month (BDT)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No budget data.")

    # 7. Production vs Sales
    st.markdown("#### 7. Production vs Sales")
    prod = sd.fetch_all(token, "production_order", filters={"business_unit_id": str(bu_id)}, max_rows=100000)
    if not prod.empty and not sal.empty:
        prod["year"] = pd.to_datetime(prod["start_date"]).dt.year
        prod["month"] = pd.to_datetime(prod["start_date"]).dt.month
        pq = prod.groupby(["year", "month"], as_index=False)["order_qty"].sum()
        pq["period"] = pq["year"].astype(str) + "-" + pq["month"].astype(str).str.zfill(2)
        merged = pq.merge(sv[["period", "total_order_value"]], on="period", how="outer").fillna(0)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=merged["period"], y=merged["order_qty"], name="Production Qty (qty)"), secondary_y=False)
        fig.add_trace(go.Scatter(x=merged["period"], y=merged["total_order_value"], name="Sales Value (BDT)", mode="lines+markers"), secondary_y=True)
        fig.update_layout(title="Production quantity (qty) vs Sales value (BDT)")
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
        c1.metric("Employees", f"{emp_cnt:,} persons")
        c2.metric("Total Sales Value (BDT)", format_currency(total_sales))
        c3.metric("Sales per Employee (BDT)", format_currency(per_emp))
    else:
        st.info("Insufficient data for employee productivity.")


# ============================================================
# SALES PERFORMANCE (Phase E)
# ============================================================
def page_sales_performance(token, f):
    st.markdown("## Sales Performance")
    st.caption("Sales force (who is a salesperson) and their monthly targets. "
               "Note: achieved-sales-per-employee is only partially populated in the source ERP, "
               "so performance here is target-based.")

    bu = f["bu_df"]
    bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
    bfull = dict(zip(bu["business_unit_id"], bu["business_unit"]))

    sf = sd.fetch_all(token, "sales_force", max_rows=50000)
    stgt = sd.fetch_all(token, "sales_target", max_rows=200000)

    if sf.empty and stgt.empty:
        st.info("No sales performance data yet.")
        return

    # SBU filter for this tab
    if not sf.empty:
        sf["company"] = sf["business_unit_id"].map(bmap)
    if not stgt.empty:
        stgt["company"] = stgt["business_unit_id"].map(bmap)

    all_companies = sorted(set(
        list(sf["company"].dropna().unique()) if not sf.empty else []
        + list(stgt["company"].dropna().unique()) if not stgt.empty else []
    ))
    sel = st.multiselect("Select SBUs", all_companies, default=all_companies)

    if sel:
        sf = sf[sf["company"].isin(sel)]
        stgt = stgt[stgt["company"].isin(sel)]

    # ---- 1. Sales force summary ----
    st.markdown("### Sales Force")
    c1, c2, c3 = st.columns(3)
    c1.metric("Sales people", f"{sf['employee_id'].nunique():,}" if not sf.empty else 0)
    c2.metric("Sales managers", f"{int(sf['is_manager'].sum()):,}" if not sf.empty and 'is_manager' in sf.columns else 0)
    c3.metric("Territories", f"{sf['territory_name'].nunique():,}" if not sf.empty else 0)

    if not sf.empty:
        sf_show = sf[["employee_code", "employee_name", "company", "territory_name",
                      "channel_name", "is_manager", "contact_number", "email"]]
        st.dataframe(sf_show, use_container_width=True, height=350)
        _download(sf_show, "Download Sales Force (Excel)", f"sales_force_{datetime.now():%Y%m%d_%H%M}.xlsx")

    # ---- 2. Targets ----
    st.markdown("### Sales Targets (BDT)")

    # Month/year filter for targets
    if not stgt.empty:
        years = sorted(stgt["year_id"].dropna().unique().tolist())
        stgt = _in_month_range(stgt, "year_id", "month_id", f["start"], f["end"])

        # Target by SBU over months
        t_sbu = stgt.groupby(["company", "year_id", "month_id"], as_index=False)["target_amount"].sum()
        t_sbu["period"] = t_sbu["year_id"].astype(str) + "-" + t_sbu["month_id"].astype(str).str.zfill(2)
        fig = px.line(t_sbu, x="period", y="target_amount", color="company",
                      title="Sales target by SBU (BDT)")
        st.plotly_chart(fig, use_container_width=True)

        # Top sales people by target
        st.markdown("#### Top sales people by target (BDT)")
        t_emp = stgt.groupby(["employee_code", "employee_name", "company"], as_index=False)["target_amount"].sum()
        t_emp = t_emp.sort_values("target_amount", ascending=False).head(20)
        fig2 = px.bar(t_emp, x="target_amount", y="employee_name", orientation="h",
                      title="Top 20 sales people by target (BDT)")
        st.plotly_chart(fig2, use_container_width=True)

        # Target by channel
        st.markdown("#### Target by channel (BDT)")
        t_ch = stgt.groupby("channel_name", as_index=False)["target_amount"].sum().sort_values("target_amount", ascending=False)
        fig3 = px.bar(t_ch, x="channel_name", y="target_amount", title="Target by channel (BDT)")
        st.plotly_chart(fig3, use_container_width=True)

        st.dataframe(stgt, use_container_width=True)
        _download(stgt, "Download Sales Targets (Excel)", f"sales_targets_{datetime.now():%Y%m%d_%H%M}.xlsx")
    else:
        st.info("No sales target data.")


# ============================================================
# SBU STRATEGIC GAP ANALYSIS (Phase D)
# ============================================================
def page_gap_analysis(token):
    st.markdown("## SBU Strategic Gap Analysis")
    st.caption("5-Year plan evaluation — imported from the Excel analysis file.")

    # Notes & Methodology popover button
    with st.popover("📘 Notes & Methodology"):
        notes = sd.fetch_all(token, "gap_notes", max_rows=5000)
        if not notes.empty:
            for _, r in notes.iterrows():
                topic = r.get("topic") or ""
                content = r.get("content") or ""
                if topic:
                    st.markdown(f"**{topic}**")
                if content:
                    st.markdown(content)
        else:
            st.info("Notes not imported yet.")

    summary = sd.fetch_all(token, "sbu_gap_summary", max_rows=50000)
    if summary.empty:
        st.warning("Gap analysis data not yet imported.")
        return

    st.markdown("### Summary")
    disp = summary.copy()
    num_cols = ["baseline_fy26_rev", "fy27_strategy_rev", "first_year_jump", "five_yr_cagr",
                "np_margin_ramp", "strategy_vs_budget"]
    for c in num_cols:
        if c in disp.columns:
            disp[c] = pd.to_numeric(disp[c], errors="coerce")
    st.dataframe(disp, use_container_width=True, height=450)

    sev = summary["severity"].value_counts().reset_index()
    sev.columns = ["Severity", "Count"]
    fig = px.pie(sev, names="Severity", values="Count", title="Gap severity distribution (SBUs)")
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

        detail = sd.fetch_all(token, "sbu_gap_detail", filters={"sbu": sel}, max_rows=5000)
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
    if "token" in st.session_state and st.session_state["token"] is not None:
        main_app()
    else:
        login_screen()


if __name__ == "__main__":
    main()
