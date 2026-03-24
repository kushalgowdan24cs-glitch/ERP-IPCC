from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from fastapi import WebSocket
import numpy as np
import logging

logger = logging.getLogger("session_manager")


@dataclass
class ActiveSession:
    session_id: str
    session_code: str
    student_id: str
    student_name: str
    exam_id: str
    exam_title: str
    exam_data: dict

    status: str = "created"
    risk_score: float = 0.0
    risk_level: str = "GREEN"

    face_baseline: Optional[np.ndarray] = None
    voice_baseline: Optional[np.ndarray] = None

    client_ws: Optional[WebSocket] = None
    mobile_ws: Optional[WebSocket] = None
    dashboard_ws_list: List[WebSocket] = field(default_factory=list)

    flags: List[dict] = field(default_factory=list)
    answers: Dict[str, str] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_frame_time: Optional[datetime] = None
    last_face_seen: Optional[datetime] = None
    gaze_away_start: Optional[datetime] = None

    current_question_shown_at: Optional[float] = None
    keystroke_log: List[dict] = field(default_factory=list)

    # Latest base64 frames cached for dashboard initial state
    last_laptop_frame: Optional[str] = None
    last_mobile_frame: Optional[str] = None


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, ActiveSession] = {}
        self._code_to_id: Dict[str, str] = {}
        # Global list — every admin dashboard WS goes here
        self._dashboard_connections: List[WebSocket] = []

    def create(self, session_id, session_code, **kwargs):
        session = ActiveSession(session_id=session_id, session_code=session_code, **kwargs)
        self._sessions[session_id] = session
        self._code_to_id[session_code] = session_id
        return session

    def get_by_id(self, session_id):
        return self._sessions.get(session_id)

    def get_by_code(self, code):
        sid = self._code_to_id.get(code)
        if sid:
            return self._sessions.get(sid)
        return None

    def get_all_active(self):
        return [s for s in self._sessions.values() if s.status in ("created", "system_check", "identity_verification", "in_progress")]

    # 🚨 THE MISSING LINK: Fetch all sessions (including offline/completed) 🚨
    def get_all(self):
        return list(self._sessions.values())

    def add_flag(self, session_id, flag):
        session = self._sessions.get(session_id)
        if session:
            session.flags.append(flag)
            session.risk_score += flag.get("risk_points", 0)
            session.risk_level = self._compute_risk_level(session.risk_score)

    def _compute_risk_level(self, score):
        if score >= 76:
            return "RED"
        elif score >= 51:
            return "ORANGE"
        elif score >= 26:
            return "YELLOW"
        return "GREEN"

    # ── Dashboard connection management (global) ──

    def add_dashboard_ws(self, ws: WebSocket):
        self._dashboard_connections.append(ws)
        logger.info(f"Dashboard connected. Total dashboards: {len(self._dashboard_connections)}")

    def remove_dashboard_ws(self, ws: WebSocket):
        if ws in self._dashboard_connections:
            self._dashboard_connections.remove(ws)
        logger.info(f"Dashboard disconnected. Total dashboards: {len(self._dashboard_connections)}")

    async def broadcast_to_dashboard(self, session_id, message):
        """Send a message to ALL connected admin dashboards."""
        dead = []
        for ws in self._dashboard_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._dashboard_connections.remove(ws)

    async def send_to_student(self, session_id: str, message: dict):
        """Send a direct command to a specific student's WebSocket (God Mode)."""
        session = self._sessions.get(session_id)
        if session and session.client_ws:
            try:
                await session.client_ws.send_json(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send command to student {session_id}: {e}")
                return False
        return False

    def remove(self, session_id):
        session = self._sessions.pop(session_id, None)
        if session:
            self._code_to_id.pop(session.session_code, None)


manager = SessionManager()