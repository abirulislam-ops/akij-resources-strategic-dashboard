import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
from datetime import datetime

from db_config import (
    load_data, get_company_id_list, get_company_name, get_company_full_name, COMPANIES
)
from queries import (
    get_employee_count_query, get_employee_detail_query, get_employee_dept_summary_query,
    get_marketing_budget_query, get_financial_performance_query, get_budget_vs_actual_query,
    get_sales_performance_query, get_production_query, get_inventory_query,
    get_gl_summary_query, get_available_years_query
)

st.set_page_config(
    page_title="Akij Resources - Strategic Planning Dashboard",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: bold; color: #1f77b4; }
    .metric-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 1.5rem; border-radius: 1rem; color: white; text-align: center; }
    .metric-value { font-size: 2rem; font-weight: bold; }
    .metric-label { font-size: 0.9rem; opacity: 0.9; }
    .section-header { font-size: 1.5rem; font-weight: bold; color: #2c3e50; margin-top: 1rem; }
    div[data-testid="stMetric"] { background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem; }
</style>
""", unsafe_allow_html=True)


def format_currency(val):
    if pd.isna(val) or val == 0:
        return "0"
    if abs(val) >= 10000000:
        return f"{val/10000000:.2f} Cr"
    elif abs(val) >= 100000:
        return f"{val/100000:.2f} L"
    else:
        return f"{val:,.0f}"


def format_number(val):
    if pd.isna(val):
        return "0"
    return f"{int(val):,}"


def export_to_excel(dataframes_dict, filename="dashboard_export.xlsx"):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for sheet_name, df in dataframes_dict.items():
            safe_name = sheet_name[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
    return buffer.getvalue()


def render_metric_card(label, value, delta=None):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.metric(label=label, value=value, delta=delta)


def page_summary():
    st.markdown("# Strategic Planning Dashboard")
    st.markdown("### Company Overview")
    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_year = st.selectbox("From Year", options=range(2026, 2019, -1), index=3, key="sum_min_year")
    with col2:
        min_month = st.selectbox("From Month", options=range(1, 13), index=0, key="sum_min_month", format_func=lambda x: datetime(2026, x, 1).strftime("%B"))
    with col3:
        max_year = st.selectbox("To Year", options=range(2026, 2019, -1), index=0, key="sum_max_year")
    with col4:
        max_month = st.selectbox("To Month", options=range(1, 13), index=7, key="sum_max_month", format_func=lambda x: datetime(2026, x, 1).strftime("%B"))

    company_filter = st.multiselect(
        "Filter Companies",
        options=list(COMPANIES.keys()),
        default=list(COMPANIES.keys()),
        format_func=lambda x: f"{COMPANIES[x]['name']} - {COMPANIES[x]['full']}",
        key="sum_company_filter"
    )

    if not company_filter:
        st.warning("Please select at least one company")
        return

    st.divider()
    st.markdown("### Employee Summary")
    emp_df = load_data(get_employee_count_query(company_filter))
    if not emp_df.empty:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Employees", format_number(emp_df["TotalEmployees"].sum()))
        with c2:
            st.metric("Active Employees", format_number(emp_df["ActiveEmployees"].sum()))
        with c3:
            st.metric("Inactive Employees", format_number(emp_df["InactiveEmployees"].sum()))

        fig = px.bar(emp_df, x="Company", y=["ActiveEmployees", "InactiveEmployees"],
                      barmode="group", title="Employee Count by Company",
                      color_discrete_map={"ActiveEmployees": "#2ecc71", "InactiveEmployees": "#e74c3c"})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

        export_data = {"Employee Summary": emp_df}
    else:
        st.info("No employee data available")
        export_data = {}

    st.divider()
    st.markdown("### Department Distribution")
    dept_df = load_data(get_employee_dept_summary_query(company_filter))
    if not dept_df.empty:
        dept_pivot = dept_df.pivot_table(index="Department", columns="Company", values="EmployeeCount", fill_value=0)
        fig = px.imshow(dept_pivot.values, x=dept_pivot.columns.tolist(), y=dept_pivot.index.tolist(),
                         color_continuous_scale="Blues", title="Employee Distribution: Department x Company")
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)
        export_data["Department Summary"] = dept_df

    st.divider()
    st.markdown("### Financial Overview by Company")
    fin_df = load_data(get_financial_performance_query(company_filter, min_year))
    if not fin_df.empty:
        monthly_fin = fin_df.groupby(["Company", "TranMonth"])["TotalAmount"].sum().reset_index()
        fig = px.line(monthly_fin, x="TranMonth", y="TotalAmount", color="Company",
                       title=f"Monthly Financial Trend ({min_year})",
                       labels={"TranMonth": "Month", "TotalAmount": "Total Amount (BDT)"})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

        top_gl = fin_df.groupby("Company").apply(
            lambda x: x.groupby("GLAccount")["TotalAmount"].sum().nlargest(5)
        ).reset_index()
        if not top_gl.empty:
            st.markdown("#### Top 5 GL Accounts per Company")
            for company in top_gl["Company"].unique():
                company_data = top_gl[top_gl["Company"] == company]
                with st.expander(f"{company} - Top GL Accounts"):
                    st.dataframe(company_data[["GLAccount", "TotalAmount"]].reset_index(drop=True))

        export_data["Financial Performance"] = fin_df

    st.divider()
    st.markdown("### Marketing Budget by Company")
    mkt_df = load_data(get_marketing_budget_query(company_filter))
    if not mkt_df.empty:
        mkt_summary = mkt_df.groupby(["Company", "Year"])["BudgetAmount"].sum().reset_index()
        fig = px.bar(mkt_summary, x="Company", y="BudgetAmount", color="Year",
                      title="Marketing Budget by Company & Year",
                      barmode="group")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
        export_data["Marketing Budget"] = mkt_df
    else:
        st.info("No marketing budget data found")

    st.divider()
    st.markdown("### Sales Performance")
    sales_df = load_data(get_sales_performance_query(company_filter, min_year))
    if not sales_df.empty:
        monthly_sales = sales_df.groupby(["Company", "SaleMonth"])["OrderCount"].sum().reset_index()
        fig = px.line(monthly_sales, x="SaleMonth", y="OrderCount", color="Company",
                       title=f"Monthly Sales Orders ({min_year})",
                       labels={"SaleMonth": "Month", "OrderCount": "Number of Orders"})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
        export_data["Sales Performance"] = sales_df
    else:
        st.info("No sales data available")

    st.divider()
    st.markdown("### Production Summary")
    prod_df = load_data(get_production_query(company_filter, min_year))
    if not prod_df.empty:
        monthly_prod = prod_df.groupby(["Company", "ProdMonth"]).agg(
            {"OrdersCount": "sum", "TotalOrderQty": "sum"}
        ).reset_index()
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for company in monthly_prod["Company"].unique():
            comp_data = monthly_prod[monthly_prod["Company"] == company]
            fig.add_trace(go.Bar(x=comp_data["ProdMonth"], y=comp_data["TotalOrderQty"], name=company))
        fig.update_layout(title=f"Production Orders by Month ({min_year})", height=400, barmode="group")
        st.plotly_chart(fig, use_container_width=True)
        export_data["Production"] = prod_df
    else:
        st.info("No production data available")

    st.divider()
    st.markdown("### Inventory Movement")
    inv_df = load_data(get_inventory_query(company_filter, min_year))
    if not inv_df.empty:
        inv_summary = inv_df.groupby(["Company", "InvMonth"]).agg(
            {"TotalQty": "sum", "TotalValue": "sum"}
        ).reset_index()
        fig = make_subplots(rows=1, cols=2, subplot_titles=("Quantity Movement", "Value Movement"))
        for company in inv_summary["Company"].unique():
            comp_data = inv_summary[inv_summary["Company"] == company]
            fig.add_trace(go.Bar(x=comp_data["InvMonth"], y=comp_data["TotalQty"], name=company), row=1, col=1)
            fig.add_trace(go.Bar(x=comp_data["InvMonth"], y=comp_data["TotalValue"], name=company, showlegend=False), row=1, col=2)
        fig.update_layout(height=400, barmode="group")
        st.plotly_chart(fig, use_container_width=True)
        export_data["Inventory"] = inv_df
    else:
        st.info("No inventory data available")

    st.divider()
    st.markdown("### Export All Data")
    if st.button("Download All Summary Data as Excel", key="export_all_summary"):
        if export_data:
            excel_data = export_to_excel(export_data)
            st.download_button(
                label="Download Excel",
                data=excel_data,
                file_name=f"strategic_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No data to export")


def page_company(bu_id):
    company_name = get_company_name(bu_id)
    company_full = get_company_full_name(bu_id)

    st.markdown(f"# {company_name} - {company_full}")
    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        year = st.selectbox("Select Year", options=range(2026, 2019, -1), index=0, key=f"{company_name}_year")
    with col2:
        st.empty()
    with col3:
        st.empty()

    export_data = {}

    st.markdown("### Company KPIs")
    emp_count = load_data(get_employee_count_query([bu_id]))
    fin_data = load_data(get_financial_performance_query([bu_id], year))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        total_emp = emp_count["TotalEmployees"].sum() if not emp_count.empty else 0
        st.metric("Total Employees", format_number(total_emp))
    with c2:
        active_emp = emp_count["ActiveEmployees"].sum() if not emp_count.empty else 0
        st.metric("Active Employees", format_number(active_emp))
    with c3:
        if not fin_data.empty:
            total_fin = fin_data["TotalAmount"].sum()
            st.metric("Total Financial Volume", format_currency(total_fin))
        else:
            st.metric("Total Financial Volume", "N/A")
    with c4:
        if not fin_data.empty:
            months_active = fin_data["TranMonth"].nunique()
            st.metric("Active Months", months_active)
        else:
            st.metric("Active Months", 0)

    st.divider()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Employees", "Financial Performance", "Budget vs Actual",
        "Marketing", "Production", "Inventory"
    ])

    with tab1:
        st.markdown("### Employee List")
        emp_detail = load_data(get_employee_detail_query(bu_id))
        if not emp_detail.empty:
            st.dataframe(emp_detail, use_container_width=True, height=400)
            export_data["Employees"] = emp_detail

            st.markdown("### Department Breakdown")
            dept_summary = load_data(get_employee_dept_summary_query([bu_id]))
            if not dept_summary.empty:
                fig = px.pie(dept_summary, values="EmployeeCount", names="Department",
                             title=f"{company_name} - Employee Distribution by Department")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No employee data available")

    with tab2:
        st.markdown("### Financial Performance")
        fin_df = load_data(get_financial_performance_query([bu_id], year))
        if not fin_df.empty:
            monthly = fin_df.groupby("TranMonth")["TotalAmount"].sum().reset_index()
            fig = px.bar(monthly, x="TranMonth", y="TotalAmount",
                          title=f"{company_name} - Monthly Financial Volume ({year})",
                          labels={"TranMonth": "Month", "TotalAmount": "Total Amount (BDT)"})
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

            journal_dist = fin_df.groupby("JournalType")["TotalAmount"].sum().reset_index()
            fig2 = px.pie(journal_dist, values="TotalAmount", names="JournalType",
                           title=f"{company_name} - Journal Type Distribution ({year})")
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)

            st.markdown("#### Top GL Accounts")
            top_gl = fin_df.groupby("GLAccount")["TotalAmount"].sum().nlargest(10).reset_index()
            fig3 = px.bar(top_gl, x="TotalAmount", y="GLAccount", orientation="h",
                           title=f"{company_name} - Top 10 GL Accounts ({year})")
            fig3.update_layout(height=400)
            st.plotly_chart(fig3, use_container_width=True)

            export_data["Financial Performance"] = fin_df
            export_data["Top GL Accounts"] = top_gl
        else:
            st.info("No financial data available")

    with tab3:
        st.markdown("### Budget vs Actual")
        budget_df = load_data(get_budget_vs_actual_query([bu_id], year))
        if not budget_df.empty:
            monthly_budget = budget_df.groupby("Month")["BudgetAmount"].sum().reset_index()
            fig = px.bar(monthly_budget, x="Month", y="BudgetAmount",
                          title=f"{company_name} - Monthly Budget ({year})",
                          labels={"Month": "Month", "BudgetAmount": "Budget Amount (BDT)"})
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

            budget_gl = budget_df.groupby("GLAccount")["BudgetAmount"].sum().nlargest(10).reset_index()
            fig2 = px.bar(budget_gl, x="BudgetAmount", y="GLAccount", orientation="h",
                           title=f"{company_name} - Top 10 Budget GL Accounts ({year})")
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)

            export_data["Budget"] = budget_df
        else:
            st.info("No budget data available")

    with tab4:
        st.markdown("### Marketing Budget")
        mkt_df = load_data(get_marketing_budget_query([bu_id]))
        if not mkt_df.empty:
            mkt_yearly = mkt_df.groupby(["Year", "Month"])["BudgetAmount"].sum().reset_index()
            fig = px.line(mkt_yearly, x="Month", y="BudgetAmount", color="Year",
                           title=f"{company_name} - Marketing Budget Trend",
                           labels={"Month": "Month", "BudgetAmount": "Budget (BDT)"})
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
            export_data["Marketing Budget"] = mkt_df
        else:
            st.info("No marketing budget data")

    with tab5:
        st.markdown("### Production")
        prod_df = load_data(get_production_query([bu_id], year))
        if not prod_df.empty:
            monthly_prod = prod_df.groupby("ProdMonth").agg(
                {"OrdersCount": "sum", "TotalOrderQty": "sum"}
            ).reset_index()

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=monthly_prod["ProdMonth"], y=monthly_prod["TotalOrderQty"],
                                  name="Order Quantity"), secondary_y=False)
            fig.add_trace(go.Scatter(x=monthly_prod["ProdMonth"], y=monthly_prod["OrdersCount"],
                                      name="Number of Orders", mode="lines+markers"), secondary_y=True)
            fig.update_layout(title=f"{company_name} - Production Overview ({year})", height=400)
            st.plotly_chart(fig, use_container_width=True)
            export_data["Production"] = prod_df
        else:
            st.info("No production data available")

    with tab6:
        st.markdown("### Inventory")
        inv_df = load_data(get_inventory_query([bu_id], year))
        if not inv_df.empty:
            inv_monthly = inv_df.groupby("InvMonth").agg(
                {"TotalQty": "sum", "TotalValue": "sum"}
            ).reset_index()

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=inv_monthly["InvMonth"], y=inv_monthly["TotalQty"],
                                  name="Quantity"), secondary_y=False)
            fig.add_trace(go.Scatter(x=inv_monthly["InvMonth"], y=inv_monthly["TotalValue"],
                                      name="Value (BDT)", mode="lines+markers"), secondary_y=True)
            fig.update_layout(title=f"{company_name} - Inventory Movement ({year})", height=400)
            st.plotly_chart(fig, use_container_width=True)

            stock_dist = inv_df.groupby("StockType")["TotalValue"].sum().reset_index()
            fig2 = px.pie(stock_dist, values="TotalValue", names="StockType",
                           title=f"{company_name} - Stock Type Distribution")
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)
            export_data["Inventory"] = inv_df
        else:
            st.info("No inventory data available")

    st.divider()
    st.markdown("### Export Company Data")
    if st.button(f"Download {company_name} Data as Excel", key=f"export_{company_name}"):
        if export_data:
            excel_data = export_to_excel(export_data)
            st.download_button(
                label="Download Excel",
                data=excel_data,
                file_name=f"{company_name}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_{company_name}"
            )
        else:
            st.warning("No data to export")


def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to",
        options=["Summary"] + [f"{COMPANIES[bu]['name']}" for bu in sorted(COMPANIES.keys())],
        key="main_nav"
    )

    st.sidebar.divider()
    st.sidebar.markdown("### Dashboard Info")
    st.sidebar.markdown(f"**Last Refresh:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    st.sidebar.markdown(f"**Companies:** {len(COMPANIES)}")
    st.sidebar.markdown("**Database:** DWH (203.202.241.211)")

    if page == "Summary":
        page_summary()
    else:
        for bu_id, info in COMPANIES.items():
            if page == info["name"]:
                page_company(bu_id)
                break


if __name__ == "__main__":
    main()