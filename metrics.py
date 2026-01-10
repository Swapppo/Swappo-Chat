"""
Prometheus metrics for Chat Service
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# Service info
chat_service = Info("chat_service", "Chat service version")
chat_service.info({"version": "1.0.0"})

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0],
)

# Retry Metrics
retry_attempts_total = Counter(
    "retry_attempts_total", "Total retry attempts", ["operation", "attempt"]
)

retry_success_total = Counter(
    "retry_success_total", "Total successful retries", ["operation"]
)

# Business Metrics
messages_sent_total = Counter("messages_sent_total", "Total messages sent")

conversations_created_total = Counter(
    "conversations_created_total", "Total conversations created"
)

active_conversations = Gauge("active_conversations", "Number of active conversations")


# Helper functions
def record_http_request(method: str, endpoint: str, status_code: int, duration: float):
    """Record HTTP request metrics"""
    http_requests_total.labels(
        method=method, endpoint=endpoint, status=status_code
    ).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
        duration
    )


def update_chat_metrics(db):
    """Update chat metrics from database"""
    from sqlalchemy import func

    from models import ConversationDB

    # Count active conversations
    count = db.query(func.count(ConversationDB.id)).scalar() or 0
    active_conversations.set(count)
