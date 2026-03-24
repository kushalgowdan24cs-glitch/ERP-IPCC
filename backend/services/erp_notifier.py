"""
ERP Notifier — sends BANNED_OBJECT alerts to the Java ERP backend.

The notification is fire-and-forget: it logs failures but never crashes
the proctoring pipeline.  One automatic retry with a 2-second backoff
is attempted before giving up.
"""

import httpx
import logging
from datetime import datetime
from config import settings

logger = logging.getLogger("erp_notifier")


async def notify_erp_banned_object(
    session_id: str,
    student_id: str,
    detection: dict,
    image_url: str,
):
    """
    POST a BANNED_OBJECT violation to the ERP webhook.

    Parameters
    ----------
    session_id : str
        Active exam session ID.
    student_id : str
        Student identifier from the ERP.
    detection : dict
        Must contain ``class_name`` and ``confidence``.
    image_url : str
        Relative URL to the evidence snippet image.
    """
    payload = {
        "flag": "BANNED_OBJECT",
        "object_type": detection["class_name"],
        "confidence": detection["confidence"],
        "image_url": image_url,
        "session_id": session_id,
        "student_id": student_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    url = settings.ERP_WEBHOOK_URL
    if not url:
        logger.debug("ERP_WEBHOOK_URL not configured — skipping notification")
        return

    # One retry with 2-second backoff
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)

            if resp.status_code < 300:
                logger.info(
                    f"✅ ERP notified: {detection['class_name']} "
                    f"({detection['confidence']:.0%}) → {resp.status_code}"
                )
                return
            else:
                logger.warning(
                    f"ERP returned {resp.status_code} on attempt {attempt}"
                )
        except Exception as exc:
            logger.warning(f"ERP notification attempt {attempt} failed: {exc}")

        if attempt == 1:
            import asyncio
            await asyncio.sleep(2)

    logger.error("❌ ERP notification failed after 2 attempts — moving on")
