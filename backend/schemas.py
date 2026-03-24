from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class CreateSessionRequest(BaseModel):
    student_id: str
    student_name: str
    exam_id: str
    exam_title: str
    questions: List[dict]
    duration_minutes: int = 60


class CreateSessionResponse(BaseModel):
    session_id: str
    session_code: str
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    student_name: str
    exam_title: str
    status: str
    risk_score: float
    risk_level: str
    total_flags: int
    started_at: Optional[datetime]


class SessionResultResponse(BaseModel):
    session_id: str
    student_id: str
    exam_id: str
    status: str
    answers: Optional[dict]
    risk_score: float
    risk_level: str
    total_flags: int
    events: List[dict]
    recommendation: str  # CLEAN, REVIEW, FLAGGED


class ProctoringFlag(BaseModel):
    flag_type: str
    severity: str
    message: str
    details: Optional[dict] = None
    timestamp: float