import os

files = {}

# ============================================================
# services/db_service.py — Database persistence layer
# ============================================================
files[os.path.join("services", "db_service.py")] = """
import json
import time
from datetime import datetime
from sqlalchemy import text
from database import engine

async def save_session_to_db(session):
    async with engine.begin() as conn:
        await conn.execute(text('''
            INSERT OR REPLACE INTO exam_sessions
            (id, session_code, student_id, student_name, exam_id,
             exam_title, status, risk_score, risk_level, answers,
             exam_data, started_at, completed_at, created_at, total_flags, face_enrolled)
            VALUES (:id, :code, :sid, :sname, :eid,
                    :etitle, :status, :risk, :rlevel, :answers,
                    :edata, :started, :completed, :created, :flags, :face)
        '''), {
            "id": session.session_id,
            "code": session.session_code,
            "sid": session.student_id,
            "sname": session.student_name,
            "eid": session.exam_id,
            "etitle": session.exam_title,
            "status": session.status,
            "risk": session.risk_score,
            "rlevel": session.risk_level,
            "answers": json.dumps(session.answers),
            "edata": json.dumps(session.exam_data),
            "started": session.started_at.isoformat() if session.started_at else None,
            "completed": getattr(session, 'completed_at', None),
            "created": datetime.utcnow().isoformat(),
            "flags": len(session.flags),
            "face": session.face_baseline is not None,
        })


async def save_event_to_db(session_id, flag):
    async with engine.begin() as conn:
        await conn.execute(text('''
            INSERT INTO proctoring_events
            (session_id, event_type, severity, message, details, risk_points, timestamp)
            VALUES (:sid, :etype, :sev, :msg, :details, :rp, :ts)
        '''), {
            "sid": session_id,
            "etype": flag.get("flag_type", "UNKNOWN"),
            "sev": flag.get("severity", "LOW"),
            "msg": flag.get("message", ""),
            "details": json.dumps(flag.get("details", {})),
            "rp": flag.get("risk_points", 0),
            "ts": datetime.utcnow().isoformat(),
        })


async def save_answer_to_db(session_id, question_index, answer):
    async with engine.begin() as conn:
        await conn.execute(text('''
            INSERT OR REPLACE INTO student_answers
            (session_id, question_index, answer, submitted_at)
            VALUES (:sid, :qi, :ans, :ts)
        '''), {
            "sid": session_id,
            "qi": str(question_index),
            "ans": str(answer),
            "ts": datetime.utcnow().isoformat(),
        })


async def get_all_sessions():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            'SELECT id, session_code, student_name, exam_title, status, '
            'risk_score, risk_level, total_flags, started_at, completed_at '
            'FROM exam_sessions ORDER BY created_at DESC'
        ))
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]


async def get_session_report(session_id):
    async with engine.begin() as conn:
        # Session info
        result = await conn.execute(text(
            'SELECT * FROM exam_sessions WHERE id = :sid'
        ), {"sid": session_id})
        row = result.fetchone()
        if not row:
            return None
        session_data = dict(row._mapping)

        # Events
        result = await conn.execute(text(
            'SELECT event_type, severity, message, risk_points, timestamp '
            'FROM proctoring_events WHERE session_id = :sid ORDER BY timestamp'
        ), {"sid": session_id})
        events = [dict(r._mapping) for r in result.fetchall()]

        # Answers
        result = await conn.execute(text(
            'SELECT question_index, answer, submitted_at '
            'FROM student_answers WHERE session_id = :sid ORDER BY question_index'
        ), {"sid": session_id})
        answers = [dict(r._mapping) for r in result.fetchall()]

        return {
            "session": session_data,
            "events": events,
            "answers": answers,
            "summary": {
                "total_flags": len(events),
                "critical_flags": sum(1 for e in events if e["severity"] == "CRITICAL"),
                "high_flags": sum(1 for e in events if e["severity"] == "HIGH"),
                "medium_flags": sum(1 for e in events if e["severity"] == "MEDIUM"),
                "risk_score": session_data.get("risk_score", 0),
                "risk_level": session_data.get("risk_level", "GREEN"),
            }
        }
"""

# ============================================================
# services/evidence_capture.py — Save frame snapshots as evidence
# ============================================================
files[os.path.join("services", "evidence_capture.py")] = """
import os
import cv2
import numpy as np
from datetime import datetime
from config import settings
import logging

logger = logging.getLogger("evidence")

EVIDENCE_DIR = os.path.join(str(settings.BASE_DIR), "evidence")
os.makedirs(EVIDENCE_DIR, exist_ok=True)


def save_evidence_frame(session_id, frame, flag, face_result=None):
    session_dir = os.path.join(EVIDENCE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%H%M%S")
    flag_type = flag.get("flag_type", "UNKNOWN").replace(" ", "_")
    filename = f"{timestamp}_{flag_type}.jpg"
    filepath = os.path.join(session_dir, filename)

    # Draw bounding boxes if available
    annotated = frame.copy()

    if face_result and face_result.get("face_bbox"):
        x1, y1, x2, y2 = face_result["face_bbox"]
        color = (0, 255, 0) if face_result.get("identity_match") else (0, 0, 255)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        sim = face_result.get("similarity", 0)
        cv2.putText(annotated, f"Sim: {sim:.2f}", (x1, y1 - 10),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # Add flag info as text overlay
    cv2.putText(annotated, flag_type, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.putText(annotated, f"Severity: {flag.get('severity', '?')}", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

    cv2.imwrite(filepath, annotated)
    logger.info(f"Evidence saved: {filepath}")
    return filepath


def get_evidence_files(session_id):
    session_dir = os.path.join(EVIDENCE_DIR, session_id)
    if not os.path.exists(session_dir):
        return []

    files = []
    for f in sorted(os.listdir(session_dir)):
        if f.endswith(".jpg"):
            parts = f.replace(".jpg", "").split("_", 1)
            files.append({
                "filename": f,
                "timestamp": parts[0] if len(parts) > 0 else "",
                "flag_type": parts[1] if len(parts) > 1 else "",
                "path": f"/api/v1/evidence/{session_id}/{f}",
            })
    return files
"""

# ============================================================
# services/report_generator.py — Generate final exam report
# ============================================================
files[os.path.join("services", "report_generator.py")] = """
import json
import os
from datetime import datetime
from config import settings
import logging

logger = logging.getLogger("reports")

REPORTS_DIR = os.path.join(str(settings.BASE_DIR), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def generate_report(session, evidence_files=None):
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "session": {
            "session_id": session.session_id,
            "session_code": session.session_code,
            "student_id": session.student_id,
            "student_name": session.student_name,
            "exam_id": session.exam_id,
            "exam_title": session.exam_title,
            "status": session.status,
            "started_at": session.started_at.isoformat() if session.started_at else None,
        },
        "risk_assessment": {
            "final_score": round(session.risk_score, 1),
            "risk_level": session.risk_level,
            "recommendation": get_recommendation(session.risk_score, session.flags),
            "total_flags": len(session.flags),
        },
        "flag_breakdown": {
            "CRITICAL": [],
            "HIGH": [],
            "MEDIUM": [],
            "LOW": [],
        },
        "answers": session.answers,
        "evidence_count": len(evidence_files) if evidence_files else 0,
    }

    for flag in session.flags:
        severity = flag.get("severity", "LOW")
        if severity in report["flag_breakdown"]:
            report["flag_breakdown"][severity].append({
                "type": flag.get("flag_type"),
                "message": flag.get("message"),
                "timestamp": flag.get("timestamp"),
                "risk_points": flag.get("risk_points", 0),
            })

    # Save to file
    filepath = os.path.join(REPORTS_DIR, f"{session.session_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved: {filepath}")
    return report


def get_recommendation(score, flags):
    critical = sum(1 for f in flags if f.get("severity") == "CRITICAL")
    if score < 15 and critical == 0:
        return "CLEAN"
    elif score >= 60 or critical >= 3:
        return "FLAGGED"
    else:
        return "REVIEW"
"""

# ============================================================
# routers/reports.py — API for reports, history, evidence
# ============================================================
files[os.path.join("routers", "reports.py")] = """
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
"""

# ============================================================
# Updated database.py — Add new tables
# ============================================================
files["database.py"] = """
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text('''
            CREATE TABLE IF NOT EXISTS exam_sessions (
                id TEXT PRIMARY KEY,
                session_code TEXT,
                student_id TEXT,
                student_name TEXT,
                exam_id TEXT,
                exam_title TEXT,
                status TEXT DEFAULT 'created',
                risk_score REAL DEFAULT 0,
                risk_level TEXT DEFAULT 'GREEN',
                face_enrolled INTEGER DEFAULT 0,
                answers TEXT DEFAULT '{}',
                exam_data TEXT DEFAULT '{}',
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT,
                total_flags INTEGER DEFAULT 0
            )
        '''))

        await conn.execute(text('''
            CREATE TABLE IF NOT EXISTS proctoring_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                event_type TEXT,
                severity TEXT,
                message TEXT,
                details TEXT DEFAULT '{}',
                risk_points INTEGER DEFAULT 0,
                timestamp TEXT
            )
        '''))

        await conn.execute(text('''
            CREATE TABLE IF NOT EXISTS student_answers (
                session_id TEXT,
                question_index TEXT,
                answer TEXT,
                submitted_at TEXT,
                PRIMARY KEY (session_id, question_index)
            )
        '''))


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
"""

# ============================================================
# Updated websocket_handler.py — Add persistence + evidence
# ============================================================
files[os.path.join("routers", "websocket_handler.py")] = """
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.session_manager import manager
from services.db_service import save_session_to_db, save_event_to_db, save_answer_to_db
from services.evidence_capture import save_evidence_frame
from services.report_generator import generate_report
from services.evidence_capture import get_evidence_files
from ai_engine import ai
import numpy as np
import cv2
import base64
import json
import time
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger("proctoring.ws")

router = APIRouter()


def decode_frame(base64_data):
    img_bytes = base64.b64decode(base64_data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return frame


@router.websocket("/ws/proctor/{session_code}")
async def proctoring_socket(websocket: WebSocket, session_code: str):
    await websocket.accept()

    session = manager.get_by_code(session_code)
    if not session:
        await websocket.send_json({"type": "error", "message": "Invalid session code"})
        await websocket.close(code=4001)
        return

    session.client_ws = websocket
    session.status = "system_check"

    logger.info(f"Student connected: {session.student_name} (code: {session_code})")

    # Save session to DB
    await save_session_to_db(session)

    await websocket.send_json({
        "type": "session_ready",
        "session_id": session.session_id,
        "student_name": session.student_name,
        "exam_title": session.exam_title,
        "exam": session.exam_data,
    })

    gaze_away_start = None
    no_face_start = None
    last_frame = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")
            all_flags = []

            if msg_type == "frame":
                try:
                    frame = decode_frame(data["frame"])
                    last_frame = frame.copy()
                    session.last_frame_time = datetime.utcnow()

                    face_result = ai.face.verify_frame(frame, session.face_baseline)
                    all_flags.extend(face_result["flags"])

                    if not face_result["face_detected"]:
                        if no_face_start is None:
                            no_face_start = time.time()
                        elif time.time() - no_face_start > 15:
                            flag = {
                                "flag_type": "FACE_ABSENT_EXTENDED",
                                "severity": "CRITICAL",
                                "message": "No face for " + str(int(time.time() - no_face_start)) + " seconds",
                                "risk_points": 5,
                            }
                            all_flags.append(flag)
                    else:
                        no_face_start = None

                    obj_result = ai.objects.detect(frame)
                    all_flags.extend(obj_result["flags"])

                    gaze_result = ai.gaze.analyze(frame)
                    if not gaze_result["looking_at_screen"]:
                        if gaze_away_start is None:
                            gaze_away_start = time.time()
                        else:
                            away_duration = time.time() - gaze_away_start
                            if away_duration > 8:
                                all_flags.append({
                                    "flag_type": "GAZE_AWAY_SUSTAINED",
                                    "severity": "HIGH",
                                    "message": "Looking " + gaze_result["gaze_direction"] + " for " + str(int(away_duration)) + "s",
                                    "risk_points": 4,
                                })
                    else:
                        gaze_away_start = None

                    # Save evidence for important flags
                    for flag in all_flags:
                        if flag.get("severity") in ("CRITICAL", "HIGH"):
                            try:
                                save_evidence_frame(
                                    session.session_id, frame, flag, face_result
                                )
                            except Exception as e:
                                logger.debug(f"Evidence save error: {e}")

                except Exception as e:
                    logger.error(f"Frame processing error: {e}")

            elif msg_type == "enroll_face":
                try:
                    frame = decode_frame(data["frame"])
                    faces = ai.face.detect_faces(frame)

                    if len(faces) == 1:
                        embedding = ai.face.extract_embedding(faces[0]["crop"])
                        session.face_baseline = embedding
                        session.status = "identity_verification"

                        # Save enrollment frame as evidence
                        save_evidence_frame(
                            session.session_id, frame,
                            {"flag_type": "ENROLLMENT", "severity": "INFO",
                             "message": "Face enrolled"},
                            {"face_bbox": faces[0]["bbox"], "identity_match": True, "similarity": 1.0}
                        )

                        await save_session_to_db(session)

                        await websocket.send_json({
                            "type": "enrollment_result",
                            "success": True,
                            "message": "Face enrolled successfully",
                        })
                        logger.info(f"Face enrolled for {session.student_name}")
                    else:
                        msg = "No face detected" if len(faces) == 0 else "Multiple faces detected"
                        await websocket.send_json({
                            "type": "enrollment_result",
                            "success": False,
                            "message": "Enrollment failed: " + msg,
                        })
                except Exception as e:
                    logger.error(f"Enrollment error: {e}")
                    await websocket.send_json({
                        "type": "enrollment_result",
                        "success": False,
                        "message": "Enrollment error: " + str(e),
                    })

            elif msg_type == "audio":
                try:
                    audio_result = ai.audio.analyze_chunk(
                        data.get("audio", []),
                        data.get("sample_rate", 16000),
                    )
                    all_flags.extend(audio_result.get("flags", []))
                except Exception as e:
                    logger.debug(f"Audio error: {e}")

            elif msg_type == "system_event":
                event_name = data.get("event", "")
                if event_name == "copy_paste_attempt":
                    all_flags.append({"flag_type": "COPY_PASTE_ATTEMPT", "severity": "HIGH", "message": "Copy/paste attempted", "risk_points": 5})
                elif event_name == "tab_switch":
                    all_flags.append({"flag_type": "TAB_SWITCH_ATTEMPT", "severity": "HIGH", "message": "Window/tab switch attempted", "risk_points": 6})
                elif event_name == "app_lost_focus":
                    all_flags.append({"flag_type": "APP_LOST_FOCUS", "severity": "HIGH", "message": "Exam app lost focus", "risk_points": 7})

            elif msg_type == "exam_start":
                session.status = "in_progress"
                session.started_at = datetime.utcnow()
                await save_session_to_db(session)
                logger.info(f"Exam started: {session.student_name}")

            elif msg_type == "answer_submit":
                q_idx = data.get("question_index")
                answer = data.get("answer")
                session.answers[str(q_idx)] = answer
                await save_answer_to_db(session.session_id, q_idx, answer)

            elif msg_type == "exam_complete":
                session.status = "completed"
                session.completed_at = datetime.utcnow()

                # Generate final report
                evidence = get_evidence_files(session.session_id)
                report = generate_report(session, evidence)
                recommendation = report["risk_assessment"]["recommendation"]

                await save_session_to_db(session)

                await websocket.send_json({
                    "type": "exam_completed",
                    "risk_score": session.risk_score,
                    "risk_level": session.risk_level,
                    "total_flags": len(session.flags),
                    "recommendation": recommendation,
                    "report_url": f"/api/v1/report/{session.session_id}",
                })

                logger.info(
                    f"Exam completed: {session.student_name} | "
                    f"Risk: {session.risk_score} ({session.risk_level}) | "
                    f"Rec: {recommendation} | "
                    f"Evidence frames: {len(evidence)}"
                )
                break

            # Process flags
            if all_flags:
                for flag in all_flags:
                    points = ai.risk.compute_flag_points(flag)
                    flag["risk_points"] = points
                    flag["timestamp"] = time.time()
                    session.flags.append(flag)
                    session.risk_score += points
                    session.risk_level = ai.risk.compute_risk_level(session.risk_score)

                    # Save each flag to database
                    await save_event_to_db(session.session_id, flag)

                # Update session in DB
                await save_session_to_db(session)

                await websocket.send_json({
                    "type": "flags",
                    "flags": all_flags,
                    "risk_score": round(session.risk_score, 1),
                    "risk_level": session.risk_level,
                })

                await manager.broadcast_to_dashboard(session.session_id, {
                    "type": "session_update",
                    "session_id": session.session_id,
                    "student_name": session.student_name,
                    "risk_score": round(session.risk_score, 1),
                    "risk_level": session.risk_level,
                    "new_flags": all_flags,
                    "total_flags": len(session.flags),
                })

                if ai.risk.should_auto_terminate(session.risk_score):
                    session.status = "terminated"
                    await save_session_to_db(session)
                    await websocket.send_json({
                        "type": "terminate",
                        "reason": "Risk score exceeded threshold",
                    })
                    break

    except WebSocketDisconnect:
        logger.info(f"Student disconnected: {session.student_name}")
        session.status = "disconnected"
        await save_session_to_db(session)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        session.client_ws = None


@router.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket):
    await websocket.accept()
    logger.info("Dashboard connected")

    active = manager.get_all_active()
    for s in active:
        s.dashboard_ws_list.append(websocket)

    await websocket.send_json({
        "type": "initial_state",
        "sessions": [
            {
                "session_id": s.session_id,
                "student_name": s.student_name,
                "exam_title": s.exam_title,
                "status": s.status,
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
                "total_flags": len(s.flags),
                "flags": s.flags[-20:],
            }
            for s in active
        ],
    })

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "send_warning":
                target = manager.get_by_id(data.get("session_id"))
                if target and target.client_ws:
                    await target.client_ws.send_json({"type": "warning", "message": data.get("message", "Please focus.")})
            elif data.get("type") == "terminate_session":
                target = manager.get_by_id(data.get("session_id"))
                if target and target.client_ws:
                    target.status = "terminated"
                    await save_session_to_db(target)
                    await target.client_ws.send_json({"type": "terminate", "reason": "Terminated by proctor"})
    except WebSocketDisconnect:
        logger.info("Dashboard disconnected")
        for s in manager.get_all_active():
            if websocket in s.dashboard_ws_list:
                s.dashboard_ws_list.remove(websocket)
"""

# ============================================================
# Updated main.py — Add reports router + evidence serving
# ============================================================
files["main.py"] = """
import sys
import os
import logging
import mimetypes
from contextlib import asynccontextmanager

mimetypes.add_type('text/css', '.css')
mimetypes.add_type('application/javascript', '.js')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-24s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("proctorshield")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db
from ai_engine import ai
from routers import sessions, websocket_handler, reports


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    logger.info("=" * 50)
    logger.info("  ProctorShield v" + settings.APP_VERSION)
    logger.info("=" * 50)

    logger.info("Initializing database...")
    await init_db()
    logger.info("  Database ready")

    logger.info("Loading AI models...")
    ai.load_all()

    logger.info("=" * 50)
    logger.info("  Server running on http://" + settings.HOST + ":" + str(settings.PORT))
    logger.info("  Dashboard:  http://localhost:" + str(settings.PORT) + "/dashboard/")
    logger.info("  History:    http://localhost:" + str(settings.PORT) + "/api/v1/history")
    logger.info("=" * 50)

    yield
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(websocket_handler.router)
app.include_router(reports.router)

dashboard_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")
dashboard_dir = os.path.abspath(dashboard_dir)
if os.path.exists(dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "endpoints": {
            "create_test": "POST /api/v1/sessions/mock/create-test",
            "active_sessions": "GET /api/v1/sessions/active/all",
            "session_history": "GET /api/v1/history",
            "session_report": "GET /api/v1/report/{session_id}",
            "completed_sessions": "GET /api/v1/sessions/completed",
            "dashboard": "/dashboard/",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        ws_max_size=16 * 1024 * 1024,
    )
"""

# ============================================================
# WRITE ALL FILES
# ============================================================
print("=" * 50)
print("  Phase 2: Persistence + Evidence + Reports")
print("=" * 50)

for filepath, content in files.items():
    dirpath = os.path.dirname(filepath)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

    line_count = len(content.strip().split("\n"))
    print(f"  Wrote {filepath} ({line_count} lines)")

# Delete old database so tables get recreated
import pathlib
db_file = pathlib.Path("proctorshield.db")
if db_file.exists():
    db_file.unlink()
    print("  Deleted old database (will be recreated)")

# Create directories
os.makedirs("evidence", exist_ok=True)
os.makedirs("reports", exist_ok=True)
print("  Created evidence/ and reports/ directories")

print()
print("Phase 2 complete!")
print("Now run: python main.py")
print()
print("After restart:")
print("  1. Create test session: curl -X POST http://localhost:8000/api/v1/sessions/mock/create-test")
print("  2. Take exam in client")
print("  3. View report: http://localhost:8000/api/v1/history")
print("  4. Evidence frames saved in: backend/evidence/<session_id>/")
print("  5. Reports saved in: backend/reports/<session_id>.json")