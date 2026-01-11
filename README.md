# Swappo-Chat

Chat microservice for the Swappo platform enabling communication between users with accepted trade offers.

## Features

- **Chat Room Management**: Automatic creation for accepted trade offers
- **Messaging**: Send, retrieve, and track message status
- **Unread Counts**: Track unread messages per room
- **Notification Integration**: Automatic notifications for new messages
- **Statistics**: Chat analytics and metrics
- **Prometheus Metrics**: Built-in monitoring

## Quick Start

### Docker (Recommended)

```bash
docker-compose up -d
```

### Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| POST | `/api/v1/chat-rooms` | Create chat room |
| GET | `/api/v1/chat-rooms` | List user's chat rooms |
| GET | `/api/v1/chat-rooms/{id}` | Get chat room details |
| GET | `/api/v1/chat-rooms/trade-offer/{id}` | Get room by trade offer |
| PATCH | `/api/v1/chat-rooms/{id}/deactivate` | Deactivate chat room |
| POST | `/api/v1/messages` | Send message |
| GET | `/api/v1/messages` | List messages in room |
| GET | `/api/v1/messages/{id}` | Get message details |
| PATCH | `/api/v1/messages/{id}` | Mark message as read |
| PATCH | `/api/v1/messages/mark-read` | Mark all as read |
| GET | `/api/v1/statistics` | Get chat statistics |
| GET | `/metrics` | Prometheus metrics |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection string |
| `SQL_ECHO` | false | Enable SQL query logging |
| `NOTIFICATION_SERVICE_URL` | http://notifications_service:8000 | Notifications API URL |

## Service Integration

- **Matchmaking Service**: Triggers chat room creation on offer acceptance
- **Notification Service**: Sends push notifications for new messages with retry logic

## Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
