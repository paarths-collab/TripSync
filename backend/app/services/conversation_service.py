# backend/app/services/conversation_service.py

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional

from app.models import conversation_model, user_model
from app.services import connection_access

CHAT_FORBIDDEN_DETAIL = "Chat is only available with an approved ride partner"

def find_or_create_conversation(
    db: Session,
    user1_id: int,
    user2_id: int
) -> conversation_model.Conversation:
    """
    Find or create a conversation between two users.
    Ensures user1_id < user2_id for consistency (sorted user IDs).

    user1_id is the caller. Raises 400 for a self-chat, 404 for an unknown
    partner and 403 unless the two users share an active ride connection.
    """
    if user1_id == user2_id:
        raise HTTPException(status_code=400, detail="You cannot chat with yourself")

    partner = db.query(user_model.User).filter(user_model.User.id == user2_id).first()
    if partner is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not connection_access.users_have_active_ride(db, user1_id, user2_id):
        raise HTTPException(status_code=403, detail=CHAT_FORBIDDEN_DETAIL)

    # Sort user IDs to ensure consistency
    sorted_user1 = min(user1_id, user2_id)
    sorted_user2 = max(user1_id, user2_id)
    
    # Try to find existing conversation
    conversation = db.query(conversation_model.Conversation).filter(
        and_(
            conversation_model.Conversation.user1_id == sorted_user1,
            conversation_model.Conversation.user2_id == sorted_user2
        )
    ).first()
    
    if conversation:
        return conversation
    
    # Create new conversation
    conversation = conversation_model.Conversation(
        user1_id=sorted_user1,
        user2_id=sorted_user2
    )
    
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    
    return conversation


def get_conversation_by_id(
    db: Session,
    conversation_id: int
) -> Optional[conversation_model.Conversation]:
    """
    Get a conversation by ID.
    """
    return db.query(conversation_model.Conversation).filter(
        conversation_model.Conversation.id == conversation_id
    ).first()


def get_conversation_for_users(
    db: Session,
    user1_id: int,
    user2_id: int
) -> Optional[conversation_model.Conversation]:
    """
    Get conversation between two users (if exists).
    """
    sorted_user1 = min(user1_id, user2_id)
    sorted_user2 = max(user1_id, user2_id)
    
    return db.query(conversation_model.Conversation).filter(
        and_(
            conversation_model.Conversation.user1_id == sorted_user1,
            conversation_model.Conversation.user2_id == sorted_user2
        )
    ).first()


def get_user_conversations(
    db: Session,
    user_id: int
) -> list[conversation_model.Conversation]:
    """
    Get all conversations for a user.
    """
    return db.query(conversation_model.Conversation).filter(
        (conversation_model.Conversation.user1_id == user_id) |
        (conversation_model.Conversation.user2_id == user_id)
    ).all()

