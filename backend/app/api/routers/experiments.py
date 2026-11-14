import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.api.schemas.experiments import (
    ArtifactOut,
    ExperimentCreate,
    ExperimentEvaluationOut,
    ExperimentOut,
    ModelResultOut,
    ReproducibilityOut,
)
from app.core.logging import get_logger, log_event
from app.services import experiments as experiment_service

router = APIRouter(prefix="/projects/{project_id}/experiments", tags=["experiments"])
log = get_logger("experiments")


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_experiment(
    project_id: uuid.UUID,
    body: ExperimentCreate,
    user: CurrentUser,
    db: DbSession,
):
    experiment = experiment_service.create_experiment(db, user.id, project_id, body.model_dump())
    log_event(log, "experiment_created", project_id=str(project_id), experiment_id=str(experiment.id), user_id=str(user.id))
    return experiment


@router.get("", response_model=list[ExperimentOut])
def list_experiments(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    experiments = experiment_service.list_experiments(db, user.id, project_id)
    return experiments[offset : offset + limit]


@router.get("/{experiment_id}", response_model=ExperimentOut)
def get_experiment(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
):
    return experiment_service.get_owned_experiment(db, user.id, project_id, experiment_id)


@router.delete("/{experiment_id}")
def delete_experiment(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
):
    cleanup = experiment_service.delete_experiment(db, user.id, project_id, experiment_id)
    return {"deleted": True, "artifact_cleanup": cleanup}


@router.get("/{experiment_id}/evaluation", response_model=ExperimentEvaluationOut)
def get_experiment_evaluation(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
):
    experiment, results = experiment_service.get_experiment_evaluation(
        db, user.id, project_id, experiment_id
    )
    metrics = experiment.metrics or {}
    return ExperimentEvaluationOut(
        experiment_id=experiment.id,
        status=experiment.status,
        task_type=experiment.task_type,
        target_column=experiment.target_column,
        best_model_name=metrics.get("best_model_name"),
        models=[ModelResultOut.model_validate(r) for r in results],
    )


@router.get("/{experiment_id}/reproducibility", response_model=ReproducibilityOut)
def get_experiment_reproducibility(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
):
    return ReproducibilityOut.model_validate(
        experiment_service.get_experiment_reproducibility(db, user.id, project_id, experiment_id)
    )


@router.get("/{experiment_id}/artifact", response_model=ArtifactOut)
def get_experiment_artifact(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
):
    return ArtifactOut.model_validate(
        experiment_service.get_experiment_artifact(db, user.id, project_id, experiment_id)
    )


# ---------------- What-If analysis ----------------

from pydantic import BaseModel, Field  # noqa: E402


class WhatIfPredictIn(BaseModel):
    features: dict


class WhatIfCounterfactualIn(BaseModel):
    features: dict
    goal: dict[str, Any] = Field(default_factory=dict)
    n_candidates: int = Field(default=3, ge=1, le=50)
    seed: int = Field(default=42, ge=0, le=999999)
    immutable: list[str] = Field(default_factory=list, max_length=100)


@router.get("/{experiment_id}/what-if/schema")
def get_whatif_schema(project_id: uuid.UUID, experiment_id: uuid.UUID, user: CurrentUser, db: DbSession):
    from app.services import whatif as whatif_service

    return whatif_service.get_whatif_schema(db, user.id, project_id, experiment_id)


@router.post("/{experiment_id}/what-if/predict")
def whatif_predict(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    body: WhatIfPredictIn,
    user: CurrentUser,
    db: DbSession,
):
    from app.services import whatif as whatif_service

    return whatif_service.predict_whatif(db, user.id, project_id, experiment_id, body.features)


@router.post("/{experiment_id}/what-if/counterfactual")
def whatif_counterfactual(
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    body: WhatIfCounterfactualIn,
    user: CurrentUser,
    db: DbSession,
):
    from app.services import whatif as whatif_service

    return whatif_service.generate_counterfactuals(
        db, user.id, project_id, experiment_id,
        body.features, body.goal,
        n_candidates=body.n_candidates, seed=body.seed, immutable=body.immutable,
    )
