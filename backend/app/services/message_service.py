# backend/app/services/message_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_
from typing import List
from fastapi import HTTPException
from datetime import datetime

from app.models import user_model, message_model, conversation_model
from app.schemas import message_schema
from app.services import conversation_service, connection_access

def create_message(
    db: Session,
    sender: user_model.User,
    message_data: message_schema.MessageCreate
) -> message_model.Message:
    """
    Create a new chat message.
    Finds or creates a conversation between the sender and receiver.
    Raises 400 (self), 404 (unknown receiver) or 403 (no active ride) via
    conversation_service.find_or_create_conversation.
    """
    # Get or create conversation between sender and receiver
    conversation = conversation_service.find_or_create_conversation(
        db=db,
        user1_id=sender.id,
        user2_id=message_data.receiver_id
    )
    
    # Verify sender is part of the conversation
    if conversation.user1_id != sender.id and conversation.user2_id != sender.id:
        raise HTTPException(status_code=403, detail="You are not part of this conversation")
    
    # Create message
    message = message_model.Message(
        conversation_id=conversation.id,
        sender_id=sender.id,
        content=message_data.content,
        created_at=datetime.utcnow()
    )
    
    db.add(message)
    db.commit()
    db.refresh(message)
    
    return message


def get_messages_for_conversation(
    db: Session,
    user: user_model.User,
    conversation_id: int,
    limit: int = 100
) -> List[message_model.Message]:
    """
    Get all messages for a conversation.
    Validates that the user is part of the conversation.
    """
    # Verify the conversation exists and user is part of it
    conversation = db.query(conversation_model.Conversation).filter(
        conversation_model.Conversation.id == conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Check if user is part of this conversation
    if conversation.user1_id != user.id and conversation.user2_id != user.id:
        raise HTTPException(status_code=403, detail="You are not part of this conversation")
    
    # Get messages
    messages = db.query(message_model.Message).options(
        joinedload(message_model.Message.sender)
    ).filter(
        message_model.Message.conversation_id == conversation_id
    ).order_by(
        message_model.Message.created_at.desc(),
        message_model.Message.id.desc()
    ).limit(limit).all()
    # Newest `limit` messages, returned oldest-first.
    messages.reverse()
    
    # Mark messages as read
    db.query(message_model.Message).filter(
        message_model.Message.conversation_id == conversation_id,
        message_model.Message.sender_id != user.id,
        message_model.Message.is_read == False
    ).update({"is_read": True})
    db.commit()
    
    return messages


def mark_messages_as_read(
    db: Session,
    user: user_model.User,
    conversation_id: int
) -> int:
    """
    Mark all messages from the other user as read.
    Returns the count of messages marked.
    Raises 404 if the conversation does not exist, 403 if the user is not in it.
    """
    conversation = db.query(conversation_model.Conversation).filter(
        conversation_model.Conversation.id == conversation_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.user1_id != user.id and conversation.user2_id != user.id:
        raise HTTPException(status_code=403, detail="You are not part of this conversation")

    count = db.query(message_model.Message).filter(
        message_model.Message.conversation_id == conversation_id,
        message_model.Message.sender_id != user.id,
        message_model.Message.is_read == False
    ).update({"is_read": True})
    db.commit()
    
    return count


def get_recent_conversations(
    db: Session,
    user: user_model.User
):
    """
    Get all recent conversations for a user with the last message and unread count.
    Returns conversations where user is involved with their latest message.
    """
    # Get all conversations for this user
    conversations = db.query(conversation_model.Conversation).options(
        joinedload(conversation_model.Conversation.user1).joinedload(user_model.User.profile),
        joinedload(conversation_model.Conversation.user2).joinedload(user_model.User.profile)
    ).filter(
        (conversation_model.Conversation.user1_id == user.id) |
        (conversation_model.Conversation.user2_id == user.id)
    ).all()

    # Contact details are only visible to partners on an active ride.
    active_partner_ids = connection_access.get_active_partner_ids(db, user.id)

    result = []
    for conv in conversations:
        # Get the partner (the other user in the conversation)
        if conv.user1_id == user.id:
            partner = conv.user2
        else:
            partner = conv.user1
        
        # Get last message for this conversation
        last_message = db.query(message_model.Message).filter(
            message_model.Message.conversation_id == conv.id
        ).order_by(
            message_model.Message.created_at.desc()
        ).first()
        
        # Count unread messages from partner
        unread_count = db.query(message_model.Message).filter(
            message_model.Message.conversation_id == conv.id,
            message_model.Message.sender_id == partner.id,
            message_model.Message.is_read == False
        ).count()
        
        can_see_details = partner.id in active_partner_ids
        profile = partner.profile if can_see_details else None

        result.append({
            "conversation_id": conv.id,
            "partner": {
                "id": partner.id,
                "full_name": partner.full_name,
                "phone_number": profile.phone_number if profile else None,
                "email": partner.email if can_see_details else None,
                "year_of_study": profile.year_of_study if profile else None,
                "bio": profile.bio if profile else None,
            },
            "last_message": {
                "content": last_message.content if last_message else None,
                "created_at": last_message.created_at.isoformat() if last_message else None,
                "sender_id": last_message.sender_id if last_message else None
            } if last_message else None,
            "unread_count": unread_count
        })
    
    # Sort by last message time (most recent first)
    result.sort(key=lambda x: x["last_message"]["created_at"] if x["last_message"] else "", reverse=True)
    
    return result
