# Verification report (v0.2.0)

Everything below was **actually executed** in the build environment, from a clean copy of this package
(new virtualenv from `requirements-dev.txt`, `npm ci` from `package-lock.json`, `.env` created from `.env.example`).

**Environment:** Linux (Ubuntu 24), Python 3.12.3, Node 22.22.2, npm 10.9.7, PostgreSQL 16.
**Not available there:** Windows, PowerShell, Docker, a web browser.

## Executed and passed

| Check | Result |
|---|---|
| Baseline: your uploaded M1 ZIP, unmodified, on PostgreSQL | 37 passed |
| Backend suite, default mode (temporary SQLite database) | **69 passed** |
| Same backend suite on PostgreSQL 16 (`TEST_DATABASE_URL=..._test`) | **69 passed** |
| Development database untouched by tests (SHA-256 of `data/modelmind_dev.db` before vs after a full run) | identical |
| Test harness refuses a PostgreSQL test database not ending in `_test` | refused (RuntimeError) |
| Fresh SQLite database: `alembic upgrade head`, `downgrade base`, `upgrade head` via the real CLI | passed (in test suite) |
| Old PostgreSQL schema (built by the original M1 migration) vs new code: `alembic check` | "No new upgrade operations detected" |
| `python -m app.check_config`: before migration / after migration / unedited `.env.example` / bad secret / unreachable PostgreSQL | exit 1 with hint / exit 0 / exit 2 with message / exit 2 / exit 1 with hint; no secret or DB password printed |
| Real server on SQLite + real Vite dev server: register, duplicate register (409), wrong login (401), login, create, list, patch, tampered token (401), no token (401), other user gets 404, delete, deleted project 404, all **through the Vite proxy** | all as expected |
| Server log after that flow searched for the passwords and the JWT | 0 matches |
| Frontend `npm run typecheck` (TypeScript 7.0.2) | 0 errors |
| Frontend `npm test` (Vitest, jsdom) | **28 passed** (4 files) |
| Frontend `npm run build` (Vite 8) | success; JS 306 kB (95 kB gzip), CSS 31 kB |
| `npm audit --omit=dev` | 0 vulnerabilities |

What the 28 frontend tests cover: API client (bearer header, error envelope, 401 handling, network failure, 204), validation rules,
login/registration flows, protected routes, session restore, locally expired token, server 401 mid-session, logout, project list /
empty / error+retry / create / validation / edit / delete with confirmation / search, project not found, dashboard honesty
(no ML metrics, no chart when empty), coming-soon pages. These tests replace the network (`fetch`) with a stub; the real components,
router and auth code run. The real backend integration was checked separately (row above) with HTTP calls, not through the React UI.

## NOT verified (be aware)

1. **PowerShell scripts** (`scripts/*.ps1`) were written carefully but **never executed** (no PowerShell here). The manual commands in the
   README are the dependable path; if a script misbehaves, use them and tell me the error.
2. **Windows behaviour in general**: Windows paths, `py` launcher, venv activation, npm on Windows. Nothing was run on Windows.
3. **Docker / `docker compose` / WSL**: not run. `docker-compose.yml` is unchanged in function from M1 apart from localhost-only port binding.
   This package does **not** fix Docker or WSL.
4. **Visual rendering in a real browser** (layout, colours, responsiveness, keyboard focus rings): no browser was available. The UI was
   verified through the type system, component tests, and the production build, **not by looking at it**. Expect to spot cosmetic issues.
5. **Python 3.11** (only 3.12 was run) and **Node versions other than 22**.
6. Tests cover behaviour, not load or security penetration. No rate limiting or lockout exists yet.
