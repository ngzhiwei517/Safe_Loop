# SafeLoop AI

SafeLoop AI is a bilingual construction-site safety loop for reporters, safety
reviewers, responsible technicians and crews. It captures an observation, keeps AI
drafts visibly separate from human decisions, assigns and verifies corrective work,
shows the reporter what changed, and turns verified cases into grounded crew lessons.
English and Simplified Chinese are first-class throughout the browser experience.

The workflow is deliberately human-controlled: AI cannot approve, assign, reject,
escalate, publish or close a case, and only a human reviewer can verify closure.

## Live Singapore demo

Open [safeloop-ai-demo.vercel.app](https://safeloop-ai-demo.vercel.app/en) for
English or [the Mandarin route](https://safeloop-ai-demo.vercel.app/zh-CN). The
API is deployed at
[safeloop-api-s55z7xniza-as.a.run.app](https://safeloop-api-s55z7xniza-as.a.run.app/health).
The demo uses only synthetic people and safety records; the six sign-in accounts
below work on both the hosted and local demo.

## See the full demo in three commands

Install Docker Desktop, Supabase CLI 2.115.0, Python 3.12 and Node.js 22 first. Then,
from PowerShell:

```powershell
git clone https://github.com/ngzhiwei517/Safe_Loop.git
cd Safe_Loop
pwsh -File scripts/demo.ps1
```

On macOS or Linux, use `bash scripts/demo.sh` for the third command. The script starts
the local Supabase stack, applies every migration, loads the verified 40-report demo,
and starts both applications. Open <http://127.0.0.1:3000/en> or
<http://127.0.0.1:3000/zh-CN>.

All six demo accounts use password `SafeLoopDemo!2026`:

| Role | Email |
| --- | --- |
| English reporter | `reporter-en@example.test` |
| Mandarin reporter | `reporter-zh@example.test` |
| Reviewer | `reviewer@example.test` |
| Responsible technician | `responsible@example.test` |
| Crew | `crew@example.test` |
| Administrator | `admin@example.test` |

These public credentials belong only in an isolated local/demo project. Never run
`supabase/demo_seed.sql` in a project containing real people or reports.

## Stack

| Layer | Pinned runtime or package |
| --- | --- |
| Backend | Python 3.12, FastAPI 0.115.6, asyncpg 0.30.0 |
| Workflow AI | LangGraph 1.2.10, Google Gen AI 2.19.0 |
| Frontend | Node.js 22, Next.js 15.5.21, React 19.0.0 |
| Local platform | Supabase CLI 2.115.0, PostgreSQL 17, pgvector |
| Production regions | Supabase `ap-southeast-1`, Cloud Run `asia-southeast1`, Vercel `sin1` |

Exact Python and npm dependency versions live in
`backend/requirements.txt` and `frontend/package-lock.json`.

## Manual development setup

Start and migrate the local database:

```powershell
supabase start
supabase db reset --local
```

Create `backend/.env` from `backend/.env.example` and `frontend/.env.local` from
`frontend/.env.example`. Use the values printed by `supabase status -o env`; do not
commit either environment file.

Run the backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m app.doctor
.venv\Scripts\python -m uvicorn app.main:app --reload
```

Run the frontend in a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

The API documentation is at <http://127.0.0.1:8000/docs>. Debug headers work only
when both `APP_ENV=local` and `ALLOW_DEBUG_AUTH=true`; normal browser use always uses
Supabase JWT authentication.

## Verification

Backend:

```powershell
cd backend
python -m ruff check .
python -m mypy app --strict
python -m pytest
```

Frontend:

```powershell
cd frontend
npm ci
npm run build
npm run tsc
npm run test
```

Production builds use the committed `frontend/lib/stateMachine.ts` contract and do
not require a running backend. When backend transitions change, start the backend,
run `npm run generate-state-machine` from `frontend`, then review and commit the
generated contract before building or deploying.

The database integration tests run when `TEST_DATABASE_URL` is set. The Playwright
suite refuses a non-loopback Supabase URL, runs with `AI_PROVIDER=stub`, and exercises
the full English and Mandarin workflow. CI starts an isolated Supabase stack, applies
all migrations, runs the browser loop, and loads the demo seed twice to prove it is
rerunnable.

## Database and demo data

Tracked migrations are in `supabase/migrations/`; `supabase/seed.sql` creates stable
base profiles, and `supabase/demo_seed.sql` adds 40 realistic reports across every
status, two approved procedures, rework histories, published briefings and quiz
responses. To add the demo to an already-running disposable database:

```powershell
$env:DATABASE_URL = "postgresql://..."
python scripts/apply_demo_seed.py
```

The script never prints the database URL and aborts unless the required demo counts
are present.

## Deployment and operations

The Singapore-only topology, environment contract, GitHub production configuration
and deployment procedure are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Rollback,
key rotation and AI-provider outage procedures are in [docs/RUNBOOK.md](docs/RUNBOOK.md).

Production deployment is an explicit `Deploy Singapore` workflow dispatch. It applies
database migrations first, deploys the backend container to Cloud Run, then deploys
the frontend to Vercel. The workflow refuses any configured runtime region other than
Singapore. The current hosted demo was deployed and smoke-tested in both languages on
23 August 2026.

## Common startup failures

| Symptom | Fix |
| --- | --- |
| `supabase` is not recognised | Install Supabase CLI 2.115.0 and restart the terminal. |
| Supabase cannot start | Start Docker Desktop and wait until its engine is ready. |
| Python environment creation fails | Install 64-bit Python 3.12 and enable its launcher/PATH entry. |
| `npm` is not recognised | Install Node.js 22 or run the checked build in GitHub Actions. |
| Doctor reports `DATABASE_URL` | Copy the local `DB_URL` or hosted session-pooler URL into `backend/.env`. |
| Doctor reports database reachability | Check the host, port, VPN and Supabase network restrictions. |
| Doctor reports authentication | Re-copy the database password and percent-encode special URI characters. |
| Doctor reports missing schema | Run `supabase db reset --local` or the tracked production migration workflow. |
| Sign-in fails for a demo user | Apply `supabase/demo_seed.sql`; base `seed.sql` identities intentionally have no password. |
| Deep health reports storage | Create both private buckets and set the Supabase service-role key. |
| Deep health reports provider | Confirm Vertex AI is enabled in `asia-southeast1`; follow the outage runbook. |
