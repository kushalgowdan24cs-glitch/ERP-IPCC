from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from services.session_manager import manager
from mock_erp import get_mock_exam, get_student_photo_path
from ai_engine import ai
import uuid
import random
import string
import cv2
import asyncio
import logging

logger = logging.getLogger("sessions")

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def generate_code(length=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _preload_erp_embedding(student_id):
    """
    Read the student's official college ID photo and extract the face embedding.
    This runs at session creation time so the baseline is ready before the exam.
    In production, this photo comes from the ERP database.
    """
    photo_path = get_student_photo_path(student_id)
    if not photo_path:
        logger.warning(f"No ERP photo found for {student_id}")
        return None

    frame = cv2.imread(photo_path)
    if frame is None:
        logger.error(f"Failed to read photo: {photo_path}")
        return None

    faces = ai.face.detect_faces(frame)
    if len(faces) == 0:
        logger.warning(f"No face found in ERP photo for {student_id}")
        return None

    embedding = ai.face.extract_embedding(faces[0])
    logger.info(f"✅ ERP face embedding loaded for {student_id}")
    return embedding


@router.post("/")
async def create_session(req: dict):
    session_id = str(uuid.uuid4())
    session_code = generate_code()

    student_id = req.get("student_id", "STU001")

    # Pre-load the official face embedding from the ERP photo
    erp_embedding = await asyncio.to_thread(_preload_erp_embedding, student_id)

    session = manager.create(
        session_id=session_id,
        session_code=session_code,
        student_id=student_id,
        student_name=req.get("student_name", "Test Student"),
        exam_id=req.get("exam_id", "EXAM001"),
        exam_title=req.get("exam_title", "Test Exam"),
        exam_data={
            "questions": req.get("questions", []),
            "duration_minutes": req.get("duration_minutes", 60),
        },
    )

    # Store the ERP embedding as the face baseline
    if erp_embedding is not None:
        session.face_baseline = erp_embedding

    return {
        "session_id": session_id,
        "session_code": session_code,
        "status": "created",
        "has_erp_photo": erp_embedding is not None,
    }


@router.get("/{session_id}")
async def get_session_status(session_id: str):
    session = manager.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "student_name": session.student_name,
        "exam_title": session.exam_title,
        "status": session.status,
        "risk_score": session.risk_score,
        "risk_level": session.risk_level,
        "total_flags": len(session.flags),
        "started_at": session.started_at.isoformat() if session.started_at else None,
    }


@router.post("/mock/create-test")
async def create_test_session():
    exam = get_mock_exam("EXAM001")
    session_id = str(uuid.uuid4())
    session_code = generate_code()

    # Pre-load the official face embedding from the ERP photo
    erp_embedding = await asyncio.to_thread(_preload_erp_embedding, "STU001")

    session = manager.create(
        session_id=session_id,
        session_code=session_code,
        student_id="STU001",
        student_name="Divyansh Rai",
        exam_id="EXAM001",
        exam_title=exam["title"],
        exam_data={
            "questions": exam["questions"],
            "duration_minutes": exam["duration_minutes"],
        },
    )

    # Store the ERP embedding as the face baseline
    if erp_embedding is not None:
        session.face_baseline = erp_embedding

    return {
        "session_id": session_id,
        "session_code": session_code,
        "has_erp_photo": erp_embedding is not None,
        "message": "Test session created. Enter code " + session_code + " in the client app.",
    }


@router.get("/active/all")
async def get_all_active_sessions():
    active = manager.get_all_active()
    return [
        {
            "session_id": s.session_id,
            "session_code": s.session_code,
            "student_name": s.student_name,
            "exam_title": s.exam_title,
            "status": s.status,
            "risk_score": s.risk_score,
            "risk_level": s.risk_level,
            "total_flags": len(s.flags),
            "started_at": s.started_at.isoformat() if s.started_at else None,
        }
        for s in active
    ]


@router.get("/student-photo/{student_id}")
async def get_student_photo(student_id: str):
    """Serve the student's official college ID photo from the ERP database."""
    photo_path = get_student_photo_path(student_id)
    if not photo_path:
        raise HTTPException(status_code=404, detail="No photo found for student")
    media_type = "image/jpeg" if photo_path.endswith((".jpg", ".jpeg")) else "image/png"
    return FileResponse(photo_path, media_type=media_type)
