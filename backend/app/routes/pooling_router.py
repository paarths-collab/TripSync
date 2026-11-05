# backend/app/routes/pooling_router.py

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional

from app.db.database import get_db
from app.services import pooling_service, auth_service
from app.schemas import pooling_schema
from app.models import user_model, pooling_model

router = APIRouter()
logger = logging.getLogger(__name__)

def _serialize_connection(connection, user_id: int):
    """Shape shared by GET /connections/active and GET /requests/current."""
    if not connection:
        return None

    # Determine who is the partner and get user's own request ID
    if connection.sender_request.user_id == user_id:
        partner = connection.receiver_request.user
        partner_request_id = connection.receiver_request_id
        user_request_id = connection.sender_request_id
    else:
        partner = connection.sender_request.user
        partner_request_id = connection.sender_request_id
        user_request_id = connection.receiver_request_id

    return {
        "id": connection.id,
        "status": connection.status,
        "created_at": connection.created_at,
        "user_request_id": user_request_id,
        "partner": {
            "id": partner.id,
            "full_name": partner.full_name,
            "phone_number": partner.profile.phone_number if partner.profile else None,
            "email": partner.email,
            "year_of_study": partner.profile.year_of_study if partner.profile else None,
            "bio": partner.profile.bio if partner.profile else None,
            "request_id": partner_request_id,
        },
    }


@router.post("/requests", response_model=pooling_schema.PoolingMatchResponse)
async def create_pooling_request_and_find_matches(
    request_data: pooling_schema.PoolingRequestCreate,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    This single endpoint does two things:
    1. Creates a new pooling request for the current user (cancelling any old ones).
    2. Immediately searches for and returns any available matches.
    """
    # Step 1: Create the user's request
    new_request = await pooling_service.create_or_update_pooling_request(
        db=db, user=current_user, request_data=request_data
    )
    
    # Step 2: Find matches for this new request (returns list of matched requests).
    # Provider failures are explicit errors, never an empty (200) match list.
    try:
        matched_requests = await pooling_service.find_matches(db=db, new_request=new_request)
    except pooling_service.MatchingProviderTimeout:
        raise HTTPException(status_code=504, detail="Matching service timed out. Please try again.")
    except pooling_service.MatchingProviderError:
        raise HTTPException(status_code=502, detail="Matching service is unavailable. Please try again.")
    
    # Step 3: Convert to MatchedUser schema with request_id and connection info
    matched_users = []
    for matched_req in matched_requests:
        # Check if there's an existing connection
        existing_connection = db.query(pooling_model.PoolingConnection).filter(
            or_(
                and_(
                    pooling_model.PoolingConnection.sender_request_id == new_request.id,
                    pooling_model.PoolingConnection.receiver_request_id == matched_req.id
                ),
                and_(
                    pooling_model.PoolingConnection.sender_request_id == matched_req.id,
                    pooling_model.PoolingConnection.receiver_request_id == new_request.id
                )
            )
        ).order_by(pooling_model.PoolingConnection.id.desc()).first()
        
        connection_status = 'none'
        connection_id = None
        
        if existing_connection:
            connection_id = existing_connection.id
            if existing_connection.status == pooling_model.PoolingConnectionStatus.PENDING:
                # Determine if we sent or received
                if existing_connection.sender_request_id == new_request.id:
                    connection_status = 'pending_sent'
                else:
                    connection_status = 'pending_received'
            elif existing_connection.status == pooling_model.PoolingConnectionStatus.APPROVED:
                connection_status = 'approved'
            elif existing_connection.status == pooling_model.PoolingConnectionStatus.REJECTED:
                connection_status = 'rejected'
        
        matched_user = pooling_schema.MatchedUser(
            id=matched_req.user.id,
            full_name=matched_req.user.full_name,
            phone_number=None if connection_status != 'approved' else (matched_req.user.profile.phone_number if matched_req.user.profile else None),
            email=None if connection_status != 'approved' else matched_req.user.email,
            year_of_study=None if connection_status != 'approved' else (matched_req.user.profile.year_of_study if matched_req.user.profile else None),
            bio=None if connection_status != 'approved' else (matched_req.user.profile.bio if matched_req.user.profile else None),
            profile_image_url=None,
            request_id=matched_req.id,
            connection_status=connection_status,
            connection_id=connection_id
        )
        matched_users.append(matched_user)
    
    return pooling_schema.PoolingMatchResponse(
        request_id=new_request.id,
        matches=matched_users
    )


@router.post("/connections/send")
async def send_connection_request(
    connection_data: pooling_schema.ConnectionRequest,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Send a connection request to another user's pooling request.
    """
    # Sender's newest open (ACTIVE/MATCHED) request
    sender_request = db.query(pooling_model.PoolingRequest).filter(
        pooling_model.PoolingRequest.user_id == current_user.id,
        pooling_model.PoolingRequest.status.in_([
            pooling_model.PoolingRequestStatus.ACTIVE,
            pooling_model.PoolingRequestStatus.MATCHED
        ])
    ).order_by(
        pooling_model.PoolingRequest.created_at.desc(),
        pooling_model.PoolingRequest.id.desc(),
    ).first()
    
    if not sender_request:
        has_ride = db.query(pooling_model.PoolingRequest.id).filter(
            pooling_model.PoolingRequest.user_id == current_user.id,
            pooling_model.PoolingRequest.status == pooling_model.PoolingRequestStatus.CONNECTED,
        ).first()
        if has_ride:
            raise HTTPException(status_code=409, detail="You already have an active ride")
        raise HTTPException(status_code=404, detail="No active pooling request found")
    
    connection = await pooling_service.send_connection_request(
        db=db,
        sender_request_id=sender_request.id,
        receiver_request_id=connection_data.target_request_id,
        sender_user=current_user
    )
    
    return {
        "message": "Connection request sent",
        "connection_id": connection.id,
        "status": connection.status
    }


@router.post("/connections/{connection_id}/respond")
async def respond_to_connection_request(
    connection_id: int,
    response_data: pooling_schema.ConnectionResponse,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Approve or reject a connection request.
    """
    connection = await pooling_service.respond_to_connection(
        db=db,
        connection_id=connection_id,
        action=response_data.action,
        responder_user=current_user
    )
    
    return {
        "message": f"Connection {response_data.action}ed",
        "connection_id": connection.id,
        "status": connection.status
    }


@router.get("/connections/active")
async def get_active_connection(
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Get the currently active (approved) connection for the user.
    Returns full details including partner information.
    """
    return {"connection": _serialize_connection(
        pooling_service.get_active_connection(db=db, user_id=current_user.id),
        current_user.id,
    )}


@router.get("/requests/current")
async def get_current_request(
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Recovery endpoint: the caller's most recent request, its active connection (if
    any) and whether the ride has ended (latest request CANCELLED after having an
    APPROVED connection), for clients that missed a WebSocket event.
    """
    latest = pooling_service.get_latest_request(db=db, user_id=current_user.id)
    if latest is None:
        return {"request": None, "connection": None, "ride_ended": False}

    connection = None
    if latest.status == pooling_model.PoolingRequestStatus.CONNECTED:
        connection = pooling_service.get_active_connection(db=db, user_id=current_user.id)

    ride_ended = (
        latest.status == pooling_model.PoolingRequestStatus.CANCELLED
        and pooling_service.request_has_approved_connection(db=db, request_id=latest.id)
    )

    return {
        "request": {
            "id": latest.id,
            "status": latest.status,
            "destination_name": latest.destination_name,
            "created_at": latest.created_at,
        },
        "connection": _serialize_connection(connection, current_user.id),
        "ride_ended": ride_ended,
    }


@router.delete("/requests/{request_id}")
async def cancel_pooling_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Cancel a pooling request and notify any connected partners.
    """
    result = await pooling_service.cancel_pooling_request(
        db=db,
        request_id=request_id,
        user=current_user
    )
    return result