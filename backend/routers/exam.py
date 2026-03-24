import os
import json
import logging
import hashlib
import httpx
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, status, Request
from pydantic import BaseModel
from livekit import api
import asyncpg

router = APIRouter()
logger = logging.getLogger(__name__)

# ─── CONFIGURATION ───
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "f47ac10b58cc4372a5670e02b2c3d479f47ac10b58cc4372")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "http://localhost:7880") # Note: HTTP for API calls, not WS
ERP_WEBHOOK_URL = os.getenv("ERP_WEBHOOK_URL", "http://localhost:8080/api/v1/exam-results")

# ─── DATABASE DEPENDENCY ───
async def get_db_connection(request: Request):
    async with request.app.state.db_pool.acquire() as conn:
        yield conn

# ─── SCHEMAS ───
class SubmitExamRequest(BaseModel):
    student_id: str
    exam_code: str
    # In a real app, you'd pass a JWT here to verify identity again

# ─── BACKGROUND TASK: THE HEAVY LIFTING ───
async def finalize_exam_and_notify_erp(db_pool, student_id: str, exam_code: str, room_name: str):
    """
    Runs completely in the background after the student has safely closed their app.
    1. Force-closes the LiveKit room (stopping all recording).
    2. Calculates the final forensic data.
    3. Sends the secure Webhook to the Java ERP.
    """
    logger.info(f"Starting background finalization for {student_id}...")
    
    # 1. Force-Close the LiveKit Room
    try:
        lk_api = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        await lk_api.room.delete_room(api.DeleteRoomRequest(room=room_name))
        await lk_api.aclose()
        logger.info(f"Successfully destroyed LiveKit room: {room_name}")
    except Exception as e:
        logger.error(f"Failed to delete LiveKit room (it may already be empty): {e}")

    async with db_pool.acquire() as conn:
        # 2. Gather final Risk Score and Violations from Postgres
        session = await conn.fetchrow(
            "SELECT id, risk_score, risk_level FROM exam_sessions WHERE exam_code = $1 AND student_id = $2",
            exam_code, student_id
        )
        
        if not session:
            return
            
        session_id = session['id']
        
        violations = await conn.fetch(
            "SELECT violation_type, frame_timestamp FROM violations WHERE session_id = $1",
            session_id
        )
        
        # 3. Construct the Webhook Payload for the Java ERP
        payload = {
            "student_id": student_id,
            "exam_code": exam_code,
            "trust_score": max(0, 100 - session['risk_score']), # 100 is perfect, 0 is worst
            "risk_level": session['risk_level'],
            "violations_count": len(violations),
            "video_evidence_url": f"http://localhost:9001/exam-recordings/{room_name}.mp4",
            "submitted_at": datetime.utcnow().isoformat()
        }
        
        # 4. Attempt to send to Java ERP
        webhook_success = False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(ERP_WEBHOOK_URL, json=payload, timeout=10.0)
                if response.status_code in [200, 201, 202]:
                    webhook_success = True
                    logger.info(f"Successfully sent results to Java ERP for {student_id}")
                else:
                    logger.warning(f"Java ERP returned status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to reach Java ERP: {e}")

        # 5. Handle Success vs Failure (Dead Letter Queue)
        if webhook_success:
            await conn.execute(
                "UPDATE exam_sessions SET state = 'ARCHIVED', erp_webhook_sent = TRUE, updated_at = NOW() WHERE id = $1",
                session_id
            )
        else:
            # The ERP is down. Save it to the DLQ so we don't lose the grade.
            await conn.execute(
                """
                INSERT INTO webhook_dlq (session_id, payload, http_status, next_retry_at)
                VALUES ($1, $2, $3, NOW() + INTERVAL '5 minutes')
                """,
                session_id, json.dumps(payload), getattr(response, 'status_code', 500) if 'response' in locals() else 500
            )
            await conn.execute(
                "UPDATE exam_sessions SET state = 'REPORT_GENERATED', updated_at = NOW() WHERE id = $1",
                session_id
            )
            logger.warning(f"Results for {student_id} saved to Dead Letter Queue for retry.")


# ─── THE CORE ENDPOINT (Ultra-Fast) ───
@router.post("/api/v1/submit-exam")
async def submit_exam(
    request: SubmitExamRequest, 
    background_tasks: BackgroundTasks,
    req: Request,
    db: asyncpg.Connection = Depends(get_db_connection)
):
    """
    Marks the exam as SUBMITTED instantly, then kicks off the background process.
    """
    # 1. Lock the row and verify they are currently in an exam
    session = await db.fetchrow(
        "SELECT id, state, livekit_room FROM exam_sessions WHERE exam_code = $1 AND student_id = $2",
        request.exam_code, request.student_id
    )

    if not session or session['state'] not in ['IN_PROGRESS', 'PAUSED', 'FLAGGED']:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active exam session found to submit.")

    # 2. Instantly update State to SUBMITTED
    await db.execute(
        "UPDATE exam_sessions SET state = 'SUBMITTED', submitted_at = NOW() WHERE id = $1",
        session['id']
    )

    # 3. Fire and Forget the Background Task
    background_tasks.add_task(
        finalize_exam_and_notify_erp, 
        req.app.state.db_pool, # Pass the pool, not the single connection
        request.student_id, 
        request.exam_code, 
        session['livekit_room']
    )

    # 4. Return immediately so the student's UI feels lightning fast
    return {"status": "success", "message": "Exam submitted securely. You may now close the application."}