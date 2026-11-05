# backend/app/routes/campus_party_router.py
"""Campus party router: /connections (+ accept/decline/withdraw), /parties/{id} (+ changes, note, report, cancel).

Mounted after campus_events_router, which owns the literal ``/parties/active``;
``{party_id}`` is an int so the literal can never be captured here.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import campus_schema as schemas
from app.services import auth_service, campus_idempotency, campus_party_service as svc

router = APIRouter()

# ids beyond a 32-bit INTEGER cannot exist: reject with 422 instead of a DB error
Id = Annotated[int, Path(ge=1, le=2_147_483_647)]


def _respond(result: svc.Result, status_code: int = 200) -> JSONResponse:
    headers = {campus_idempotency.REPLAY_HEADER: "true"} if result.replay else None
    return JSONResponse(status_code=status_code, content=result.body, headers=headers)


# ---------------------------------------------------------------- connections
@router.post("/suggestions/{suggestion_id}/connections", status_code=201)
async def create_connection(
    suggestion_id: Id,
    body: schemas.ConnectionCreate = schemas.ConnectionCreate(),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.create_proposal(db, current_user, suggestion_id, body), 201)


@router.get("/connections")
def list_connections(
    role: str = Query("all"),
    state: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return svc.list_proposals(db, current_user, role, state, limit)


@router.post("/connections/{connection_id}/accept")
async def accept_connection(
    connection_id: Id,
    body: schemas.ConnectionAccept,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.accept_proposal(db, current_user, connection_id, body))


@router.post("/connections/{connection_id}/decline")
async def decline_connection(
    connection_id: Id,
    body: schemas.ConnectionDecision = schemas.ConnectionDecision(),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.decline_proposal(db, current_user, connection_id, body))


@router.post("/connections/{connection_id}/withdraw")
async def withdraw_connection(
    connection_id: Id,
    body: schemas.ConnectionDecision = schemas.ConnectionDecision(),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.withdraw_proposal(db, current_user, connection_id, body))


# -------------------------------------------------------------------- parties
@router.get("/parties/{party_id}")
def get_party(
    party_id: Id,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return svc.get_party(db, current_user, party_id)


@router.post("/parties/{party_id}/cancel")
async def cancel_party(
    party_id: Id,
    body: schemas.PartyCancel,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.cancel_party(db, current_user, party_id, body))


@router.post("/parties/{party_id}/changes", status_code=201)
async def propose_change(
    party_id: Id,
    body: schemas.ChangeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.propose_change(db, current_user, party_id, body), 201)


@router.post("/parties/{party_id}/changes/{change_id}/approve")
async def approve_change(
    party_id: Id,
    change_id: Id,
    body: schemas.ChangeApprove,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.decide_change(
        db, current_user, party_id, change_id,
        action="approve", expected_party_version=body.expected_party_version,
    ))


@router.post("/parties/{party_id}/changes/{change_id}/reject")
async def reject_change(
    party_id: Id,
    change_id: Id,
    body: schemas.ChangeReject = schemas.ChangeReject(),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.decide_change(
        db, current_user, party_id, change_id,
        action="reject", expected_party_version=body.expected_party_version,
    ))


@router.post("/parties/{party_id}/changes/{change_id}/withdraw")
async def withdraw_change(
    party_id: Id,
    change_id: Id,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.decide_change(
        db, current_user, party_id, change_id, action="withdraw",
    ))


@router.patch("/parties/{party_id}")
async def patch_party(
    party_id: Id,
    body: schemas.PartyNotePatch,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.update_cost_note(db, current_user, party_id, body))


@router.post("/parties/{party_id}/report")
async def report_party(
    party_id: Id,
    body: schemas.ReportBody,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return _respond(await svc.report_outcome(db, current_user, party_id, body))
