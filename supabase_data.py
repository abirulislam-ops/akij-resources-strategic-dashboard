"""
Akij Resources — SPA Shared Dashboard: data access layer.

Connects to the Supabase branch (Postgres) for the shared Streamlit dashboard.

Two access paths:
  1. Auth        -> supabase-py (email/password) — for login.
  2. Read data   -> supabase-py PostgREST (anon key + user session) — RLS enforced.
  3. Manual SQL  -> psycopg2 as "spa_reader" (SELECT-only role) — for arbitrary
                    read-only queries typed by the user.

Credentials are read from Streamlit secrets when deployed, or from
SPA Branch Database/config.py when run locally.
"""

import os
import sys
import re
import pandas as pd

# Allow local import of config.py from the sibling "SPA Branch Database" folder.
_LOCAL_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "SPA Branch Database", "config.py",
)


def _secret_or_config(name):
    """Return a value from st.secrets (deployed) or config.py (local)."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return None


def get_config():
    """Return a dict of config values, preferring Streamlit secrets."""
    cfg = {}
    # Try Streamlit secrets first
    try:
        import streamlit as st
        s = st.secrets
        cfg["url"] = s.get("SUPABASE_URL")
        cfg["anon"] = s.get("SUPABASE_ANON_KEY")
        cfg["reader_host"] = s.get("READER_DB_HOST")
        cfg["reader_port"] = s.get("READER_DB_PORT")
        cfg["reader_db"] = s.get("READER_DB_DATABASE")
        cfg["reader_user"] = s.get("READER_DB_USER")
        cfg["reader_password"] = s.get("READER_DB_PASSWORD")
    except Exception:
        pass

    # Fall back to local config.py if any key is missing
    if not cfg.get("url") or not cfg.get("anon"):
        if os.path.exists(_LOCAL_CONFIG):
            sys.path.insert(0, os.path.dirname(_LOCAL_CONFIG))
            try:
                import config as _c
                cfg.setdefault("url", _c.SUPABASE_URL)
                cfg.setdefault("anon", _c.SUPABASE_ANON_KEY)
                cfg.setdefault("reader_host", _c.READER_DB["host"])
                cfg.setdefault("reader_port", _c.READER_DB["port"])
                cfg.setdefault("reader_db", _c.READER_DB["database"])
                cfg.setdefault("reader_user", _c.READER_DB["user"])
                cfg.setdefault("reader_password", _c.READER_DB["password"])
            except Exception:
                pass
    return cfg


# ============================================================
# AUTH (supabase-py)
# ============================================================
def get_supabase_client():
    from supabase import create_client
    cfg = get_config()
    if not cfg.get("url") or not cfg.get("anon"):
        raise RuntimeError("Supabase URL/anon key not configured.")
    return create_client(cfg["url"], cfg["anon"])


def sign_in(email, password):
    """Return (session_or_None, error_message_or_None).

    Returns the Auth `Session` object (which has .access_token and
    .refresh_token), not the raw AuthResponse.
    """
    try:
        client = get_supabase_client()
        res = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        # res is an AuthResponse; the token lives on res.session.
        return res.session, None
    except Exception as e:
        return None, _friendly_auth_error(e)


def _friendly_auth_error(e):
    s = str(e)
    if "Invalid login credentials" in s:
        return "Invalid email or password."
    if "Email not confirmed" in s:
        return "Email not confirmed — check your invite email and click the link."
    return f"Login failed: {s}"


# ============================================================
# READ-ONLY DATA (PostgREST via supabase-py)
# ============================================================
def fetch_table(session, table, columns="*", filters=None, limit=5000):
    """Read rows from a branch table via the user's authenticated session (RLS)."""
    from supabase import create_client
    cfg = get_config()
    client = create_client(cfg["url"], cfg["anon"])
    client.postgrest.auth(session.access_token)

    q = client.table(table).select(columns)
    if filters:
        for col, val in filters.items():
            q = q.eq(col, val)
    q = q.limit(limit)
    res = q.execute()
    return pd.DataFrame(res.data or [])


# ============================================================
# MANUAL SQL (psycopg2 as spa_reader, SELECT-only)
# ============================================================
def manual_query(sql, limit=5000, timeout_sec=30):
    """Run a user-supplied SQL query as the read-only spa_reader role.

    Safety:
      - Only a single SELECT statement is allowed (whitespace-trimmed, no ';').
      - Runs as spa_reader (SELECT-only, read-only transactions at DB level).
      - Enforced LIMIT + statement timeout.
    Returns (df_or_None, error_or_None).
    """
    cleaned = sql.strip().rstrip(";").strip()
    if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
        return None, "Only SELECT queries are allowed."
    if ";" in cleaned:
        return None, "Multiple statements are not allowed."

    try:
        import psycopg2
        cfg = get_config()
        conn = psycopg2.connect(
            host=cfg["reader_host"],
            port=int(cfg.get("reader_port") or 5432),
            dbname=cfg["reader_db"],
            user=cfg["reader_user"],
            password=cfg["reader_password"],
            sslmode="require",
            connect_timeout=15,
            options=f"-c statement_timeout={timeout_sec * 1000}",
        )
        # Enforce read-only at the DB session level (defence in depth).
        conn.set_session(readonly=True, autocommit=True)
    except Exception as e:
        return None, f"Could not connect to read-only database: {e}"

    try:
        df = pd.read_sql(cleaned, conn)
        if len(df) > limit:
            df = df.head(limit)
        return df, None
    except Exception as e:
        return None, f"Query error: {e}"
    finally:
        conn.close()


# ============================================================
# LIST TABLES (for the SQL helper)
# ============================================================
def list_tables():
    """Return a curated list of branch tables + their purpose."""
    return [
        ("business_unit", "Business units (short code, name)"),
        ("department", "Departments"),
        ("designation", "Designations / job titles"),
        ("general_ledger", "GL accounts (code, name, IS group)"),
        ("employee", "Employees (code, name, BU, dept, designation)"),
        ("employee_details", "Employee contact (email, mobile)"),
        ("budget_row", "Budget by BU / GL / year / month"),
        ("production_order", "Production orders (qty, item, date)"),
        ("summary_finance_monthly", "Finance summary: company/year/month/ISGroup/GL"),
        ("summary_inventory_monthly", "Inventory summary: company/year/month/stock type"),
        ("summary_sales_monthly", "Sales summary: company/year/month/orders/value"),
    ]
