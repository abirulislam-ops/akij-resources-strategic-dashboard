"""
Supabase access helpers (server-side, service-role key).

The service-role key is only ever used from trusted server processes
(Streamlit Cloud backend, or the on-prem scheduler) — never exposed to a
browser. Officer-facing UI has no login; the role split (officer = add-only,
admin = edit) is enforced by the UI, not by RLS.

Credentials resolution (matches the SPA dashboard's supabase_data.py):
  1. Streamlit secrets (st.secrets)  — deployed on Streamlit Cloud
  2. environment variables           — local runs
  3. config.py (local, git-ignored)  — on-premise scripts
"""

import os

from supabase import create_client

TABLE_SBU = "romi_sbu"
TABLE_CAMPAIGN = "romi_campaign"


def _creds():
    url = key = None
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
    except Exception:
        pass
    url = url or os.environ.get("SUPABASE_URL")
    key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        try:
            import config
            url = url or getattr(config, "SUPABASE_URL", None)
            key = key or getattr(config, "SUPABASE_SERVICE_ROLE_KEY", None)
        except Exception:
            pass
    return url, key


def get_client():
    url, key = _creds()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured "
            "(set Streamlit secrets or environment variables)."
        )
    return create_client(url, key)


# ---------------------------------------------------------------------------
# SBU config table
# ---------------------------------------------------------------------------
def fetch_sbus():
    c = get_client()
    res = c.table(TABLE_SBU).select("*").order("name").execute()
    return res.data or []


def upsert_sbu(sbu: dict):
    c = get_client()
    c.table(TABLE_SBU).upsert(sbu).execute()


# ---------------------------------------------------------------------------
# Campaign table
# ---------------------------------------------------------------------------
def fetch_campaigns(business_unit_id=None):
    c = get_client()
    q = c.table(TABLE_CAMPAIGN).select("*").order("start_date", desc=True)
    if business_unit_id is not None:
        q = q.eq("business_unit_id", business_unit_id)
    res = q.execute()
    return res.data or []


def fetch_campaign(campaign_id):
    c = get_client()
    res = c.table(TABLE_CAMPAIGN).select("*").eq("id", campaign_id).execute()
    return (res.data or [None])[0]


def insert_campaign(row: dict):
    c = get_client()
    res = c.table(TABLE_CAMPAIGN).insert(row).execute()
    return (res.data or [None])[0]


def update_campaign(campaign_id, updates: dict):
    c = get_client()
    res = c.table(TABLE_CAMPAIGN).update(updates).eq("id", campaign_id).execute()
    return (res.data or [None])[0]


def delete_campaign(campaign_id):
    c = get_client()
    c.table(TABLE_CAMPAIGN).delete().eq("id", campaign_id).execute()
