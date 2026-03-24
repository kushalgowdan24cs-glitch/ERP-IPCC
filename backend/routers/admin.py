import os
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

router = APIRouter()
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

@router.websocket("/api/v1/admin/ws")
async def admin_websocket(websocket: WebSocket):
    """
    Connects the Proctor's browser directly to the Redis Pub/Sub stream.
    """
    await websocket.accept()
    logger.info("Admin Dashboard Connected.")
    
    redis_client = Redis.from_url(REDIS_URL)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("admin_live_alerts")
    
    try:
        while True:
            # Check for new messages every 100ms
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message and message['type'] == 'message':
                # Forward the JSON alert directly to the React/HTML frontend
                payload = message['data'].decode('utf-8')
                await websocket.send_text(payload)
            
            await asyncio.sleep(0.01) # Yield to the event loop

    except WebSocketDisconnect:
        logger.info("Admin Dashboard Disconnected.")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
    finally:
        await pubsub.unsubscribe("admin_live_alerts")
        await pubsub.close()
        await redis_client.close()