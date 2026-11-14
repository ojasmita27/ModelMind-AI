# ModelMind AI Audit - Phase 1 & 2 Findings

## CRITICAL FINDINGS

### AUDIT-001: Database-Storage Path Mismatch (CRITICAL)
**Status:** VERIFIED
**Severity:** CRITICAL
**Evidence:**
- Database stores file paths as: `datasets/48739073-41bb-46c2-8f9f-119f69059a11/v1/hemoflow-execution-trace-tick-1792558665671.csv`
- Actual storage location: `data/uploads/datasets/1d19fad5-4284-40cd-b2f9-9a104c9f5525/v1/modelmind_customer_churn_sample.csv`
- Database shows 2 datasets with 2 versions
- Storage contains 34 dataset folders with different UUIDs
- Files referenced in database DO NOT exist at stored paths
**Impact:** Dataset files cannot be retrieved, experiments cannot be reproduced, data loss
**Root Cause:** LocalObjectStorage base_path configuration or file path storage inconsistency
**Files:** `backend/app/storage/local.py`, `backend/app/services/datasets.py`

### AUDIT-002: Scientific Incorrectness - Wrong Task Type for Targets (CRITICAL)
**Status:** VERIFIED
**Severity:** CRITICAL
**Evidence:**
- Experiments use `age` (56 unique values, continuous) as classification target
- Experiments use `tenure_months` (119 unique values, continuous) as classification target
- Experiments use `annual_income` (576 unique values, continuous) as classification target
- Only valid classification target is `churn` (2 unique values: Yes/No)
- 15 experiments in database, many using wrong task type
**Impact:** Invalid ML experiments, meaningless metrics, scientific invalidity
**Root Cause:** No validation that task type matches target column characteristics
**Files:** `backend/app/ml_engine/preprocessing.py`, `frontend/src/pages/ProjectExperiments.tsx`

### AUDIT-003: Missing Target Values Not Handled (CRITICAL)
**Status:** VERIFIED
**Severity:** CRITICAL
**Evidence:**
- `annual_income` column has 8 missing values (NaN)
- Experiments targeting `annual_income` fail with "Input y contains NaN"
- Error occurs despite preprocessing code claiming to remove missing targets
- 3 experiments failed with this error
**Impact:** Experiments fail, poor user experience, data loss
**Root Cause:** Preprocessing may not be removing missing target values before training
**Files:** `backend/app/ml_engine/preprocessing.py:split_frame()`, `backend/app/services/experiments.py`

### AUDIT-004: Near-Zero Metrics on Invalid Experiments (HIGH)
**Status:** VERIFIED
**Severity:** HIGH
**Evidence:**
- Classification on `age`: accuracy 0-5%, precision/recall/F1 ~0-0.02
- Classification on `tenure_months`: accuracy 0-4%, precision/recall/F1 ~0-0.02
- These are expected when treating continuous values as discrete classes
- Experiments marked as "completed" despite being scientifically invalid
**Impact:** Misleading results, wasted compute, invalid conclusions
**Root Cause:** No validation that task type is appropriate for target
**Files:** `backend/app/ml_engine/training.py`

### AUDIT-005: README Contradiction (MEDIUM)
**Status:** VERIFIED
**Severity:** MEDIUM
**Evidence:**
- README states: "ML features are on the roadmap and are **not implemented yet**"
- Reality: Full ML pipeline implemented (training.py, metrics.py, models.py, preprocessing.py)
- 15 experiments exist in database with metrics
- Experiment API router and service layer fully implemented
**Impact:** Misleading documentation, confusion about actual capabilities
**Files:** `README.md`, `backend/app/ml_engine/`, `backend/app/api/routers/experiments.py`

## DATABASE STATE

**Tables:** alembic_version, users, projects, datasets, dataset_versions, experiments
**Migration:** Current revision 0003 (latest)
**Users:** 1
**Projects:** 1
**Datasets:** 2 (abc, example)
**Dataset Versions:** 2 (both completed)
**Experiments:** 15 (11 completed, 3 failed, 1 unknown)

## EXPERIMENT ANALYSIS

**Completed Experiments with Wrong Targets:**
- 4 experiments targeting `age` (continuous) as classification
- 6 experiments targeting `tenure_months` (continuous) as classification
- 1 experiment targeting `annual_income` (continuous) as classification

**Failed Experiments:**
- 3 experiments targeting `annual_income` failed with "Input y contains NaN"

**Metrics Pattern:**
- Invalid experiments show near-zero metrics (0-5% accuracy)
- This is mathematically expected when treating 56-576 unique continuous values as discrete classes

## STORAGE INTEGRITY

**Database References:**
- `datasets/48739073-41bb-46c2-8f9f-119f69059a11/v1/hemoflow-execution-trace-tick-1792558665671.csv`
- `datasets/1d19fad5-4284-40cd-b2f9-9a104c9f5525/v1/modelmind_customer_churn_sample.csv`

**Actual Storage:**
- 34 dataset folders exist in `data/uploads/datasets/`
- Only 2 match database UUIDs
- Files at database paths DO NOT exist
- Files at actual storage paths DO exist

**Conclusion:** Database and storage are desynchronized. This is a data integrity crisis.

## DATASET CONTENT (Actual File)

**File:** `data/uploads/datasets/1d19fad5-4284-40cd-b2f9-9a104c9f5525/v1/modelmind_customer_churn_sample.csv`
**Shape:** 600 rows, 9 columns
**Columns:** age, annual_income, tenure_months, monthly_spend, support_tickets, contract_type, autopay, usage_hours_per_month, churn
**Missing Values:** annual_income (8), monthly_spend (8), usage_hours_per_month (8)
**Valid Classification Target:** churn (Yes/No, 352 No, 248 Yes)
**Valid Regression Targets:** age, tenure_months, annual_income, monthly_spend, usage_hours_per_month

## ARCHITECTURE INVENTORY

**Backend:**
- FastAPI 0.146.0, SQLAlchemy 2.0.55, Alembic 1.20.0
- Routers: auth, datasets, experiments, health, projects
- Services: auth, datasets, experiments, projects
- ML Engine: training, metrics, models, preprocessing
- Storage: LocalObjectStorage (local filesystem only)
- Jobs: In-memory single-thread queue
- Profiling: CSVProfiler

**Frontend:**
- React 19.3.1, TypeScript 7.0.2, Vite 8.3.5
- Pages: Landing, Login, Register, Dashboard, Projects, ProjectDetail, ProjectExperiments, Datasets, DatasetDetail, ComingSoon, NotFound
- Features: projects, datasets
- API Clients: auth, projects, datasets, experiments

**Database:**
- SQLite (development), PostgreSQL (production supported)
- Migrations: 0001 (users/projects), 0002 (datasets), 0003 (experiments)

**Deferred Features (Correctly Documented):**
- What-If Lab (empty extension)
- DataTwin (empty extension)
- Failure Intelligence (empty extension)
- MLflow integration (not implemented)
- S3 storage (not implemented)
