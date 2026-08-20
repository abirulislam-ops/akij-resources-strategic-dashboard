# akij-resources-strategic-dashboard
# Akij Resources Strategic Planning Dashboard

## Overview
Interactive web dashboard connecting to Akij Resources DWH SQL Server database for strategic planning analysis.

## Features
- Company-wise summary with all 10 business units
- Employee counts, departments, designations
- Financial performance by GL account
- Budget vs Actual analysis
- Marketing budget trends
- Sales performance
- Production metrics
- Inventory movement
- Interactive charts (Plotly)
- Excel export functionality
- Date & company filters

## Database Connection
- Server: `203.202.241.211,1433`
- Database: `DWH`
- User: `mcp_user`
- Password: `iAOS@35o997`
- Driver: `ODBC Driver 18 for SQL Server`

## Quick Start
```bash
# Clone repository
git clone https://github.com/your-username/akij-resources-strategic-dashboard.git

# Navigate to dashboard folder
cd akij-resources-strategic-dashboard/dashboard

# Install dependencies
pip install -r requirements.txt

# Run dashboard
python -m streamlit run app.py
