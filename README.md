# SPA Shared Dashboard

The Streamlit dashboard colleagues access from **anywhere**. It reads the
**Supabase branch** (not the office DWH) and requires login.

## Features

- **Login** via Supabase Auth (per-user email/password, invite flow).
- **Views**: Overview, Financial, Inventory, Sales, Budget, Employees, Production.
- **Manual SQL box** (SELECT-only, read-only DB role, row cap).
- **Download** each dataset as Excel.

## Architecture

```
Colleague → Streamlit Cloud (public URL)
              │  login (Supabase Auth)
              ▼
           Supabase branch (Postgres)
              │  read (anon key + session; RLS = SELECT only)
              ▼
           data + charts
              │  manual SQL (spa_reader role, SELECT only)
```

## Deploy to Streamlit Cloud

1. Push this folder to a GitHub repo (the branch `supabase_data.py` reads
   credentials from **Streamlit secrets**, not the repo).
2. Create a Streamlit Cloud app pointing at `app.py`.
3. In **Streamlit → Settings → Secrets**, add:

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_ANON_KEY = "eyJ..."
READER_DB_HOST = "db.xxxx.supabase.co"
READER_DB_PORT = "5432"
READER_DB_DATABASE = "postgres"
READER_DB_USER = "spa_reader"
READER_DB_PASSWORD = "your-spa-reader-password"
```

> The `spa_reader` password must match the one set in `schema.sql`
> (`CREATE ROLE spa_reader LOGIN PASSWORD '...'`).

4. Deploy. Share the URL with colleagues.

## Run locally (for testing)

```powershell
cd "C:\Abir\Akij Resources\Strategic planning Department\SPA Shared Dashboard"
pip install -r requirements.txt
python -m streamlit run app.py
```

When run locally, `supabase_data.py` falls back to
`SPA Branch Database\config.py` for credentials.

## Security

| Concern | Control |
|---------|---------|
| Who can log in | Supabase Auth (invite-only users) |
| What they can read | RLS: authenticated = SELECT only |
| Manual SQL | `spa_reader` role: SELECT only, read-only transactions, row cap, timeout |
| Secrets | Stored in Streamlit secrets, never committed to the repo |
