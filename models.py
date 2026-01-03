from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class MessageStatus(str, Enum):
    """Message delivery status enum"""

    sent = "sent"
    delivered = "delivered"
    read = "read"


# SQLAlchemy Models (Database)
class ChatRoomDB(Base):
    """SQLAlchemy model for chat_rooms table"""

    __tablename__ = "chat_rooms"

    id = Column(Integer, primary_key=True, index=True)

    # Trade offer ID that created this chat room
    trade_offer_id = Column(Integer, nullable=False, unique=True, index=True)

    # Participants (user IDs)
    user1_id = Column(String(100), nullable=False, index=True)
    user2_id = Column(String(100), nullable=False, index=True)

    # Room metadata
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MessageDB(Base):
    """SQLAlchemy model for messages table"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    # Chat room reference
    chat_room_id = Column(
        Integer,
        ForeignKey("chat_rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Sender information
    sender_id = Column(String(100), nullable=False, index=True)

    # Message content
    content = Column(Text, nullable=False)

    # Message status
    status = Column(
        String(20), nullable=False, default=MessageStatus.sent.value, index=True
    )

    # Read timestamp
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# Pydantic Models (API)
class ChatRoomCreate(BaseModel):
    """Schema for creating a new chat room"""

    trade_offer_id: int = Field(..., description="ID of the accepted trade offer")
    user1_id: str = Field(..., description="First participant user ID")
    user2_id: str = Field(..., description="Second participant user ID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trade_offer_id": 123,
                "user1_id": "user_abc123",
                "user2_id": "user_xyz789",
            }
        }
    )


class ChatRoomResponse(BaseModel):
    """Schema for chat room response"""

    id: int
    trade_offer_id: int
    user1_id: str
    user2_id: str
    is_active: bool
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    """Schema for creating a new message"""

    chat_room_id: int = Field(..., description="ID of the chat room")
    sender_id: str = Field(..., description="ID of the user sending the message")
    content: str = Field(
        ..., min_length=1, max_length=5000, description="Message content"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "chat_room_id": 1,
                "sender_id": "user_abc123",
                "content": "Hi! When can we meet for the trade?",
            }
        }
    )


class MessageResponse(BaseModel):
    """Schema for message response"""

    id: int
    chat_room_id: int
    sender_id: str
    content: str
    status: MessageStatus
    read_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageUpdate(BaseModel):
    """Schema for updating a message (marking as read)"""

    status: Optional[MessageStatus] = None

    model_config = ConfigDict(json_schema_extra={"example": {"status": "read"}})


class ChatRoomWithLastMessage(BaseModel):
    """Schema for chat room with last message preview"""

    id: int
    trade_offer_id: int
    user1_id: str
    user2_id: str
    is_active: bool
    last_message_at: Optional[datetime] = None
    last_message_content: Optional[str] = None
    last_message_sender_id: Optional[str] = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatStatistics(BaseModel):
    """Schema for chat statistics"""

    total_rooms: int
    active_rooms: int
    total_messages: int
    total_unread_messages: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_rooms": 45,
                "active_rooms": 32,
                "total_messages": 1523,
                "total_unread_messages": 18,
            }
        }
    )


class ErrorResponse(BaseModel):
    """Schema for error responses"""

    detail: str

    model_config = ConfigDict(
        json_schema_extra={"example": {"detail": "Chat room not found"}}
    )
