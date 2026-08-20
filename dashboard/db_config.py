import os
import pyodbc
import pandas as pd
import streamlit as st
from contextlib import contextmanager

# Database connection settings - READ FROM ENVIRONMENT VARIABLES
# Users must set these before running the dashboard:
#   set DB_SERVER=203.202.241.211,1433
#   set DB_NAME=DWH
#   set DB_USER=mcp_user
#   set DB_PASSWORD=iAOS@35o997
DB_CONFIG = {
    "server": os.getenv("DB_SERVER", "203.202.241.211,1433"),
    "database": os.getenv("DB_NAME", "DWH"),
    "username": os.getenv("DB_USER", "mcp_user"),
    "password": os.getenv("DB_PASSWORD", "iAOS@35o997"),
    "driver": "{ODBC Driver 18 for SQL Server}",
    "timeout": int(os.getenv("DB_TIMEOUT", "30")),
}

# Company mapping
COMPANIES = {
    232: {"name": "AAFL", "full": "Akij Agro Food Ltd"},
    4: {"name": "ACCL", "full": "Akij Cement Co. Ltd"},
    144: {"name": "AEL", "full": "Akij Enterprise Ltd"},
    175: {"name": "ARMCL", "full": "Akij Rice & Molasses Co. Ltd"},
    184: {"name": "iBOS", "full": "iBOS Ltd"},
    221: {"name": "ACL", "full": "Akij Computer Ltd"},
    224: {"name": "AIL", "full": "Akij Insaf Ltd"},
    245: {"name": "AASL", "full": "Akij Agro Stores Ltd"},
    252: {"name": "NJL", "full": "New Jilhong Ltd"},
    255: {"name": "AMPL", "full": "Akij Multi Products Ltd"},
}


def get_connection():
    """Get database connection using environment variables"""
    conn_str = (
        f"DRIVER={DB_CONFIG['driver']};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['username']};"
        f"PWD={DB_CONFIG['password']};"
        f"TrustServerCertificate=Yes;"
        f"Timeout={DB_CONFIG['timeout']};"
    )
    return pyodbc.connect(conn_str)


@st.cache_data(ttl=300)
def load_data(query, params=None):
    """Load data with caching"""
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Query error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def get_company_id_list():
    """Return list of company IDs"""
    return [232, 4, 144, 175, 184, 221, 224, 245, 252, 255]


def get_company_name(bu_id):
    """Get company short name by ID"""
    return COMPANIES.get(bu_id, {}).get("name", f"BU-{bu_id}")


def get_company_full_name(bu_id):
    """Get company full name by ID"""
    return COMPANIES.get(bu_id, {}).get("full", f"Business Unit {bu_id}")