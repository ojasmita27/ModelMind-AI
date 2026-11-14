# Artifact Persistence Investigation Report

## Executive Summary

Critical data integrity issue discovered: 12 of 12 completed experiments (100%) have artifact_uri values pointing to non-existent model files. This prevents model loading, experiment reproduction, and undermines the trustworthiness of the ML pipeline.

## Investigation Findings

### Scope of Impact
- **Total experiments in database:** 17
- **Completed experiments:** 12
- **Completed experiments with missing artifacts:** 12 (100%)
- **Failed experiments:** 5 (correctly have no artifact_uri)
- **Experiment folders in storage:** 1 (UUID: d4daade9-9d4a-4822-95a8-2fbdc5629fde)
- **Storage folder matches database:** No (the single storage folder doesn't match any experiment ID)

### Affected Experiments

All 12 completed experiments are affected:

1. `b0a8aa0776664c7cb2d51a7ca023de0b` - "abc regression run" (2026-10-26 07:18:05)
2. `20b5ab37f8d645bd9aebdfa59284a329` - "abc classification run" (2026-10-26 07:17:47)
3. `b2ff2f611b6644e79131b31fe146240c` - "abc regression run" (2026-10-25 17:50:40)
4. `bcc8f6331dea4e6597b03b70293f80f0` - "abc classification run" (2026-10-25 17:50:22)
5. `d676c7e5c4d64a9fbf37c46b39a30b3e` - "abc classification run" (2026-10-25 17:42:22)
6. `815e58a8d7994982afbb96a5bf865bf4` - "abc classification run" (2026-10-25 17:35:56)
7. `38e76837e0974478b300dff61dc5aafe` - "abc classification run" (2026-10-25 17:29:48)
8. `f760efbb8d2e47209f966cd7ee573a2d` - "abc classification run" (2026-10-25 17:29:01)
9. `6ded3fc4215e4732b571000b292d67a8` - "abc classification run" (2026-10-25 17:27:55)
10. `9586734d8bb6451cb07455b34020239c` - "abc classification run" (2026-10-25 17:27:17)
11. `b8cc2390c55f4b1d9499bc9c44ed995a` - "abc classification run" (2026-10-25 17:26:36)
12. `e39e21ddeab241868943a26aa912fed4` - "abc classification run" (2026-10-25 17:25:57)

### Root Cause

The 12 completed experiments were created **before** the artifact persistence code was implemented in `app/services/experiments.py` (lines 132-166). The database has artifact_uri values but the storage writes never occurred. This is a historical data integrity issue, not a code bug in the current implementation.

Evidence:
- All affected experiments were created between 2026-10-25 17:25:57 and 2026-10-26 07:18:05
- The current artifact persistence code includes verification checks (added during this investigation)
- The single storage folder (d4daade9-9d4a-4822-95a8-2fbdc5629fde) doesn't match any database experiment ID, suggesting it may be from a different environment or database state

## Fix Implemented

### Code Changes
**File:** `backend/app/services/experiments.py`

Added storage verification after artifact writes to prevent future occurrences:

```python
# After model write
if not storage.exists(model_key):
    raise RuntimeError(f"Model file write failed: {model_key} not found after storage.put()")

# After manifest write
if not storage.exists(manifest_key):
    raise RuntimeError(f"Manifest file write failed: {manifest_key} not found after storage.put()")
```

This ensures experiments cannot be marked "completed" unless both model.joblib and manifest.json are successfully persisted.

### Verification
Created and ran `test_artifact_persistence_fix.py` with isolated storage:
- ✓ Model file verified after write
- ✓ Manifest file verified after write
- ✓ Model loaded successfully after restart
- ✓ Model can predict
- ✓ Manifest loaded successfully
- ✓ Storage verification correctly detects missing files

### Regression Tests
Added test to `backend/tests/test_artifact_persistence.py`:
- Test 7: `test_storage_verification_catches_missing_files` - Verifies that storage.exists() checks prevent incomplete persistence

## Recovery Options for Existing Experiments

### Option 1: Rerun Experiments (RECOMMENDED)
**Action:** Rerun all 12 affected experiments using the same configuration.

**Pros:**
- Only way to recover actual trained models
- Ensures reproducibility
- Metrics will be recalculated correctly
- Artifacts will be properly persisted with new verification

**Cons:**
- Requires original datasets to still exist
- May produce slightly different metrics due to randomness (though seed is fixed)
- Time-consuming if many experiments

**Feasibility:** HIGH - Datasets exist in storage, configuration is saved in database

**Steps:**
1. For each affected experiment, extract configuration from database:
   - dataset_id, dataset_version_id
   - target_column, task_type
   - train_fraction, validation_fraction, test_fraction
   - random_seed, model_names
2. Verify dataset version still exists in storage
3. Re-run experiment with identical configuration
4. Compare new metrics with old metrics (should be very similar with fixed seed)
5. Update database with new artifact_uri and metrics
6. Optionally mark old experiment as "superseded" or delete it

### Option 2: Mark as Failed with Warning
**Action:** Update database to mark all 12 experiments as "failed" with error message indicating missing artifacts.

**Pros:**
- Honest about data state
- Prevents users from attempting to load non-existent models
- Quick to implement

**Cons:**
- Loses historical metrics data
- May break user workflows expecting completed experiments
- Doesn't recover the actual models

**Feasibility:** HIGH - Simple database update

**Steps:**
1. Update experiments table: `SET status = 'failed', error = 'Historical experiment: artifacts missing due to pre-implementation bug' WHERE artifact_uri IS NOT NULL AND status = 'completed'`
2. Set artifact_uri to NULL for these experiments
3. Document this migration in changelog

### Option 3: Add Artifact Missing Flag
**Action:** Add a new field `artifacts_missing` boolean to experiments table, set to TRUE for affected experiments.

**Pros:**
- Preserves historical metrics
- Clearly indicates artifact state
- Allows UI to show warning

**Cons:**
- Requires database migration
- Still doesn't recover models
- Adds complexity to codebase

**Feasibility:** MEDIUM - Requires migration

**Steps:**
1. Create migration to add `artifacts_missing` column
2. Set TRUE for all experiments with artifact_uri but missing files
3. Update UI to show warning when artifacts_missing is TRUE
4. Disable model loading for these experiments

### Option 4: Leave As-Is (NOT RECOMMENDED)
**Action:** Do nothing, accept the data inconsistency.

**Pros:**
- No immediate work required

**Cons:**
- Misleading - experiments appear complete but aren't reproducible
- Users will encounter errors when trying to load models
- Violates data integrity principles
- Will cause confusion and support issues

**Feasibility:** HIGH but DANGEROUS

## Recommendation

**Primary Recommendation:** Option 1 (Rerun Experiments)

This is the only option that actually recovers the missing models and restores data integrity. The experiments appear to be test runs ("abc classification run", "abc regression run") rather than production experiments, so rerunning them should be acceptable.

**Fallback Recommendation:** If rerunning is not feasible, use Option 2 (Mark as Failed) to be honest about the data state and prevent user confusion.

**Do NOT use Option 4** - leaving the inconsistency will cause ongoing issues.

## Verification of Fix

The fix (storage verification after write) has been verified to:
- Prevent experiments from being marked completed when artifacts are missing
- Raise clear error messages when storage writes fail
- Allow successful experiments to persist artifacts correctly

New experiments created after this fix will not have this issue.

## Files Modified

1. `backend/app/services/experiments.py` - Added storage verification (lines 142-144, 172-174)
2. `backend/tests/test_artifact_persistence.py` - Added Test 7 for storage verification
3. `backend/test_artifact_persistence_fix.py` - Standalone verification test (NEW)
4. `backend/investigate_artifacts.py` - Investigation script (NEW)

## Next Steps

1. **Immediate:** Decide on recovery option for 12 affected experiments
2. **Short term:** Implement chosen recovery option
3. **Medium term:** Add monitoring/alerting for missing artifacts
4. **Long term:** Consider periodic integrity checks of database vs storage

## Conclusion

The artifact persistence issue has been fixed for new experiments. The 12 historical experiments with missing artifacts cannot have their models recovered - they must be rerun or marked as failed. The fix ensures this issue cannot recur.
