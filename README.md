# Swappo Chat Service

The Chat microservice enables users who have accepted trade offers to communicate with each other.

## Quick Start

### Using Docker Compose

```bash
docker-compose up --build
```

The service will be available at:
- **API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **PgAdmin**: http://localhost:5050

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn main:app --reload
```

## Key Features

- ✅ Chat room creation for accepted trade offers
- ✅ Real-time messaging between trade participants
- ✅ Message status tracking (sent/delivered/read)
- ✅ Unread message counts
- ✅ Notification integration
- ✅ Chat statistics and analytics

## API Endpoints

### Chat Rooms
- `POST /api/v1/chat-rooms` - Create chat room
- `GET /api/v1/chat-rooms` - List user's chat rooms
- `GET /api/v1/chat-rooms/{id}` - Get chat room details
- `GET /api/v1/chat-rooms/trade-offer/{id}` - Get chat room by trade offer
- `PATCH /api/v1/chat-rooms/{id}/deactivate` - Deactivate chat room

### Messages
- `POST /api/v1/messages` - Send message
- `GET /api/v1/messages` - List messages in room
- `GET /api/v1/messages/{id}` - Get message details
- `PATCH /api/v1/messages/{id}` - Update message (mark as read)
- `PATCH /api/v1/messages/mark-read` - Mark all as read

### Statistics
- `GET /api/v1/statistics` - Get chat statistics

## Environment Variables

```env
DATABASE_URL=postgresql://swappo_user:swappo_pass@localhost:5432/swappo_chat
SQL_ECHO=false
```

## Integration

The Chat service is automatically integrated with:
- **Matchmaking Service**: Creates chat rooms when offers are accepted
- **Notification Service**: Sends notifications for new messages

## Documentation

For detailed documentation, see [README_DETAILED.md](./README_DETAILED.md)
