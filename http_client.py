"""
HTTP Client utilities with retry pattern for Chat service
Used for resilient communication with Notifications service
"""

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@retry(
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=False,  # Don't fail message sending if notification fails
)
async def send_notification_with_retry(url: str, notification_data: dict) -> bool:
    """
    Send notification with retry logic

    Args:
        url: Notification service URL
        notification_data: Notification payload

    Returns:
        True if successful, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=notification_data)

            if response.status_code == 201:
                print("✅ Notification sent successfully")
                return True
            else:
                print(f"⚠️ Notification service returned: {response.text}")
                response.raise_for_status()  # Trigger retry on HTTP errors
                return False

    except Exception as e:
        print(f"⚠️ Failed to send notification: {str(e)}")
        return False
