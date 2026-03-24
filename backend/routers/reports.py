from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from services.db_service import get_all_sessions, get_session_report
from services.evidence_capture import get_evidence_files
import os

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get("/history")
async def session_history():
    sessions = await get_all_sessions()
    return {"sessions": sessions}


@router.get("/report/{session_id}")
async def session_report(session_id: str):
    report = await get_session_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Session not found")

    evidence = get_evidence_files(session_id)
    report["evidence"] = evidence
    return report


@router.get("/evidence/{session_id}/{filename}")
async def get_evidence_image(session_id: str, filename: str):
    from config import settings
    filepath = os.path.join(str(settings.BASE_DIR), "evidence", session_id, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return FileResponse(filepath, media_type="image/jpeg")


@router.get("/sessions/completed")
async def completed_sessions():
    all_sessions = await get_all_sessions()
    completed = [s for s in all_sessions if s.get("status") in ("completed", "terminated")]
    return {"sessions": completed}
