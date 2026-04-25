import os
import jwt
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status, Request
from pydantic import BaseModel
from livekit import api
import asyncpg

# Initialize router
router = APIRouter()
logger = logging.getLogger(__name__)

# ─── CONFIGURATION ───
ERP_JWT_SECRET = os.getenv("ERP_JWT_SECRET", "shared-secret-with-java-erp")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "f47ac10b58cc4372a5670e02b2c3d479f47ac10b58cc4372")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://127.0.0.1:8000")
STUDENT_PHOTOS_DIR = Path(__file__).resolve().parent.parent / "student_photos"

# ─── DATABASE DEPENDENCY (High-Performance Pool) ───
async def get_db_connection(request: Request):
    """
    Grabs a fast, pre-warmed connection from the pool we initialized in main.py.
    This prevents the database from crashing when 1,000 students connect at once.
    """
    async with request.app.state.db_pool.acquire() as conn:
        yield conn

# ─── REQUEST/RESPONSE SCHEMAS ───
class ExamJoinRequest(BaseModel):
    erp_jwt_token: Optional[str] = None
    token: Optional[str] = None
    client_type: Optional[str] = "desktop"

class ExamJoinResponse(BaseModel):
    livekit_url: str
    token: str
    room_name: str
    state: str
    student_id: str
    exam_code: str
    erp_photo_url: str


class PreflightContextResponse(BaseModel):
    student_id: str
    student_name: str
    exam_code: str
    erp_photo_url: str


class ProctorTokenResponse(BaseModel):
    token: str
    room_name: str


@router.get("/api/v1/proctor-token/{exam_code}", response_model=ProctorTokenResponse)
async def get_proctor_token(exam_code: str):
    room_name = f"exam_{exam_code}"
    try:
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.with_identity("PROCTOR_ADMIN")
        token.with_name("Head Proctor")
        token.with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=False,
            can_publish_data=False,
            can_subscribe=True,
            hidden=True,
        ))
        return ProctorTokenResponse(token=token.to_jwt(), room_name=room_name)
    except Exception as e:
        logger.error(f"Proctor Token Generation Failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate proctor token.",
        )


def decode_exam_token(erp_jwt_token: str):
    try:
        payload = jwt.decode(erp_jwt_token, ERP_JWT_SECRET, algorithms=["HS256"])
        student_id = payload.get("sub")
        student_name = payload.get("name") or student_id
        exam_code = payload.get("exam_code")

        if not exam_code:
            raise HTTPException(
                status_code=400,
                detail="Exam token required (missing exam_code claim)"
    )

        return student_id, student_name, exam_code
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Exam token has expired.")
    except (jwt.InvalidTokenError, ValueError) as e:
        logger.error(f"JWT Verification Failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid exam token.")


def extract_join_token(join_req: ExamJoinRequest) -> str:
    jwt_token = join_req.erp_jwt_token or join_req.token
    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing exam token payload. Provide `erp_jwt_token` or `token`.",
        )
    return jwt_token


def resolve_student_photo_url(student_id: str) -> str:
    for ext in ("jpg", "jpeg", "png", "webp"):
        file_name = f"{student_id}.{ext}"
        if (STUDENT_PHOTOS_DIR / file_name).exists():
            return f"{BACKEND_PUBLIC_URL}/student_photos/{file_name}"

    # Let the client use /student_profile.jpg as local fallback.
    return ""


@router.post("/api/v1/preflight-context", response_model=PreflightContextResponse)
async def get_preflight_context(join_req: ExamJoinRequest):
    student_id, student_name, exam_code = decode_exam_token(extract_join_token(join_req))
    return PreflightContextResponse(
        student_id=student_id,
        student_name=student_name,
        exam_code=exam_code,
        erp_photo_url=resolve_student_photo_url(student_id),
    )

# ─── THE CORE ENDPOINT ───
@router.post("/api/v1/join-exam", response_model=ExamJoinResponse)
async def join_exam(join_req: ExamJoinRequest, db: asyncpg.Connection = Depends(get_db_connection)):
    """
    1. Verifies the Java ERP JWT.
    2. Checks PostgreSQL to ensure the student is allowed to test.
    3. Updates the State Machine.
    4. Generates a secure, scoped WebRTC token.
    """
    
    # STEP 1: Cryptographic Verification of the Java ERP Token
    student_id, student_name, exam_code = decode_exam_token(extract_join_token(join_req))

    is_mobile_client = (join_req.client_type or "desktop").lower() == "mobile"

    # STEP 2: Database State Machine Enforcement
    # Fetch the current exam session state
    session_record = await db.fetchrow(
        "SELECT id, state FROM exam_sessions WHERE exam_code = $1 AND student_id = $2",
        exam_code, student_id
    )

    if not session_record:
        # Idempotent insert prevents duplicate-key races when React dev mode fires duplicate requests.
        await db.execute(
            """
            INSERT INTO exam_sessions (exam_code, student_id, state, scheduled_at)
            VALUES ($1, $2, 'SCHEDULED', NOW())
            ON CONFLICT (exam_code, student_id) DO NOTHING
            """,
            exam_code, student_id
        )
        session_record = await db.fetchrow(
            "SELECT id, state FROM exam_sessions WHERE exam_code = $1 AND student_id = $2",
            exam_code, student_id
        )

    if not session_record:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize exam session.",
        )

    current_state = session_record['state']

    # CRITICAL: Prevent completed/suspended exams from being rejoined
    if current_state in ['SUBMITTED', 'REPORT_GENERATED', 'ARCHIVED', 'SUSPENDED']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Cannot join exam. Current state is: {current_state}"
        )

    # STEP 3: State Transition
    # Desktop join activates exam state; mobile desk-cam token does not mutate session state.
    if not is_mobile_client:
        if current_state == 'SCHEDULED':
            await db.execute(
                "UPDATE exam_sessions SET state = 'IDENTITY_CHECK', identity_at = NOW() WHERE exam_code = $1 AND student_id = $2",
                exam_code, student_id
            )
            current_state = 'IDENTITY_CHECK'

        if current_state in ['IDENTITY_CHECK', 'PAUSED']:
            await db.execute(
                "UPDATE exam_sessions SET state = 'IN_PROGRESS' WHERE exam_code = $1 AND student_id = $2",
                exam_code, student_id
            )
            current_state = 'IN_PROGRESS'

    # STEP 4: LiveKit Room Topology (1 Room Per Exam)
    room_name = f"exam_{exam_code}"

    # STEP 5: Generate the Scoped WebRTC Token
    try:
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        participant_identity = f"{student_id}_MOBILE" if is_mobile_client else student_id
        participant_name = f"{student_name} (Desk Cam)" if is_mobile_client else student_name
        token.with_identity(participant_identity)
        token.with_name(participant_name)
        
        # Security: The student can publish video, but CANNOT subscribe.
        # This prevents them from somehow hacking the client to view other students' exams.
        token.with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,     
            can_publish_data=True, # Allows sending behavioral telemetry via LiveKit DataChannels
            can_subscribe=False,   
            hidden=False
        ))
        
        jwt_token = token.to_jwt()
        
    except Exception as e:
        logger.error(f"LiveKit Token Generation Failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not generate video token.")

    # Update DB with the room name
    await db.execute(
        "UPDATE exam_sessions SET livekit_room = $1 WHERE exam_code = $2 AND student_id = $3",
        room_name, exam_code, student_id
    )

    return ExamJoinResponse(
        livekit_url=LIVEKIT_URL,
        token=jwt_token,
        room_name=room_name,
        state=current_state,
        student_id=student_id,
        exam_code=exam_code,
        erp_photo_url=resolve_student_photo_url(student_id),
    )