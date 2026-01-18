# test pre commit hook

import time
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from database import get_db, init_db

# Import HTTP resilience utilities
from http_client import send_notification_with_retry
from metrics import record_http_request
from models import (
    ChatRoomCreate,
    ChatRoomDB,
    ChatRoomResponse,
    ChatRoomWithLastMessage,
    ChatStatistics,
    ErrorResponse,
    MessageCreate,
    MessageDB,
    MessageResponse,
    MessageStatus,
    MessageUpdate,
)

# Notification service URL
NOTIFICATION_SERVICE_URL = "http://notifications_service:8000"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup: Initialize database
    init_db()
    yield
    # Shutdown: Cleanup if needed
    pass


# Initialize FastAPI app
app = FastAPI(
    title="Swappo Chat Service",
    description="""## Real-time Messaging API

**Swappo Chat Service** enables communication between users with accepted trades.

### Features
- Real-time messaging between matched users
- Chat room management (auto-created on trade acceptance)
- Message CRUD operations
- Read receipts and message status tracking
- Push notifications on new messages
- Chat statistics and analytics

### Chat Workflow
1. Chat room created automatically when trade accepted
2. Send messages at `/api/v1/chat-rooms/{room_id}/messages`
3. Recipients receive push notification
4. Fetch conversation history with pagination
5. Mark messages as read for read receipts

### Resilience
- Retry logic for notification delivery (3 attempts)
- Messages saved even if notifications fail
    """,
    version="1.0.0",
    contact={
        "name": "Swappo API Support",
        "url": "https://swappo.art",
        "email": "api@swappo.art",
    },
    license_info={
        "name": "MIT",
    },
    openapi_tags=[
        {"name": "Health", "description": "Service health and status endpoints"},
        {"name": "Chat Rooms", "description": "Chat room creation and management"},
        {"name": "Messages", "description": "Send and retrieve messages"},
        {"name": "Statistics", "description": "Chat analytics and metrics"},
    ],
    root_path="/chat",  # Fix for Kong reverse proxy - enables correct OpenAPI schema URLs
    lifespan=lifespan,
)

# Prometheus instrumentation
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# Middleware to track HTTP request metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    record_http_request(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
        duration=duration,
    )

    return response


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def send_message_notification(message: MessageDB, recipient_id: str):
    """
    Send notification when a new message is received (with retry).

    Args:
        message: The message that was sent
        recipient_id: The user ID of the recipient
    """
    notification_data = {
        "user_id": recipient_id,
        "type": "new_message",
        "title": "New Message 💬",
        "body": "You have a new message",
        "related_user_id": message.sender_id,
    }

    print(
        f"📤 Attempting to send notification to user {recipient_id} for message {message.id}"
    )

    # Send notification with retry logic
    await send_notification_with_retry(
        f"{NOTIFICATION_SERVICE_URL}/api/v1/notifications", notification_data
    )


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {"service": "Swappo Chat Service", "status": "running", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check endpoint"""
    from datetime import datetime

    return {
        "service": "Swappo Chat Service",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }


# ==================== Chat Room Endpoints ====================


@app.post(
    "/api/v1/chat-rooms",
    response_model=ChatRoomResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Chat Rooms"],
    responses={
        201: {"description": "Chat room created successfully"},
        400: {
            "model": ErrorResponse,
            "description": "Bad request - Chat room already exists for this trade offer",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def create_chat_room(chat_room: ChatRoomCreate, db: Session = Depends(get_db)):
    """
    Create a new chat room for an accepted trade offer.

    A chat room is created when two users accept a trade offer, allowing them to communicate.
    Each trade offer can only have one chat room.
    """
    # Check if chat room already exists for this trade offer
    existing_room = (
        db.query(ChatRoomDB)
        .filter(ChatRoomDB.trade_offer_id == chat_room.trade_offer_id)
        .first()
    )

    if existing_room:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chat room already exists for trade offer {chat_room.trade_offer_id}",
        )

    # Create new chat room
    db_chat_room = ChatRoomDB(
        trade_offer_id=chat_room.trade_offer_id,
        user1_id=chat_room.user1_id,
        user2_id=chat_room.user2_id,
        is_active=True,
    )

    db.add(db_chat_room)
    db.commit()
    db.refresh(db_chat_room)

    return db_chat_room


@app.get(
    "/api/v1/chat-rooms",
    response_model=List[ChatRoomWithLastMessage],
    tags=["Chat Rooms"],
    responses={
        200: {"description": "List of chat rooms retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_chat_rooms(
    user_id: str = Query(..., description="ID of the user to get chat rooms for"),
    active_only: bool = Query(True, description="Filter for active chat rooms only"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        50, ge=1, le=100, description="Maximum number of records to return"
    ),
    db: Session = Depends(get_db),
):
    """
    List all chat rooms for a specific user.

    Returns chat rooms with last message preview and unread message count.
    """
    # Base query - get rooms where user is a participant
    query = db.query(ChatRoomDB).filter(
        or_(ChatRoomDB.user1_id == user_id, ChatRoomDB.user2_id == user_id)
    )

    if active_only:
        query = query.filter(ChatRoomDB.is_active.is_(True))

    # Order by last message timestamp (most recent first)
    query = query.order_by(desc(ChatRoomDB.last_message_at))

    # Apply pagination
    chat_rooms = query.offset(skip).limit(limit).all()

    # Enrich with last message and unread count
    result = []
    for room in chat_rooms:
        # Get last message
        last_message = (
            db.query(MessageDB)
            .filter(MessageDB.chat_room_id == room.id)
            .order_by(desc(MessageDB.created_at))
            .first()
        )

        # Count unread messages for this user
        unread_count = (
            db.query(func.count(MessageDB.id))
            .filter(
                and_(
                    MessageDB.chat_room_id == room.id,
                    MessageDB.sender_id != user_id,
                    MessageDB.status != MessageStatus.read.value,
                )
            )
            .scalar()
        )

        room_data = ChatRoomWithLastMessage(
            id=room.id,
            trade_offer_id=room.trade_offer_id,
            user1_id=room.user1_id,
            user2_id=room.user2_id,
            is_active=room.is_active,
            last_message_at=room.last_message_at,
            last_message_content=last_message.content if last_message else None,
            last_message_sender_id=last_message.sender_id if last_message else None,
            unread_count=unread_count or 0,
            created_at=room.created_at,
            updated_at=room.updated_at,
        )
        result.append(room_data)

    return result


@app.get(
    "/api/v1/chat-rooms/{chat_room_id}",
    response_model=ChatRoomResponse,
    tags=["Chat Rooms"],
    responses={
        200: {"description": "Chat room retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Chat room not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_chat_room(chat_room_id: int, db: Session = Depends(get_db)):
    """
    Get details of a specific chat room by ID.
    """
    chat_room = db.query(ChatRoomDB).filter(ChatRoomDB.id == chat_room_id).first()

    if not chat_room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat room {chat_room_id} not found",
        )

    return chat_room


@app.get(
    "/api/v1/chat-rooms/trade-offer/{trade_offer_id}",
    response_model=ChatRoomResponse,
    tags=["Chat Rooms"],
    responses={
        200: {"description": "Chat room retrieved successfully"},
        404: {
            "model": ErrorResponse,
            "description": "Chat room not found for this trade offer",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_chat_room_by_trade_offer(
    trade_offer_id: int, db: Session = Depends(get_db)
):
    """
    Get chat room for a specific trade offer.
    """
    chat_room = (
        db.query(ChatRoomDB).filter(ChatRoomDB.trade_offer_id == trade_offer_id).first()
    )

    if not chat_room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat room not found for trade offer {trade_offer_id}",
        )

    return chat_room


@app.patch(
    "/api/v1/chat-rooms/{chat_room_id}/deactivate",
    response_model=ChatRoomResponse,
    tags=["Chat Rooms"],
    responses={
        200: {"description": "Chat room deactivated successfully"},
        404: {"model": ErrorResponse, "description": "Chat room not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def deactivate_chat_room(chat_room_id: int, db: Session = Depends(get_db)):
    """
    Deactivate a chat room (soft delete).

    Useful when a trade is completed or cancelled.
    """
    chat_room = db.query(ChatRoomDB).filter(ChatRoomDB.id == chat_room_id).first()

    if not chat_room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat room {chat_room_id} not found",
        )

    chat_room.is_active = False
    db.commit()
    db.refresh(chat_room)

    return chat_room


# ==================== Message Endpoints ====================


@app.post(
    "/api/v1/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Messages"],
    responses={
        201: {"description": "Message sent successfully"},
        400: {
            "model": ErrorResponse,
            "description": "Bad request - Invalid chat room or sender",
        },
        404: {"model": ErrorResponse, "description": "Chat room not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def send_message(message: MessageCreate, db: Session = Depends(get_db)):
    """
    Send a new message in a chat room.

    The sender must be a participant in the chat room.
    """
    # Verify chat room exists and is active
    chat_room = (
        db.query(ChatRoomDB).filter(ChatRoomDB.id == message.chat_room_id).first()
    )

    if not chat_room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat room {message.chat_room_id} not found",
        )

    if not chat_room.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chat room {message.chat_room_id} is not active",
        )

    # Verify sender is a participant
    if message.sender_id not in [chat_room.user1_id, chat_room.user2_id]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sender is not a participant in this chat room",
        )

    # Create message
    db_message = MessageDB(
        chat_room_id=message.chat_room_id,
        sender_id=message.sender_id,
        content=message.content,
        status=MessageStatus.sent.value,
    )

    db.add(db_message)

    # Update chat room's last_message_at timestamp
    chat_room.last_message_at = func.now()

    db.commit()
    db.refresh(db_message)

    # Send notification to recipient
    recipient_id = (
        chat_room.user2_id
        if message.sender_id == chat_room.user1_id
        else chat_room.user1_id
    )
    await send_message_notification(db_message, recipient_id)

    return db_message


@app.get(
    "/api/v1/messages",
    response_model=List[MessageResponse],
    tags=["Messages"],
    responses={
        200: {"description": "Messages retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Chat room not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def list_messages(
    chat_room_id: int = Query(..., description="ID of the chat room"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        100, ge=1, le=500, description="Maximum number of records to return"
    ),
    db: Session = Depends(get_db),
):
    """
    List all messages in a chat room.

    Messages are ordered by creation time (oldest first) for chat display.
    """
    # Verify chat room exists
    chat_room = db.query(ChatRoomDB).filter(ChatRoomDB.id == chat_room_id).first()

    if not chat_room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat room {chat_room_id} not found",
        )

    # Get messages
    messages = (
        db.query(MessageDB)
        .filter(MessageDB.chat_room_id == chat_room_id)
        .order_by(MessageDB.created_at)
        .offset(skip)
        .limit(limit)
        .all()
    )

    return messages


@app.get(
    "/api/v1/messages/{message_id}",
    response_model=MessageResponse,
    tags=["Messages"],
    responses={
        200: {"description": "Message retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Message not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_message(message_id: int, db: Session = Depends(get_db)):
    """
    Get a specific message by ID.
    """
    message = db.query(MessageDB).filter(MessageDB.id == message_id).first()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )

    return message


@app.patch(
    "/api/v1/messages/{message_id}",
    response_model=MessageResponse,
    tags=["Messages"],
    responses={
        200: {"description": "Message updated successfully"},
        404: {"model": ErrorResponse, "description": "Message not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def update_message(
    message_id: int, message_update: MessageUpdate, db: Session = Depends(get_db)
):
    """
    Update a message (typically to mark as read).
    """
    message = db.query(MessageDB).filter(MessageDB.id == message_id).first()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )

    # Update status if provided
    if message_update.status:
        message.status = message_update.status.value
        if message_update.status == MessageStatus.read and not message.read_at:
            message.read_at = func.now()

    db.commit()
    db.refresh(message)

    return message


@app.patch(
    "/api/v1/messages/mark-read",
    status_code=status.HTTP_200_OK,
    tags=["Messages"],
    responses={
        200: {"description": "Messages marked as read successfully"},
        404: {"model": ErrorResponse, "description": "Chat room not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def mark_messages_as_read(
    chat_room_id: int = Query(..., description="ID of the chat room"),
    user_id: str = Query(..., description="ID of the user marking messages as read"),
    db: Session = Depends(get_db),
):
    """
    Mark all messages in a chat room as read for a specific user.

    This marks all messages sent by the other participant as read.
    """
    # Verify chat room exists
    chat_room = db.query(ChatRoomDB).filter(ChatRoomDB.id == chat_room_id).first()

    if not chat_room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat room {chat_room_id} not found",
        )

    # Verify user is a participant
    if user_id not in [chat_room.user1_id, chat_room.user2_id]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a participant in this chat room",
        )

    # Update all unread messages from the other participant
    updated_count = (
        db.query(MessageDB)
        .filter(
            and_(
                MessageDB.chat_room_id == chat_room_id,
                MessageDB.sender_id != user_id,
                MessageDB.status != MessageStatus.read.value,
            )
        )
        .update({"status": MessageStatus.read.value, "read_at": func.now()})
    )

    db.commit()

    return {"message": "Messages marked as read", "updated_count": updated_count}


# ==================== Statistics Endpoints ====================


@app.get(
    "/api/v1/statistics",
    response_model=ChatStatistics,
    tags=["Statistics"],
    responses={
        200: {"description": "Statistics retrieved successfully"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def get_statistics(
    user_id: Optional[str] = Query(None, description="Filter statistics by user ID"),
    db: Session = Depends(get_db),
):
    """
    Get chat statistics.

    If user_id is provided, returns statistics for that user only.
    Otherwise, returns global statistics.
    """
    if user_id:
        # User-specific statistics
        total_rooms = (
            db.query(func.count(ChatRoomDB.id))
            .filter(or_(ChatRoomDB.user1_id == user_id, ChatRoomDB.user2_id == user_id))
            .scalar()
        )

        active_rooms = (
            db.query(func.count(ChatRoomDB.id))
            .filter(
                and_(
                    or_(ChatRoomDB.user1_id == user_id, ChatRoomDB.user2_id == user_id),
                    ChatRoomDB.is_active.is_(True),
                )
            )
            .scalar()
        )

        # Get room IDs for this user
        room_ids = (
            db.query(ChatRoomDB.id)
            .filter(or_(ChatRoomDB.user1_id == user_id, ChatRoomDB.user2_id == user_id))
            .all()
        )
        room_ids = [room_id[0] for room_id in room_ids]

        total_messages = (
            db.query(func.count(MessageDB.id))
            .filter(MessageDB.chat_room_id.in_(room_ids))
            .scalar()
            if room_ids
            else 0
        )

        total_unread_messages = (
            db.query(func.count(MessageDB.id))
            .filter(
                and_(
                    MessageDB.chat_room_id.in_(room_ids),
                    MessageDB.sender_id != user_id,
                    MessageDB.status != MessageStatus.read.value,
                )
            )
            .scalar()
            if room_ids
            else 0
        )
    else:
        # Global statistics
        total_rooms = db.query(func.count(ChatRoomDB.id)).scalar()
        active_rooms = (
            db.query(func.count(ChatRoomDB.id))
            .filter(ChatRoomDB.is_active.is_(True))
            .scalar()
        )
        total_messages = db.query(func.count(MessageDB.id)).scalar()
        total_unread_messages = (
            db.query(func.count(MessageDB.id))
            .filter(MessageDB.status != MessageStatus.read.value)
            .scalar()
        )

    return ChatStatistics(
        total_rooms=total_rooms or 0,
        active_rooms=active_rooms or 0,
        total_messages=total_messages or 0,
        total_unread_messages=total_unread_messages or 0,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
