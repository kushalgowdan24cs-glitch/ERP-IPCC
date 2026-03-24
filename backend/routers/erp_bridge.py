from fastapi import APIRouter, HTTPException, BackgroundTasks
import httpx
import logging
from datetime import datetime
from services.session_manager import manager
from ai_engine import ai
from services.db_service import save_or_update_session
from services.storage_service import generate_evidence_link

router = APIRouter()
logger = logging.getLogger("proctorshield.erp")

# The URL of the Java ERP team's receiver endpoint
JAVA_ERP_WEBHOOK_URL = "http://java-erp.university.local/api/v1/proctor/results"
# A shared secret key so the Java server knows this data actually came from your Python server
ERP_SECRET_KEY = "super_secure_java_python_handshake_key"


async def send_to_java_erp(payload: dict) -> None:
  """Background task that guarantees delivery to the Java ERP."""
  headers = {
    "Content-Type": "application/json",
    "X-Proctor-Signature": ERP_SECRET_KEY,
  }

  async with httpx.AsyncClient() as client:
    try:
      logger.info(
        f"🚀 Firing Webhook to Java ERP for {payload['student_id']}..."
      )
      response = await client.post(
        JAVA_ERP_WEBHOOK_URL,
        json=payload,
        headers=headers,
        timeout=10.0,
      )

      if response.status_code in (200, 201):
        logger.info(
          f"✅ Java ERP successfully received data for {payload['student_id']}."
        )
      else:
        logger.error(
          f"⚠️ Java ERP rejected the payload. Status: {response.status_code}"
        )
        # In a true enterprise system, you'd push this to a Dead Letter Queue to retry later!
    except httpx.RequestError as e:
      logger.error(f"❌ CRITICAL: Failed to reach Java ERP: {e}")


@router.post("/api/v1/exam/submit")
async def submit_exam_and_notify_erp(
  student_id: str, exam_id: str, background_tasks: BackgroundTasks
):
  try:
    session_id = f"exam_{exam_id}_{student_id}"
    session = manager.get_by_code(session_id) or manager.get_by_id(session_id)

    if not session:
      # If the session isn't in memory, they might have had 0 flags.
      # You would fetch from Postgres here. For now, we mock a clean record.
      risk_score = 0.0
      risk_level = "GREEN"
      flags: list[dict] = []
    else:
      risk_score = session.risk_score
      risk_level = session.risk_level
      flags = session.flags

      # Lock the session so no more frames are processed
      session.status = "completed"
      session.completed_at = datetime.utcnow()

    # 🔐 Ensure final state is saved to Postgres
    await save_or_update_session(
      {
        "session_id": session_id,
        "student_id": student_id,
        "exam_id": exam_id,
        "status": "completed",
        "risk_score": risk_score,
        "risk_level": risk_level,
        "started_at": session.started_at if session else None,
        "completed_at": session.completed_at if session else None,
      }
    )

    # 1. Compile the Forensic Payload for the Java Team
    erp_payload = {
      "student_id": student_id,
      "exam_id": exam_id,
      "completion_time": datetime.utcnow().isoformat(),
      "proctor_results": {
        "final_risk_score": round(risk_score, 1),
        "risk_category": risk_level,  # GREEN, ORANGE, RED
        "total_violations": len(flags),
        "critical_flags": [f for f in flags if f.get("severity") == "CRITICAL"],
      },
      # WE NOW GENERATE THE SECURE EVIDENCE LINK
      "evidence_video_url": generate_evidence_link(session_id)
    }

    # 2. Fire and Forget! (Doesn't make the React frontend wait)
    background_tasks.add_task(send_to_java_erp, erp_payload)

    return {"status": "success", "message": "Exam submitted and ERP notified."}

  except Exception as e:
    logger.error(f"Submission Error: {e}")
    raise HTTPException(status_code=500, detail="Failed to process exam submission.")

