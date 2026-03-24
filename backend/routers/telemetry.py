import os
import json
import logging
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from pydantic import BaseModel
import asyncpg
from redis.asyncio import Redis

router = APIRouter()
logger = logging.getLogger(__name__)

# ─── CONFIGURATION ───
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = Redis.from_url(REDIS_URL)

# ─── DATABASE DEPENDENCY ───
async def get_db_connection(request: Request):
    async with request.app.state.db_pool.acquire() as conn:
        yield conn

# ─── SCHEMAS ───
class TelemetryEvent(BaseModel):
    student_id: str
    exam_code: str
    event_type: str  # e.g., 'TAB_SWITCH', 'COPY_PASTE_ATTEMPT', 'OS_TAMPERING'
    details: str
    timestamp: int

# ─── BACKGROUND TASK ───
async def process_telemetry(db_pool, event: TelemetryEvent):
    """
    Saves the event to the database and alerts the live proctors via Redis Pub/Sub.
    """
    try:
        async with db_pool.acquire() as conn:
            # 1. Get the active session ID
            session = await conn.fetchrow(
                "SELECT id FROM exam_sessions WHERE exam_code = $1 AND student_id = $2 AND state = 'IN_PROGRESS'",
                event.exam_code, event.student_id
            )
            
            if not session:
                return # Ignore telemetry if exam isn't active
                
            session_id = session['id']

            # 2. Save to PostgreSQL for the final PDF report
            if event.event_type in ['TAB_SWITCH', 'COPY_PASTE_ATTEMPT']:
                # Increment the counters in the behavioral table
                # Upsert logic: insert if missing, update if exists
                await conn.execute(
                    """
                    INSERT INTO behavioral_telemetry (session_id, event_type, tab_switches, copy_paste_count)
                    VALUES ($1, $2, 
                            CASE WHEN $2 = 'TAB_SWITCH' THEN 1 ELSE 0 END,
                            CASE WHEN $2 = 'COPY_PASTE_ATTEMPT' THEN 1 ELSE 0 END)
                    ON CONFLICT (id) DO UPDATE 
                    SET tab_switches = behavioral_telemetry.tab_switches + (CASE WHEN EXCLUDED.event_type = 'TAB_SWITCH' THEN 1 ELSE 0 END),
                        copy_paste_count = behavioral_telemetry.copy_paste_count + (CASE WHEN EXCLUDED.event_type = 'COPY_PASTE_ATTEMPT' THEN 1 ELSE 0 END)
                    """,
                    session_id, event.event_type
                )
            elif event.event_type == 'OS_TAMPERING':
                # OS Tampering is severe, log it directly as a CRITICAL violation
                await conn.execute(
                    """
                    INSERT INTO violations (session_id, violation_type, severity, description, frame_timestamp)
                    VALUES ($1, $2, 'CRITICAL', $3, $4)
                    """,
                    session_id, 'OS_TAMPERING', event.details, float(event.timestamp / 1000.0)
                )
                # Spike the risk score
                await conn.execute(
                    "UPDATE exam_sessions SET risk_score = 100.0, risk_level = 'RED' WHERE id = $1",
                    session_id
                )

            # 3. Blast the alert to the Live Admin Dashboard via Redis Pub/Sub
            alert_payload = {
                "student_id": event.student_id,
                "exam_code": event.exam_code,
                "type": "BEHAVIORAL_ALERT",
                "event": event.event_type,
                "details": event.details
            }
            await redis_client.publish("admin_live_alerts", json.dumps(alert_payload))
            
    except Exception as e:
        logger.error(f"Failed to process telemetry: {e}")

# ─── THE CORE ENDPOINT ───
@router.post("/api/v1/telemetry")
async def receive_telemetry(
    event: TelemetryEvent, 
    background_tasks: BackgroundTasks,
    req: Request
):
    """
    Ultra-fast endpoint that accepts behavioral data from React and processes it in the background.
    """
    # Fire and forget. Return 200 OK instantly so the React UI never lags.
    background_tasks.add_task(process_telemetry, req.app.state.db_pool, event)
    return {"status": "received"}