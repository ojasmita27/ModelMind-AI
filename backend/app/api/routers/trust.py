"""Trust receipt endpoints."""
import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.services import trust as trust_service

router = APIRouter(prefix="/projects/{project_id}", tags=["trust"])


@router.post("/experiments/{experiment_id}/trust-receipt", status_code=201)
def generate_receipt(project_id: uuid.UUID, experiment_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return trust_service.generate_receipt(db, user.id, project_id, experiment_id)


@router.get("/experiments/{experiment_id}/trust-receipt")
def get_receipt(project_id: uuid.UUID, experiment_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return trust_service.get_receipt(db, user.id, project_id, experiment_id)


@router.get("/trust-receipts")
def list_receipts(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return trust_service.list_receipts(db, user.id, project_id)


@router.post("/trust-receipts/{receipt_id}/verify")
def verify_receipt(project_id: uuid.UUID, receipt_id: str, user: CurrentUser, db: DbSession):
    return trust_service.verify_receipt(db, user.id, project_id, receipt_id)


@router.get("/trust-receipts/{receipt_id}/reproducibility")
def reproducibility(project_id: uuid.UUID, receipt_id: str, user: CurrentUser, db: DbSession):
    return trust_service.reproducibility(db, user.id, project_id, receipt_id)
