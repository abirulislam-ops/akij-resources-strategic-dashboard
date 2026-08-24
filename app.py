"""
Akij Resources — SPA Shared Dashboard (Streamlit)

This is the version colleagues access from anywhere. It:
  1. Requires login (Supabase Auth, per-user email/password).
  2. Reads data from the Supabase branch (NOT the office DWH).
  3. Provides a manual SQL box (read-only, SELECT only).
  4. Lets users download data as Excel.

Deploy to Streamlit Cloud with secrets for:
    SUPABASE_URL, SUPABASE_ANON_KEY,
    READER_DB_HOST, READER_DB_PORT, READER_DB_DATABASE,
    READER_DB_USER, READER_DB_PASSWORD
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime

import supabase_data as sd

st.set_page_config(
    page_title="SPA — Strategic Planning Dashboard",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

COMPANY_ORDER = ["AAFL", "ACCL", "AEL", "ARMCL", "iBOS", "ACL", "AIL", "AASL", "NJL", "AMPL"]


def format_currency(val):
    if val is None or (isinstance(val, float) and (val != val)):
        return "—"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
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
        ["Overview", "Financial", "Inventory", "Sales", "Budget", "Employees", "Production", "Manual SQL"],
    )

    st.sidebar.divider()
    st.sidebar.markdown(f"Signed in as **{st.session_state.get('email', '')}**")
    if st.sidebar.button("Sign out"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
    st.sidebar.markdown(f"Last refresh of branch: see `refresh_log` (ETL runs 9/11/17).")

    if page == "Overview":
        page_overview(session)
    elif page == "Financial":
        page_financial(session)
    elif page == "Inventory":
        page_inventory(session)
    elif page == "Sales":
        page_sales(session)
    elif page == "Budget":
        page_budget(session)
    elif page == "Employees":
        page_employees(session)
    elif page == "Production":
        page_production(session)
    elif page == "Manual SQL":
        page_manual_sql()


# ============================================================
# PAGES
# ============================================================
def page_overview(session):
    st.markdown("## Overview")
    st.caption("Company-wise totals from the branch database.")

    bu = sd.fetch_table(session, "business_unit")
    emp = sd.fetch_table(session, "employee")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Business Units", len(bu))
    with c2:
        st.metric("Employees", f"{len(emp):,}")
    with c3:
        active = emp[emp["is_active"] == True]["employee_id"].nunique() if not emp.empty else 0
        st.metric("Active Employees", f"{active:,}")

    st.divider()
    st.markdown("### Employees by Company")
    if not emp.empty and not bu.empty:
        bu_map = dict(zip(bu["business_unit_id"], bu["short_code"]))
        emp["company"] = emp["business_unit_id"].map(bu_map)
        counts = emp.groupby("company").size().reset_index(name="Employees")
        counts = counts.sort_values("Employees", ascending=False)
        fig = px.bar(counts, x="company", y="Employees", title="Employees by Company")
        st.plotly_chart(fig, use_container_width=True)


def page_financial(session):
    st.markdown("## Financial Performance (Monthly)")
    st.caption("Monthly totals by IS Group / GL account, from the branch summary.")

    df = sd.fetch_table(session, "summary_finance_monthly", limit=100000)
    if df.empty:
        st.info("No financial summary data yet. Run the ETL from the office first.")
        return

    cols = [c for c in ["company", "year", "month", "is_group", "gl_code", "gl_name", "total_amount"] if c in df.columns]
    df = df[cols]

    companies = sorted(df["company"].dropna().unique().tolist())
    sel = st.multiselect("Companies", companies, default=companies[:5])
    years = st.multiselect("Year", sorted(df["year"].dropna().unique().tolist()),
                           default=[max(df["year"].dropna().unique())] if df["year"].notna().any() else [])

    d = df[df["company"].isin(sel)]
    if years:
        d = d[d["year"].isin(years)]

    trend = d.groupby(["year", "month"], as_index=False)["total_amount"].sum()
    trend["period"] = trend["year"].astype(str) + "-" + trend["month"].astype(str).str.zfill(2)
    fig = px.line(trend, x="period", y="total_amount", title="Total Amount by Month")
    st.plotly_chart(fig, use_container_width=True)

    by_isgroup = d.groupby("is_group", as_index=False)["total_amount"].sum().sort_values("total_amount")
    fig2 = px.bar(by_isgroup, x="total_amount", y="is_group", orientation="h",
                  title="Total by IS Group")
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### Data")
    st.dataframe(d, use_container_width=True)
    st.download_button(
        "Download Financial (Excel)", data=to_excel_bytes({"financial": d}),
        file_name=f"financial_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def page_inventory(session):
    st.markdown("## Inventory (Monthly Summary)")
    df = sd.fetch_table(session, "summary_inventory_monthly", limit=100000)
    if df.empty:
        st.info("No inventory summary data yet.")
        return
    d = df.groupby(["year", "month"], as_index=False)[["total_qty", "total_value"]].sum()
    d["period"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    fig = px.bar(d, x="period", y="total_value", title="Inventory Value by Month")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
    st.download_button("Download Inventory (Excel)", data=to_excel_bytes({"inventory": df}),
                       file_name=f"inventory_{datetime.now():%Y%m%d_%H%M}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def page_sales(session):
    st.markdown("## Sales (Monthly Summary)")
    df = sd.fetch_table(session, "summary_sales_monthly", limit=100000)
    if df.empty:
        st.info("No sales summary data yet.")
        return
    d = df.groupby(["year", "month"], as_index=False).agg(
        {"order_count": "sum", "total_order_value": "sum"}
    )
    d["period"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    fig = px.bar(d, x="period", y="total_order_value", title="Sales Value by Month")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
    st.download_button("Download Sales (Excel)", data=to_excel_bytes({"sales": df}),
                       file_name=f"sales_{datetime.now():%Y%m%d_%H%M}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def page_budget(session):
    st.markdown("## Budget")
    df = sd.fetch_table(session, "budget_row", limit=100000)
    if df.empty:
        st.info("No budget data yet.")
        return
    d = df.groupby(["year_id", "month_id"], as_index=False)["amount"].sum()
    d["period"] = d["year_id"].astype(str) + "-" + d["month_id"].astype(str).str.zfill(2)
    fig = px.bar(d, x="period", y="amount", title="Budget by Month")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
    st.download_button("Download Budget (Excel)", data=to_excel_bytes({"budget": df}),
                       file_name=f"budget_{datetime.now():%Y%m%d_%H%M}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def page_employees(session):
    st.markdown("## Employees")
    emp = sd.fetch_table(session, "employee", limit=50000)
    if emp.empty:
        st.info("No employee data yet.")
        return
    dept = sd.fetch_table(session, "department")
    desig = sd.fetch_table(session, "designation")
    bu = sd.fetch_table(session, "business_unit")

    if not dept.empty:
        dmap = dict(zip(dept["department_id"], dept["department"]))
        emp["department"] = emp["department_id"].map(dmap)
    if not desig.empty:
        gmap = dict(zip(desig["designation_id"], desig["designation"]))
        emp["designation"] = emp["designation_id"].map(gmap)
    if not bu.empty:
        bmap = dict(zip(bu["business_unit_id"], bu["short_code"]))
        emp["company"] = emp["business_unit_id"].map(bmap)

    q = st.text_input("Search by name or code")
    show = emp
    if q:
        show = emp[
            emp["employee_name"].astype(str).str.contains(q, case=False, na=False)
            | emp["employee_code"].astype(str).str.contains(q, case=False, na=False)
        ]
    st.dataframe(show, use_container_width=True, height=500)
    st.download_button("Download Employees (Excel)", data=to_excel_bytes({"employees": show}),
                       file_name=f"employees_{datetime.now():%Y%m%d_%H%M}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def page_production(session):
    st.markdown("## Production Orders")
    df = sd.fetch_table(session, "production_order", limit=100000)
    if df.empty:
        st.info("No production data yet.")
        return
    st.dataframe(df, use_container_width=True)
    st.download_button("Download Production (Excel)", data=to_excel_bytes({"production": df}),
                       file_name=f"production_{datetime.now():%Y%m%d_%H%M}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def page_manual_sql():
    st.markdown("## Manual SQL Query")
    st.caption("Run a read-only SQL query against the branch database. Only SELECT is allowed.")

    with st.expander("Available tables"):
        st.markdown("\n".join(f"- `{t}` — {desc}" for t, desc in sd.list_tables()))

    sql = st.text_area(
        "SQL query (SELECT only)",
        placeholder="SELECT company, year, month, total_amount FROM summary_finance_monthly WHERE company = 'ACCL' LIMIT 100;",
        height=120,
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        run = st.button("Run query", use_container_width=True)
    with col2:
        limit = st.number_input("Max rows", min_value=10, max_value=20000, value=5000, step=500)

    if run and sql.strip():
        with st.spinner("Running..."):
            df, err = sd.manual_query(sql, limit=limit)
        if err:
            st.error(err)
        else:
            st.success(f"Returned {len(df)} rows")
            st.dataframe(df, use_container_width=True)
            st.download_button("Download Results (Excel)", data=to_excel_bytes({"result": df}),
                               file_name=f"query_result_{datetime.now():%Y%m%d_%H%M}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


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
