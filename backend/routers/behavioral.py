from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import json
import redis.asyncio as redis
from services.db_service import save_violation
from services.session_manager import manager

router = APIRouter()

class BehavioralAlert(BaseModel):
    student_id: str
    exam_id: str
    flag_type: str
    description: str
    risk_points: float
    timestamp: float

@router.post("/api/v1/behavioral/alert")
async def receive_behavioral_alert(alert: BehavioralAlert, background_tasks: BackgroundTasks):
    session_id = f"exam_{alert.exam_id}_{alert.student_id}"
    
    # 1. Format the violation
    flag = {
        "flag_type": alert.flag_type,
        "description": alert.description,
        "severity": "HIGH" if alert.risk_points >= 15 else "MEDIUM",
        "risk_points": alert.risk_points,
        "timestamp": alert.timestamp,
        "evidence_url": "Client-side browser telemetry" # No video for this, it's pure data
    }

    # 2. Save it permanently to Postgres (in the background so it's fast)
    background_tasks.add_task(save_violation, session_id, flag)

    # 3. Update the live memory state for the Admin Dashboard
    session = manager.get_by_id(session_id)
    if session:
        session.risk_score += alert.risk_points
        session.flags.append(flag)
        
        # 4. Blast it to the React Admin UI via the Redis Pub/Sub channel
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        alert_payload = {
            "type": "violation_alert",
            "session_id": session_id,
            "student_name": alert.student_id,
            "new_flags": [flag]
        }
        await redis_client.publish("dashboard_alerts", json.dumps(alert_payload))

    return {"status": "logged"}
