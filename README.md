# ModelMind AI

**Train. Understand. Stress-Test. Diagnose. Improve.**

ModelMind AI is an ML experimentation, failure-intelligence and stress-testing platform.
This package is **M1 + Frontend Foundation (v0.2.0)**: a working full-stack application with real
authentication and project management. The ML features are on the roadmap and are **not implemented yet**
(see [Implemented vs deferred](#implemented-vs-deferred)).

| Part | Stack | Folder |
|---|---|---|
| Backend API | Python, FastAPI, SQLAlchemy 2, Alembic | `backend/` |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4 | `frontend/` |
| Database | **SQLite** (local development) or **PostgreSQL** (deployment) | `data/` (SQLite file), `docker-compose.yml` |

---

## Quick start on Windows (no Docker, no PostgreSQL)

### Prerequisites

| Tool | Version | Check in PowerShell |
|---|---|---|
| Python | 3.11 or 3.12 (tested on 3.12) | `py --version` |
| Node.js | 20.19 or newer (LTS) | `node --version` |
| VS Code | any | |

Docker and WSL are **not** needed for this mode.

### Option 1: helper scripts (recommended)

Open the project folder (`modelmind`) in VS Code, then **Terminal > New Terminal** (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
```

This creates `backend\.venv`, installs dependencies, creates `.env` **only if it does not exist** (with a freshly generated
`SECRET_KEY`), creates the SQLite database, and runs `npm install`. Then use **two terminals**:

| Terminal | Command | Result |
|---|---|---|
| 1 (backend) | `powershell -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1` | API on http://127.0.0.1:8000 (docs at `/docs`) |
| 2 (frontend) | `powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1` | App on http://localhost:5173 |

Open **http://localhost:5173**. (`-ExecutionPolicy Bypass` applies to that one command only; it changes no system setting.)

### Option 2: manual commands (same result, no scripts)

From the project root:

```powershell
# 1. Create your configuration (never overwrites if you skip this when .env exists)
Copy-Item .env.example .env
py -c "import secrets; print(secrets.token_urlsafe(48))"      # copy the output
code .env                                                      # paste it after SECRET_KEY=  (replace the CHANGE_ME text)

# 2. Backend setup
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
alembic upgrade head
```

**Terminal 1** (backend; keep it open):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000 --no-access-log
```

**Terminal 2** (frontend; keep it open):

```powershell
cd frontend
npm install        # first time only
npm run dev
```

If PowerShell says *"running scripts is disabled"* when activating the venv, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Stop, restart, reset

* **Stop:** press `Ctrl+C` in each terminal (type `deactivate` to leave the venv).
* **Restart:** run the two start commands again. Data is kept in `data\modelmind_dev.db`.
* **Reset local data:** stop the backend, delete `data\modelmind_dev.db`, then `alembic upgrade head` (from `backend`).

### Ports

| Port | Used by | Change it |
|---|---|---|
| 5173 | Vite dev server | `frontend/vite.config.ts` (`server.port`) |
| 8000 | FastAPI backend | `--port` in the uvicorn command, and `VITE_DEV_PROXY_TARGET` in `frontend/.env.local` |
| 5432 | PostgreSQL (only in PostgreSQL mode) | `POSTGRES_PORT` in `.env` |

How the pieces connect: the browser only talks to `http://localhost:5173`. Vite forwards every `/api/*` request to
`http://127.0.0.1:8000`. API configuration lives in **one place**: `frontend/src/config.ts`.

---

## PostgreSQL / Docker mode (intended for deployment)

> Requires Docker Desktop **running**, which on Windows needs WSL 2 (or Hyper-V). **This package does not fix a broken
> WSL/Docker installation; that is a separate setup task** (see `wsl --install` in Microsoft's docs). You can ignore this
> section and use SQLite until it works.

1. In `.env`: comment out the SQLite `DATABASE_URL`, then uncomment the PostgreSQL block (Option B) and replace both
   `CHANGE_ME_...` passwords with the **same** letters-and-digits password.
2. Start the database and migrate:
   ```powershell
   docker compose up -d postgres
   docker compose ps                      # wait for "healthy"
   cd backend
   .\.venv\Scripts\Activate.ps1
   alembic upgrade head
   ```
3. Run the backend and frontend exactly as above. Stop the database with `docker compose stop postgres`
   (`docker compose down -v` also deletes its data).

`ENVIRONMENT=production` refuses to start with SQLite.

---

## Tests and checks

All at once: `powershell -ExecutionPolicy Bypass -File .\scripts\run-tests.ps1`, or individually:

```powershell
# Backend (from backend\, venv active)
python -m pytest

# Frontend (from frontend\)
npm run typecheck
npm test
npm run build
```

**Safety:** backend tests use a brand-new **temporary SQLite file** by default and can never touch `data\modelmind_dev.db`
or your PostgreSQL development database. To run them on PostgreSQL, set `TEST_DATABASE_URL` to a *separate* database
whose name ends in `_test` (anything else is refused). The test header prints which database is under test.

Manual checklist: [`docs/SMOKE_TEST.md`](docs/SMOKE_TEST.md). Last verification results: [`docs/VERIFICATION_REPORT.md`](docs/VERIFICATION_REPORT.md).

---

## Implemented vs deferred

| Implemented (real, tested) | Deferred (not built; shown as "Coming soon" in the UI) |
|---|---|
| Registration, login (Argon2id, JWT), session restore, logout, expired-token handling | CSV dataset upload and dataset versioning (M2) |
| Projects: create, list (paged), view, edit, delete, owner-scoped | Data profiling (M3) |
| SQLite **and** PostgreSQL support, Alembic migrations on both | Experiment configuration and training (M5-M6) |
| Health endpoints, structured logging with redaction, uniform error envelope | MLflow tracking and model comparison (M7-M8) |
| Config check (`python -m app.check_config`), actionable startup errors | What-If Lab and SHAP, DataTwin, Failure Intelligence (Phases 2-4) |
| React app: landing, auth pages, dashboard, projects, responsive dark UI | AWS deployment (Phase 5), rate limiting, email verification, password reset |

No fake metrics, experiments or datasets are displayed anywhere.

---

## Security notes (read before deploying)

* Passwords: Argon2id. Tokens: HS256 JWT with an algorithm allow-list; `exp` and `sub` required. Login timing does not reveal registered emails.
* Every project query is filtered by the authenticated owner; another user's project returns the same 404 as a missing one.
* Logs never contain passwords, tokens, secret keys, DB passwords, request bodies, or query strings (tests assert this).
* The frontend keeps the token in `sessionStorage` (cleared when the tab closes). This is convenient but readable by any script running on the page; a hardened deployment should consider httpOnly cookies. Not implemented in this milestone.
* **Local-development-only settings:** SQLite, `--reload`, CORS for localhost origins, no HTTPS, no rate limiting or login lockout. Do not expose this build to the internet.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModelMind cannot start: the configuration is invalid.` | Read the listed variable names. Usually `.env` is missing (`Copy-Item .env.example .env`) or `SECRET_KEY` still says `CHANGE_ME`. Run `python -m app.check_config` from `backend\` for a full report. |
| `.env` edits are ignored | Make sure the file is named exactly `.env` (not `.env.txt`; enable *View > File name extensions* in Explorer) and sits in the project root, next to `README.md`. |
| Browser shows "Cannot reach the ModelMind API" | The backend is not running, or is not on port 8000. Check Terminal 1; open http://127.0.0.1:8000/api/v1/health. |
| `Port 5173 is already in use` | Another Vite is running. Close it, or change the port in `frontend/vite.config.ts`. |
| `Address already in use` on 8000 | Find it: `netstat -ano \| findstr :8000`, stop it: `taskkill /PID <pid> /F`. |
| `no such table: users` / "Database tables are missing or outdated" | `alembic upgrade head` from `backend\` (the start script does this automatically). |
| `running scripts is disabled on this system` | Use `powershell -ExecutionPolicy Bypass -File ...` as shown, or `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| `py` is not recognized | Reinstall Python from python.org with "Add python.exe to PATH" (or "py launcher") ticked; reopen PowerShell. |
| `npm install` fails with engine errors | Node is too old. Install the current LTS from nodejs.org. |
| Docker: `error during connect` / "WSL" messages | Docker Desktop needs WSL 2. Not required for SQLite mode. See Microsoft's `wsl --install` guide. |
| PostgreSQL: `password authentication failed` | `DATABASE_URL` password differs from `POSTGRES_PASSWORD`. After changing it: `docker compose down -v` then `up -d postgres`. |
| PostgreSQL: `port is already allocated` | Another PostgreSQL uses 5432. Set `POSTGRES_PORT=5433` and use 5433 in `DATABASE_URL`. |
| Login worked before, now "session expired" | The token lifetime is `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60), or `SECRET_KEY` changed. Sign in again. |

---

## Project structure

```
modelmind/
  .env.example  docker-compose.yml  README.md  CHANGE_MANIFEST.md
  scripts/        setup-local.ps1  start-backend.ps1  start-frontend.ps1  run-tests.ps1
  docs/           ARCHITECTURE.md  SMOKE_TEST.md  VERIFICATION_REPORT.md
  docker/postgres/init.sql
  backend/
    app/
      main.py            app factory, request logging middleware, lifespan checks
      check_config.py    `python -m app.check_config`
      interfaces.py      Protocols for FUTURE storage/profiling/experiments/artifacts/tracking
      core/              config, security, errors, logging, startup diagnostics
      db/                engine (SQLite+PostgreSQL), models, UTC datetime type
      api/               routers, schemas, dependencies
      services/          business logic (auth, projects)
      ml_engine/         framework-free ML code (starts in M3)
      extensions/        reserved: whatif, datatwin, failure
    alembic/             migrations
    tests/               pytest suite
  frontend/
    src/config.ts        the ONE place for API/base configuration
    src/api/             typed API client (+ tests)
    src/auth/            AuthContext, route guards, token handling
    src/components/      layout, design-system primitives, forms, modal, toasts
    src/features/        projects hook, form, card
    src/pages/           Landing, Login, Register, Dashboard, Projects, ProjectDetail, ComingSoon
```
