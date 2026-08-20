# Akij Resources Strategic Planning Dashboard

## Overview
Interactive web dashboard for strategic planning analysis connecting to Akij Resources DWH SQL Server database.

## ⚠️ SECURITY NOTE
**This repository is PRIVATE** on GitHub. Database credentials are stored in environment variables, not in the code.

## Features
- Company-wise financial summaries for all 10 business units
- Employee analytics with department breakdown
- Budget vs Actual analysis
- Marketing, Sales, Production, Inventory metrics
- Interactive charts with Plotly
- Excel export functionality
- Date & company filters

## Database Configuration
This dashboard connects to Akij Resources DWH Server.

### Required Environment Variables
Create a `.env` file or set these before running:

```bash
# Windows Command Prompt
set DB_SERVER=203.202.241.211,1433
set DB_NAME=DWH
set DB_USER=mcp_user
set DB_PASSWORD=iAOS@35o997

# PowerShell
$env:DB_SERVER="203.202.241.211,1433"
$env:DB_NAME="DWH"
$env:DB_USER="mcp_user"
$env:DB_PASSWORD="iAOS@35o997"
```

### Connection Details
- **Server**: `203.202.241.211,1433`
- **Database**: `DWH`
- **User**: `mcp_user`
- **Password**: `iAOS@35o997`
- **Driver**: `ODBC Driver 18 for SQL Server`

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-username/akij-resources-strategic-dashboard.git

# 2. Navigate to dashboard folder
cd akij-resources-strategic-dashboard/dashboard

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
# Windows:
set DB_SERVER=203.202.241.211,1433
set DB_NAME=DWH
set DB_USER=mcp_user
set DB_PASSWORD=iAOS@35o997

# PowerShell:
$env:DB_SERVER="203.202.241.211,1433"
$env:DB_NAME="DWH"
$env:DB_USER="mcp_user"
$env:DB_PASSWORD="iAOS@35o997"

# 5. Run the dashboard
python -m streamlit run app.py
```

## Access
Open http://localhost:8501 in your browser

## Dashboard Pages

### Summary Page
- Employee counts by company (active/inactive)
- Department heatmap across all companies
- Financial trend by month
- Marketing budget comparison
- Sales performance
- Production summary
- Inventory movement

### Company Tabs (10 companies each)
- **Employees**: Full employee list + department pie chart
- **Financial Performance**: Monthly volume, journal type distribution, top GL accounts
- **Budget vs Actual**: Monthly budget bars, top budget GL accounts
- **Marketing**: Marketing budget trend by year
- **Production**: Orders count + quantity dual-axis chart
- **Inventory**: Quantity + value chart, stock type distribution

## Security
- Repository is **PRIVATE** on GitHub
- Database credentials stored in environment variables
- Never commit real passwords to GitHub
- `.env` files and `.streamlit/secrets.toml` are gitignored

## License
MIT