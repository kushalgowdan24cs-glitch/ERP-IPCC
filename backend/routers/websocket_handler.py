from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
import json
from services.session_manager import manager

router = APIRouter()
logger = logging.getLogger("proctorshield.ws")


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket for the Admin Dashboard to receive live AI alerts"""
    await websocket.accept()
    manager.active_dashboards.add(websocket)
    logger.info(f"🛡️ Admin Dashboard connected. Total: {len(manager.active_dashboards)}")
    
    try:
        while True:
            # Keep the connection alive
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.active_dashboards.remove(websocket)
        logger.info("🛡️ Admin Dashboard disconnected.")

@router.websocket("/ws/session/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str):
    """WebSocket for the Student App (Tauri/React) to receive proctor commands"""
    await websocket.accept()
    await manager.connect_student(session_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            # Handle heartbeat or client-side events if needed
    except WebSocketDisconnect:
        manager.disconnect_student(session_id)
    except Exception as e:
        logger.error(f"WS Error for {session_id}: {e}")
        manager.disconnect_student(session_id)