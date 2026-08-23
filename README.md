# SafeLoop AI

SafeLoop AI is a bilingual construction-site safety observation workflow. Phase 0 provides the
pure state machine, guarded Supabase schema, report service, HTTP surface, and environment doctor.

## Backend setup

Use Python 3.12 and a virtual environment:

```cmd
cd /d "C:\Users\ngz\Downloads\zw safeloop\zw safeloop\backend"
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

Create `backend/.env` from `.env.example` and set `DATABASE_URL`. For hosted Supabase, use the
Session pooler connection string from the dashboard's Connect page. Do not commit `.env`.

Run the checks:

```cmd
python -m ruff check .
python -m mypy app --strict
python -m pytest
```

Run database integration tests only when a test database URL is explicitly supplied:

```cmd
set TEST_DATABASE_URL=postgresql://...
python -m pytest tests/test_report_service_db.py
```

The integration tests delete their fixture reports. Use a dedicated test database or test schema.

## Doctor and server

```cmd
python -m app.doctor
uvicorn app.main:app --reload
```

The doctor prints only the first required fix. It checks the working directory, dependencies,
environment, TCP reachability, database authentication, schema, guard triggers, and seed data.

## Curl walkthrough

With `ALLOW_DEBUG_AUTH=true` and the server running:

```cmd
curl -X POST http://127.0.0.1:8000/reports -H "X-Debug-User: 00000000-0000-0000-0000-000000000001" -H "X-Debug-Role: reporter" -H "Content-Type: application/json" -d "{\"description_original\":\"Unprotected edge\"}"
curl http://127.0.0.1:8000/reports/REPORT_ID -H "X-Debug-User: 00000000-0000-0000-0000-000000000001" -H "X-Debug-Role: reporter"
curl -X POST http://127.0.0.1:8000/reports/REPORT_ID/transition -H "X-Debug-User: 00000000-0000-0000-0000-000000000001" -H "X-Debug-Role: reporter" -H "Content-Type: application/json" -d "{\"target\":\"submitted\"}"
curl http://127.0.0.1:8000/reports/REPORT_ID -H "X-Debug-User: 00000000-0000-0000-0000-000000000003" -H "X-Debug-Role: reviewer"
```

The final response includes `available_transitions` computed by the server.

## Common startup failures

| Symptom | Fix |
| --- | --- |
| `py -3.12` is unavailable | Install Python 3.12 or use the project-managed runtime. |
| `asyncpg` build asks for C++ tools | Use Python 3.12/3.13 so a compatible wheel is selected. |
| Doctor reports missing `DATABASE_URL` | Create `backend/.env` and set the Supabase pooler URI. |
| Doctor reports database reachability | Check the host, port, VPN, and Supabase network access. |
| Doctor reports authentication | Re-copy the database password/URI from Supabase Connect. |
| Doctor reports missing schema | Apply `0001_schema.sql` and `0002_localised_en_checks.sql`. |
| Doctor reports missing seed data | Run `supabase/seed.sql` in the SQL Editor. |
| API returns `debug_auth_disabled` | Set `ALLOW_DEBUG_AUTH=true` only for local Phase 0 use. |

## Browser end-to-end suite

The Playwright suite runs only with `AI_PROVIDER=stub` and refuses any non-loopback Supabase URL.
CI starts the pinned local Supabase Auth/Postgres containers, resets migrations and seed data,
starts the frontend, and runs the complete English and Simplified Chinese loops with Chromium.
Running it locally requires a Docker-compatible runtime and Supabase CLI 2.115.0; after the local
stack and backend are ready, run `npm run test:e2e` from `frontend/`.
