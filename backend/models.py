from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from database import Base
import uuid


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_code = Column(String(8), unique=True, nullable=False)
    student_id = Column(String, nullable=False)
    student_name = Column(String, nullable=False)
    exam_id = Column(String, nullable=False)
    exam_title = Column(String, nullable=False)

    status = Column(String, default="created")
    # created → system_check → identity_verification → in_progress → completed → terminated

    risk_score = Column(Float, default=0.0)
    risk_level = Column(String, default="GREEN")

    face_enrolled = Column(Boolean, default=False)
    face_baseline = Column(Text, nullable=True)  # numpy array as base64
    voice_enrolled = Column(Boolean, default=False)
    voice_baseline = Column(Text, nullable=True)  # numpy array as base64

    answers = Column(JSON, nullable=True)
    exam_data = Column(JSON, nullable=True)  # questions, duration, etc.

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    total_flags = Column(Integer, default=0)


class ProctoringEvent(Base):
    __tablename__ = "proctoring_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)  # CRITICAL, HIGH, MEDIUM, LOW
    message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    risk_points = Column(Integer, default=0)
    timestamp = Column(DateTime, server_default=func.now())


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False)
    admin_id = Column(String, nullable=False)
    action = Column(String, nullable=False)  # WARNING, PAUSE, TERMINATE
    message = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())