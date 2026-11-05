# backend/app/routes/message_router.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.services import auth_service, message_service, conversation_service
from app.schemas import message_schema
from app.models import user_model

router = APIRouter()

@router.post("/messages", response_model=message_schema.Message)
async def send_message(
    message_data: message_schema.MessageCreate,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Send a chat message. Creates conversation if it doesn't exist.
    """
    message = message_service.create_message(
        db=db,
        sender=current_user,
        message_data=message_data
    )
    
    return message_schema.Message(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_name=current_user.full_name,
        content=message.content,
        created_at=message.created_at,
        is_read=message.is_read
    )


@router.get("/messages/{conversation_id}", response_model=message_schema.MessageListResponse)
async def get_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Get all messages for a conversation.
    """
    messages = message_service.get_messages_for_conversation(
        db=db,
        user=current_user,
        conversation_id=conversation_id
    )
    
    message_list = [
        message_schema.Message(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            sender_name=msg.sender.full_name,
            content=msg.content,
            created_at=msg.created_at,
            is_read=msg.is_read
        )
        for msg in messages
    ]
    
    return message_schema.MessageListResponse(messages=message_list)


@router.post("/messages/{conversation_id}/read")
async def mark_messages_read(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Mark all messages in a conversation as read.
    """
    count = message_service.mark_messages_as_read(
        db=db,
        user=current_user,
        conversation_id=conversation_id
    )
    
    return {"marked_read": count}


@router.get("/conversations")
async def get_recent_conversations(
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Get all recent conversations for the current user.
    Returns conversations with last message and unread count.
    """
    conversations = message_service.get_recent_conversations(
        db=db,
        user=current_user
    )
    
    return {"conversations": conversations}


@router.get("/conversations/find-or-create")
async def find_or_create_conversation(
    partner_id: int = Query(..., description="The ID of the user to chat with"),
    db: Session = Depends(get_db),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Find or create a conversation between current user and partner.
    Returns conversation_id. Only available between users who share an active
    ride (400 self, 404 unknown user, 403 otherwise).
    """
    conversation = conversation_service.find_or_create_conversation(
        db=db,
        user1_id=current_user.id,
        user2_id=partner_id
    )
    
    # Get partner info
    partner = conversation.user1 if conversation.user2_id == current_user.id else conversation.user2
    
    return {
        "conversation_id": conversation.id,
        "partner": {
            "id": partner.id,
            "full_name": partner.full_name,
            "email": partner.email,
        }
    }
