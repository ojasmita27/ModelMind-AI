# Historical Experiment Recovery Report

## Scope and constraints

This report covers the 12 completed experiments identified in the artifact audit. The original database records and their historical metrics are intentionally preserved. No experiment record is overwritten, deleted, or re-run automatically.

The objective is to identify which experiments can be recovered by explicit rerun using their original dataset version and configuration, while keeping the historical record intact.

## Recovery eligibility

| Experiment ID | Status in audit | Data available for explicit rerun | Recovery eligibility | Notes |
|---|---|---|---|---|
| `b0a8aa0776664c7cb2d51a7ca023de0b` | completed, missing artifacts | Original dataset version and training config should still exist in the DB if the project dataset is unchanged | Eligible for manual rerun | Historical metrics preserved; do not overwrite |
| `20b5ab37f8d645bd9aebdfa59284a329` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `b2ff2f611b6644e79131b31fe146240c` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `bcc8f6331dea4e6597b03b70293f80f0` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `d676c7e5c4d64a9fbf37c46b39a30b3e` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `815e58a8d7994982afbb96a5bf865bf4` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `38e76837e0974478b300dff61dc5aafe` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `f760efbb8d2e47209f966cd7ee573a2d` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `6ded3fc4215e4732b571000b292d67a8` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `9586734d8bb6451cb07455b34020239c` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `b8cc2390c55f4b1d9499bc9c44ed995a` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |
| `e39e21ddeab241868943a26aa912fed4` | completed, missing artifacts | Same as above | Eligible for manual rerun | Historical metrics preserved; no automatic rerun |

## Recovery decision

- All 12 historical experiments are preserved as historical records.
- None of the records should be overwritten or deleted by this task.
- All 12 are considered eligible for explicit rerun if the original dataset version and experiment configuration remain available in the database.
- None are auto-rerun by this patch.
- Recovery should happen only through a deliberate operator action that reuses the original dataset version, target column, task type, split ratios, seed, and selected model list.

## Configuration availability

The database still holds the information required to rerun the experiments:

- `dataset_id`
- `dataset_version_id`
- `target_column`
- `task_type`
- `train_fraction`, `validation_fraction`, `test_fraction`
- `random_seed`
- `model_names`

This information is sufficient for a manual recovery workflow. The current patch does not create or restore model binaries, because the audit explicitly required that historical artifacts remain untouched and not be fabricated.

## Operational guidance

1. Validate the original dataset version still exists on disk for each experiment.
2. Confirm the original project and dataset records still exist and match the experiment.
3. Recreate a fresh experiment run with the same settings, using the original dataset version.
4. Compare the rerun metrics to the historical metrics as a sanity check.
5. Keep the original experiment row as the historical record and treat the rerun as a separate recovery artifact, not a mutation of the original record.

## Risk note

These records are not automatically recoverable as a binary artifact because the original model files were never persisted. The safe path is explicit manual rerun using the saved configuration, without changing the historical database state.
