# Architecture overview (M1 + Frontend Foundation)

```
Browser (React SPA, http://localhost:5173)
   |  /api/*  (Vite dev proxy: same origin, no CORS needed)
   v
FastAPI (backend/app/api)  ->  services/  ->  db/ (SQLAlchemy)  ->  SQLite (dev) | PostgreSQL (deploy)
                                   |
                                   +--> interfaces.py   (Protocols only: storage, profiler, runner,
                                                         artifacts, tracker; implemented in later milestones)
ml_engine/  <- pure Python; MUST NOT import FastAPI/SQLAlchemy/MLflow (enforced by tests/test_architecture.py)
```

## Principles
* **Modular monolith.** One backend process; layers separated by import rules, not by network calls.
* **Environment-driven configuration** (`core/config.py`). Placeholders and weak secrets are rejected; failures print
  variable names and fixes, never values.
* **One database abstraction, two engines.** `db/session.py:build_engine` applies per-database safety (SQLite foreign keys ON,
  folder creation, cross-thread use). `UTCDateTime` makes timestamps timezone-aware UTC on both. Migrations use only portable constructs;
  `render_as_batch` is enabled for SQLite so future `ALTER TABLE` migrations work.
* **Ownership enforced in the service layer**: every project query filters by `owner_id`; foreign resources return 404.
* **Observability without leaks**: structured logs (text or JSON), request IDs, redaction in field names and message text.

## Preparing for later milestones
| Future capability | Integration point already in place |
|---|---|
| CSV upload + versions (M2) | `interfaces.ObjectStorage`; `projects` is the parent entity; sidebar/route `datasets` placeholder |
| Profiling (M3) | `interfaces.DatasetProfiler`; `ml_engine/` package |
| Experiments + reproducibility (M5-M6) | `interfaces.ExperimentSnapshot` (frozen config, **seed**, **dataset_version_id**, dataset SHA-256) and `ExperimentRunner` |
| Model artifacts (M6) | `interfaces.ArtifactStore` (load only artifacts the system wrote) |
| MLflow (M7) | `interfaces.ExperimentTracker` (one-way sink; the SQL database stays canonical) |
| What-If / DataTwin / Failure Intelligence | `extensions/{whatif,datatwin,failure}` empty packages + roadmap pages |
| Background jobs | planned `jobs` table + worker (M2), same interface later backed by SQS |
| Frontend features | new folder per feature under `src/features/`, page under `src/pages/`, route in `App.tsx`, nav entry in `lib/roadmap.ts` |

## Reproducibility plan (when experiments exist)
Every experiment will store: experiment ID, dataset version ID + SHA-256, preprocessing/split/evaluation config snapshot,
random seed, library versions and artifact URI. Models are selected on validation/cross-validation data only; the test set is
evaluated once. None of this is implemented yet; only the typed snapshot contract exists.
