from db_config import get_company_id_list

COMPANY_IDS = get_company_id_list()
COMPANY_ID_LIST = ",".join(str(x) for x in COMPANY_IDS)


def get_employee_count_query(bu_ids=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    return f"""
    SELECT 
      bu.strShortCode as Company,
      COUNT(*) as TotalEmployees,
      SUM(CASE WHEN e.isActive = 1 THEN 1 ELSE 0 END) as ActiveEmployees,
      SUM(CASE WHEN e.isActive = 0 THEN 1 ELSE 0 END) as InactiveEmployees
    FROM [saas].[empEmployeeBasicInfoArc] e
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON e.intBusinessUnitId = bu.intBusinessUnitId
    WHERE e.intBusinessUnitId IN ({ids})
    GROUP BY bu.strShortCode
    ORDER BY bu.strShortCode
    """


def get_employee_detail_query(bu_id):
    return f"""
    SELECT 
      e.strEmployeeCode as EmployeeCode,
      e.strEmployeeName as EmployeeName,
      d.strDepartment as Department,
      dg.strDesignation as Designation,
      ed.strHRPostionName as HRPosition,
      ed.strOfficeMail as OfficialEmail,
      ed.strOfficeMobile as OfficialPhone,
      ed.strPersonalMobile as PersonalPhone,
      e.dteJoiningDate as JoiningDate,
      e.isActive as IsActive
    FROM [saas].[empEmployeeBasicInfoArc] e
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON e.intBusinessUnitId = bu.intBusinessUnitId
    LEFT JOIN [saas].[masterDepartmentArc] d ON e.intDepartmentId = d.intDepartmentId
    LEFT JOIN [saas].[masterDesignationArc] dg ON e.intDesignationId = dg.intDesignationId
    LEFT JOIN [saas].[empEmployeeBasicInfoDetailsArc] ed ON e.intEmployeeBasicInfoId = ed.intEmployeeId
    WHERE e.intBusinessUnitId = {bu_id}
    AND e.isActive = 1
    ORDER BY e.strEmployeeName
    """


def get_employee_dept_summary_query(bu_ids=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    where = f"AND e.intBusinessUnitId IN ({ids})" if bu_ids else ""
    return f"""
    SELECT 
      bu.strShortCode as Company,
      d.strDepartment as Department,
      COUNT(*) as EmployeeCount
    FROM [saas].[empEmployeeBasicInfoArc] e
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON e.intBusinessUnitId = bu.intBusinessUnitId
    LEFT JOIN [saas].[masterDepartmentArc] d ON e.intDepartmentId = d.intDepartmentId
    WHERE e.isActive = 1 {where}
    GROUP BY bu.strShortCode, d.strDepartment
    ORDER BY bu.strShortCode, EmployeeCount DESC
    """


def get_marketing_budget_query(bu_ids=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    return f"""
    SELECT 
      bu.strShortCode as Company,
      gl.strGeneralLedgerName as GLAccount,
      b.intYearId as Year,
      b.intMonthId as Month,
      SUM(b.numAmount) as BudgetAmount
    FROM [bgt].[tblBudgetIncomeExpenseRowArc] b
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON b.intBusinessUnitId = bu.intBusinessUnitId
    LEFT JOIN [fin].[tblGeneralLedgerArc] gl ON b.intGeneralLedgerId = gl.intGeneralLedgerId
    WHERE b.intBusinessUnitId IN ({ids})
    AND gl.strGeneralLedgerName LIKE '%market%'
    AND b.isActive = 1
    GROUP BY bu.strShortCode, gl.strGeneralLedgerName, b.intYearId, b.intMonthId
    ORDER BY bu.strShortCode, Year, Month
    """


def get_financial_performance_query(bu_ids=None, year=None, month=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    where_year = f"AND YEAR(j.dteTransactionDate) = {year}" if year else ""
    where_month = f"AND MONTH(j.dteTransactionDate) = {month}" if month else ""
    return f"""
    SELECT 
      bu.strShortCode as Company,
      gl.strGeneralLedgerName as GLAccount,
      YEAR(j.dteTransactionDate) as TranYear,
      MONTH(j.dteTransactionDate) as TranMonth,
      jt.strAccountingJournalTypeName as JournalType,
      SUM(j.numAmount) as TotalAmount
    FROM [fin].[tblAccountingJournalArc] j
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON j.intBusinessUnitId = bu.intBusinessUnitId
    LEFT JOIN [fin].[tblGeneralLedgerArc] gl ON j.intGeneralLedgerId = gl.intGeneralLedgerId
    LEFT JOIN [fin].[tblAccountingJournalTypeArc] jt ON j.intAccountingJournalTypeId = jt.intAccountingJournalTypeId
    WHERE j.intBusinessUnitId IN ({ids})
    AND j.isActive = 1
    {where_year}
    {where_month}
    GROUP BY bu.strShortCode, gl.strGeneralLedgerName, YEAR(j.dteTransactionDate), MONTH(j.dteTransactionDate), jt.strAccountingJournalTypeName
    ORDER BY bu.strShortCode, TranYear, TranMonth
    """


def get_budget_vs_actual_query(bu_ids=None, year=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    where_year = f"AND b.intYearId = {year}" if year else ""
    return f"""
    SELECT 
      bu.strShortCode as Company,
      gl.strGeneralLedgerName as GLAccount,
      b.intYearId as Year,
      b.intMonthId as Month,
      SUM(b.numAmount) as BudgetAmount
    FROM [bgt].[tblBudgetIncomeExpenseRowArc] b
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON b.intBusinessUnitId = bu.intBusinessUnitId
    LEFT JOIN [fin].[tblGeneralLedgerArc] gl ON b.intGeneralLedgerId = gl.intGeneralLedgerId
    WHERE b.intBusinessUnitId IN ({ids})
    AND b.isActive = 1
    {where_year}
    GROUP BY bu.strShortCode, gl.strGeneralLedgerName, b.intYearId, b.intMonthId
    ORDER BY bu.strShortCode, Year, Month
    """


def get_sales_performance_query(bu_ids=None, year=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    where_year = f"AND YEAR(s.dteSalesOrderDate) = {year}" if year else ""
    return f"""
    SELECT 
      bu.strShortCode as Company,
      YEAR(s.dteSalesOrderDate) as SaleYear,
      MONTH(s.dteSalesOrderDate) as SaleMonth,
      COUNT(*) as OrderCount,
      SUM(s.numNetOrderValue) as TotalOrderValue
    FROM [oms].[tblSalesOrderHeaderArc] s
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON s.intBusinessUnitId = bu.intBusinessUnitId
    WHERE s.intBusinessUnitId IN ({ids})
    AND s.isActive = 1
    {where_year}
    GROUP BY bu.strShortCode, YEAR(s.dteSalesOrderDate), MONTH(s.dteSalesOrderDate)
    ORDER BY bu.strShortCode, SaleYear, SaleMonth
    """


def get_production_query(bu_ids=None, year=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    where_year = f"AND YEAR(p.dteStartDate) = {year}" if year else ""
    return f"""
    SELECT 
      bu.strShortCode as Company,
      YEAR(p.dteStartDate) as ProdYear,
      MONTH(p.dteStartDate) as ProdMonth,
      COUNT(*) as OrdersCount,
      SUM(p.numOrderQty) as TotalOrderQty
    FROM [mes].[tblProductionOrderArc] p
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON p.intBusinessUnitId = bu.intBusinessUnitId
    WHERE p.intBusinessUnitId IN ({ids})
    AND p.isActive = 1
    {where_year}
    GROUP BY bu.strShortCode, YEAR(p.dteStartDate), MONTH(p.dteStartDate)
    ORDER BY bu.strShortCode, ProdYear, ProdMonth
    """


def get_inventory_query(bu_ids=None, year=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    where_year = f"AND YEAR(h.dteLastActionDateTime) = {year}" if year else ""
    return f"""
    SELECT 
      bu.strShortCode as Company,
      YEAR(h.dteLastActionDateTime) as InvYear,
      MONTH(h.dteLastActionDateTime) as InvMonth,
      i.strItemName as Item,
      SUM(i.numTransactionQuantity) as TotalQty,
      SUM(i.monTransactionValue) as TotalValue,
      i.strInventoryStockTypeName as StockType
    FROM [wms].[tblInventoryTransactionRowArc] i
    INNER JOIN [wms].[tblInventoryTransactionHeaderArc] h ON i.intInventoryTransactionId = h.intInventoryTransactionId
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON h.intBusinessUnitId = bu.intBusinessUnitId
    WHERE h.intBusinessUnitId IN ({ids})
    AND h.isActive = 1
    {where_year}
    GROUP BY bu.strShortCode, YEAR(h.dteLastActionDateTime), MONTH(h.dteLastActionDateTime), i.strItemName, i.strInventoryStockTypeName
    ORDER BY bu.strShortCode, InvYear, InvMonth
    """


def get_gl_summary_query(bu_ids=None, year=None):
    ids = ",".join(str(x) for x in (bu_ids or COMPANY_IDS))
    where_year = f"AND YEAR(j.dteTransactionDate) = {year}" if year else ""
    return f"""
    SELECT 
      bu.strShortCode as Company,
      gl.strGeneralLedgerName as GLAccount,
      SUM(j.numAmount) as TotalAmount
    FROM [fin].[tblAccountingJournalArc] j
    INNER JOIN [saas].[masterBusinessUnitArc] bu ON j.intBusinessUnitId = bu.intBusinessUnitId
    LEFT JOIN [fin].[tblGeneralLedgerArc] gl ON j.intGeneralLedgerId = gl.intGeneralLedgerId
    WHERE j.intBusinessUnitId IN ({ids})
    AND j.isActive = 1
    {where_year}
    GROUP BY bu.strShortCode, gl.strGeneralLedgerName
    ORDER BY ABS(SUM(j.numAmount)) DESC
    """


def get_available_years_query():
    return """
    SELECT DISTINCT YEAR(j.dteTransactionDate) as Year
    FROM [fin].[tblAccountingJournalArc] j
    WHERE j.isActive = 1
    ORDER BY Year DESC
    """