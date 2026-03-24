import os

files = {}

# ============================================================
# mock_erp.py
# ============================================================
files["mock_erp.py"] = '''
from jose import jwt
from datetime import datetime, timedelta
from config import settings

MOCK_STUDENTS = {
    "STU001": {
        "id": "STU001",
        "name": "Arjun Sharma",
        "email": "arjun@college.edu",
        "department": "Computer Science",
    },
    "STU002": {
        "id": "STU002",
        "name": "Priya Patel",
        "email": "priya@college.edu",
        "department": "Computer Science",
    },
}

MOCK_EXAMS = {
    "EXAM001": {
        "id": "EXAM001",
        "title": "Data Structures & Algorithms - Midterm",
        "duration_minutes": 30,
        "questions": [
            {
                "id": "Q1",
                "type": "mcq",
                "text": "What is the time complexity of binary search?",
                "options": ["O(n)", "O(log n)", "O(n squared)", "O(1)"],
                "correct": 1,
            },
            {
                "id": "Q2",
                "type": "mcq",
                "text": "Which data structure uses LIFO principle?",
                "options": ["Queue", "Stack", "Array", "Linked List"],
                "correct": 1,
            },
            {
                "id": "Q3",
                "type": "mcq",
                "text": "What is the worst-case time complexity of quicksort?",
                "options": ["O(n log n)", "O(n)", "O(n squared)", "O(log n)"],
                "correct": 2,
            },
            {
                "id": "Q4",
                "type": "mcq",
                "text": "Which traversal of a BST gives sorted output?",
                "options": ["Preorder", "Postorder", "Inorder", "Level order"],
                "correct": 2,
            },
            {
                "id": "Q5",
                "type": "short_answer",
                "text": "Explain the difference between a stack and a queue. Give one real-world example of each.",
                "correct": None,
            },
            {
                "id": "Q6",
                "type": "mcq",
                "text": "What is the space complexity of merge sort?",
                "options": ["O(1)", "O(log n)", "O(n)", "O(n squared)"],
                "correct": 2,
            },
            {
                "id": "Q7",
                "type": "mcq",
                "text": "Which of the following is NOT a stable sorting algorithm?",
                "options": ["Merge Sort", "Bubble Sort", "Quick Sort", "Insertion Sort"],
                "correct": 2,
            },
            {
                "id": "Q8",
                "type": "short_answer",
                "text": "What is a hash collision? Describe two methods to resolve it.",
                "correct": None,
            },
            {
                "id": "Q9",
                "type": "mcq",
                "text": "The height of a balanced BST with n nodes is:",
                "options": ["O(n)", "O(log n)", "O(n squared)", "O(sqrt n)"],
                "correct": 1,
            },
            {
                "id": "Q10",
                "type": "short_answer",
                "text": "Write the steps of Dijkstras algorithm in your own words.",
                "correct": None,
            },
        ],
    }
}


def generate_mock_token(student_id, exam_id):
    student = MOCK_STUDENTS.get(student_id, MOCK_STUDENTS["STU001"])
    exam = MOCK_EXAMS.get(exam_id, MOCK_EXAMS["EXAM001"])
    payload = {
        "student_id": student["id"],
        "student_name": student["name"],
        "exam_id": exam["id"],
        "exam_title": exam["title"],
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=4),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_mock_exam(exam_id):
    return MOCK_EXAMS.get(exam_id, MOCK_EXAMS["EXAM001"])


def get_mock_student(student_id):
    return MOCK_STUDENTS.get(student_id, MOCK_STUDENTS["STU001"])
'''

# ============================================================
# routers/__init__.py
# ============================================================
files[os.path.join("routers", "__init__.py")] = '''
'''

# ============================================================
# routers/sessions.py
# ============================================================
files[os.path.join("routers", "sessions.py")] = '''
from fastapi import APIRouter, HTTPException
from services.session_manager import manager
from mock_erp import get_mock_exam
import uuid
import random
import string

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def generate_code(length=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


@router.post("/")
async def create_session(req: dict):
    session_id = str(uuid.uuid4())
    session_code = generate_code()

    session = manager.create(
        session_id=session_id,
        session_code=session_code,
        student_id=req.get("student_id", "STU001"),
        student_name=req.get("student_name", "Test Student"),
        exam_id=req.get("exam_id", "EXAM001"),
        exam_title=req.get("exam_title", "Test Exam"),
        exam_data={
            "questions": req.get("questions", []),
            "duration_minutes": req.get("duration_minutes", 60),
        },
    )

    return {
        "session_id": session_id,
        "session_code": session_code,
        "status": "created",
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

    session = manager.create(
        session_id=session_id,
        session_code=session_code,
        student_id="STU001",
        student_name="Arjun Sharma",
        exam_id="EXAM001",
        exam_title=exam["title"],
        exam_data={
            "questions": exam["questions"],
            "duration_minutes": exam["duration_minutes"],
        },
    )

    return {
        "session_id": session_id,
        "session_code": session_code,
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
'''

# ============================================================
# routers/websocket_handler.py
# ============================================================
files[os.path.join("routers", "websocket_handler.py")] = '''
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.session_manager import manager
from ai_engine import ai
import numpy as np
import cv2
import base64
import json
import time
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

    await websocket.send_json({
        "type": "session_ready",
        "session_id": session.session_id,
        "student_name": session.student_name,
        "exam_title": session.exam_title,
        "exam": session.exam_data,
    })

    gaze_away_start = None
    no_face_start = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")
            all_flags = []

            if msg_type == "frame":
                try:
                    frame = decode_frame(data["frame"])
                    session.last_frame_time = datetime.utcnow()

                    face_result = ai.face.verify_frame(frame, session.face_baseline)
                    all_flags.extend(face_result["flags"])

                    if not face_result["face_detected"]:
                        if no_face_start is None:
                            no_face_start = time.time()
                        elif time.time() - no_face_start > 15:
                            all_flags.append({
                                "flag_type": "FACE_ABSENT_EXTENDED",
                                "severity": "CRITICAL",
                                "message": "No face for " + str(int(time.time() - no_face_start)) + " seconds",
                                "risk_points": 5,
                            })
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
                logger.info(f"Exam started: {session.student_name}")

            elif msg_type == "answer_submit":
                session.answers[str(data.get("question_index"))] = data.get("answer")

            elif msg_type == "exam_complete":
                session.status = "completed"
                recommendation = ai.risk.generate_recommendation(session.risk_score, session.flags)
                await websocket.send_json({
                    "type": "exam_completed",
                    "risk_score": session.risk_score,
                    "risk_level": session.risk_level,
                    "total_flags": len(session.flags),
                    "recommendation": recommendation,
                })
                logger.info(f"Exam completed: {session.student_name} | Risk: {session.risk_score} | Rec: {recommendation}")
                break

            if all_flags:
                for flag in all_flags:
                    points = ai.risk.compute_flag_points(flag)
                    flag["risk_points"] = points
                    flag["timestamp"] = time.time()
                    session.flags.append(flag)
                    session.risk_score += points
                    session.risk_level = ai.risk.compute_risk_level(session.risk_score)

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
                    await websocket.send_json({
                        "type": "terminate",
                        "reason": "Risk score exceeded threshold",
                    })
                    break

    except WebSocketDisconnect:
        logger.info(f"Student disconnected: {session.student_name}")
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
                    await target.client_ws.send_json({"type": "warning", "message": data.get("message", "Please focus on your exam.")})
            elif data.get("type") == "terminate_session":
                target = manager.get_by_id(data.get("session_id"))
                if target and target.client_ws:
                    target.status = "terminated"
                    await target.client_ws.send_json({"type": "terminate", "reason": "Terminated by proctor"})
    except WebSocketDisconnect:
        logger.info("Dashboard disconnected")
        for s in manager.get_all_active():
            if websocket in s.dashboard_ws_list:
                s.dashboard_ws_list.remove(websocket)
'''

# ============================================================
# services/__init__.py
# ============================================================
files[os.path.join("services", "__init__.py")] = '''
'''

# ============================================================
# services/session_manager.py
# ============================================================
files[os.path.join("services", "session_manager.py")] = '''
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from fastapi import WebSocket
import numpy as np


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

    client_ws: Optional[WebSocket] = None
    dashboard_ws_list: List[WebSocket] = field(default_factory=list)

    flags: List[dict] = field(default_factory=list)
    answers: Dict[str, str] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    last_frame_time: Optional[datetime] = None
    last_face_seen: Optional[datetime] = None
    gaze_away_start: Optional[datetime] = None

    current_question_shown_at: Optional[float] = None
    keystroke_log: List[dict] = field(default_factory=list)


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, ActiveSession] = {}
        self._code_to_id: Dict[str, str] = {}

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
        return [s for s in self._sessions.values() if s.status in ("system_check", "identity_verification", "in_progress")]

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

    async def broadcast_to_dashboard(self, session_id, message):
        session = self._sessions.get(session_id)
        if not session:
            return
        dead = []
        for ws in session.dashboard_ws_list:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            session.dashboard_ws_list.remove(ws)

    def remove(self, session_id):
        session = self._sessions.pop(session_id, None)
        if session:
            self._code_to_id.pop(session.session_code, None)


manager = SessionManager()
'''

# ============================================================
# ai_engine/__init__.py
# ============================================================
files[os.path.join("ai_engine", "__init__.py")] = '''
import logging

logger = logging.getLogger("ai_engine")


class AIEngine:
    def __init__(self):
        self._face_verifier = None
        self._object_detector = None
        self._gaze_tracker = None
        self._audio_monitor = None
        self._risk_scorer = None
        self._loaded = False

    def load_all(self):
        if self._loaded:
            return

        logger.info("Loading AI models...")

        from .face_verifier import FaceVerifier
        from .object_detector import ObjectDetector
        from .gaze_tracker import GazeTracker
        from .audio_monitor import AudioMonitor
        from .risk_scorer import RiskScorer

        self._face_verifier = FaceVerifier()
        logger.info("  Face Verifier loaded")

        self._object_detector = ObjectDetector()
        logger.info("  Object Detector loaded")

        self._gaze_tracker = GazeTracker()
        logger.info("  Gaze Tracker loaded")

        self._audio_monitor = AudioMonitor()
        logger.info("  Audio Monitor loaded")

        self._risk_scorer = RiskScorer()
        logger.info("  Risk Scorer loaded")

        self._loaded = True
        logger.info("All AI models loaded successfully.")

    @property
    def face(self):
        return self._face_verifier

    @property
    def objects(self):
        return self._object_detector

    @property
    def gaze(self):
        return self._gaze_tracker

    @property
    def audio(self):
        return self._audio_monitor

    @property
    def risk(self):
        return self._risk_scorer


ai = AIEngine()
'''

# ============================================================
# ai_engine/face_verifier.py
# ============================================================
files[os.path.join("ai_engine", "face_verifier.py")] = '''
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, List
import logging
import urllib.request

logger = logging.getLogger("ai_engine.face")

MODELS_DIR = Path(__file__).parent.parent / "ai_models"
MODELS_DIR.mkdir(exist_ok=True)

FACE_PROTO_URL = "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
FACE_MODEL_URL = "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"


class FaceVerifier:
    def __init__(self):
        self._download_models()
        proto_path = str(MODELS_DIR / "deploy.prototxt")
        model_path = str(MODELS_DIR / "res10_300x300_ssd.caffemodel")
        self.detector = cv2.dnn.readNetFromCaffe(proto_path, model_path)
        self.has_embedder = False

    def _download_models(self):
        proto_path = MODELS_DIR / "deploy.prototxt"
        model_path = MODELS_DIR / "res10_300x300_ssd.caffemodel"

        if not proto_path.exists():
            logger.info("Downloading face detection proto...")
            urllib.request.urlretrieve(FACE_PROTO_URL, str(proto_path))

        if not model_path.exists():
            logger.info("Downloading face detection model (10MB)...")
            urllib.request.urlretrieve(FACE_MODEL_URL, str(model_path))

    def detect_faces(self, frame):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
        self.detector.setInput(blob)
        detections = self.detector.forward()

        faces = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > 0.6:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                x1, y1, x2, y2 = box.astype(int)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                if x2 - x1 > 20 and y2 - y1 > 20:
                    faces.append({
                        "bbox": (x1, y1, x2, y2),
                        "confidence": float(confidence),
                        "crop": frame[y1:y2, x1:x2].copy(),
                    })
        return faces

    def extract_embedding(self, face_crop):
        face_resized = cv2.resize(face_crop, (64, 64))
        hsv = cv2.cvtColor(face_resized, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        return hist

    def compare_embeddings(self, emb1, emb2):
        if emb1 is None or emb2 is None:
            return 0.0
        dot = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))

    def verify_frame(self, frame, baseline_embedding):
        result = {
            "face_count": 0,
            "face_detected": False,
            "identity_match": False,
            "similarity": 0.0,
            "flags": [],
            "face_bbox": None,
            "face_crop": None,
        }

        faces = self.detect_faces(frame)
        result["face_count"] = len(faces)

        if len(faces) == 0:
            result["flags"].append({
                "flag_type": "NO_FACE_DETECTED",
                "severity": "HIGH",
                "message": "No face detected in frame",
                "risk_points": 3,
            })
            return result

        if len(faces) > 1:
            result["flags"].append({
                "flag_type": "MULTIPLE_FACES",
                "severity": "CRITICAL",
                "message": str(len(faces)) + " faces detected in frame",
                "risk_points": 8,
            })

        primary = max(faces, key=lambda f: (f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1]))
        result["face_detected"] = True
        result["face_bbox"] = primary["bbox"]
        result["face_crop"] = primary["crop"]

        if baseline_embedding is not None:
            current_embedding = self.extract_embedding(primary["crop"])
            similarity = self.compare_embeddings(baseline_embedding, current_embedding)
            result["similarity"] = similarity
            if similarity >= 0.45:
                result["identity_match"] = True
            else:
                result["flags"].append({
                    "flag_type": "IDENTITY_MISMATCH",
                    "severity": "CRITICAL",
                    "message": "Face does not match enrolled student (similarity: " + str(round(similarity, 2)) + ")",
                    "risk_points": 10,
                })

        return result
'''

# ============================================================
# ai_engine/object_detector.py
# ============================================================
files[os.path.join("ai_engine", "object_detector.py")] = '''
import numpy as np
from ultralytics import YOLO
import logging

logger = logging.getLogger("ai_engine.objects")

ALERT_CLASSES = {67, 73, 63, 62}

BANNED_OBJECTS = {
    67: ("cell phone", "CRITICAL", 8),
    73: ("book", "MEDIUM", 3),
    63: ("laptop", "HIGH", 5),
    62: ("tv", "HIGH", 6),
}


class ObjectDetector:
    def __init__(self, model_name="yolov8n.pt"):
        self.model = YOLO(model_name)
        self.model.fuse()

    def detect(self, frame, confidence=0.50):
        results = self.model(frame, conf=confidence, verbose=False)

        detected_objects = []
        flags = []
        person_count = 0

        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                bbox = box.xyxy[0].tolist()
                class_name = result.names[cls_id]

                if cls_id == 0:
                    person_count += 1

                detected_objects.append({
                    "class_id": cls_id,
                    "class_name": class_name,
                    "confidence": round(conf, 3),
                    "bbox": [int(b) for b in bbox],
                })

                if cls_id in ALERT_CLASSES:
                    label, severity, risk_points = BANNED_OBJECTS[cls_id]
                    flags.append({
                        "flag_type": "BANNED_OBJECT_" + class_name.upper().replace(" ", "_"),
                        "severity": severity,
                        "message": "Detected: " + class_name + " (confidence: " + str(round(conf * 100)) + "%)",
                        "risk_points": risk_points,
                    })

        if person_count > 1:
            flags.append({
                "flag_type": "MULTIPLE_PERSONS_IN_FRAME",
                "severity": "HIGH",
                "message": str(person_count) + " people detected in frame",
                "risk_points": 6,
            })

        return {"objects": detected_objects, "person_count": person_count, "flags": flags}
'''

# ============================================================
# ai_engine/gaze_tracker.py
# ============================================================
files[os.path.join("ai_engine", "gaze_tracker.py")] = '''
import cv2
import numpy as np
import mediapipe as mp
import logging

logger = logging.getLogger("ai_engine.gaze")

LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]
LEFT_EYE_INNER = 362
LEFT_EYE_OUTER = 263
RIGHT_EYE_INNER = 133
RIGHT_EYE_OUTER = 33
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_LEFT = 33
RIGHT_EYE_RIGHT = 263
LEFT_MOUTH = 61
RIGHT_MOUTH = 291


class GazeTracker:
    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def analyze(self, frame):
        result = {
            "gaze_direction": "UNKNOWN",
            "head_pose": {"yaw": 0, "pitch": 0},
            "looking_at_screen": True,
            "iris_position": None,
            "flags": [],
        }

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mesh_results = self.face_mesh.process(rgb)

        if not mesh_results.multi_face_landmarks:
            return result

        landmarks = mesh_results.multi_face_landmarks[0]
        h, w = frame.shape[:2]

        left_iris_center = self._get_iris_center(landmarks, LEFT_IRIS, w, h)
        right_iris_center = self._get_iris_center(landmarks, RIGHT_IRIS, w, h)
        left_inner = self._get_point(landmarks, LEFT_EYE_INNER, w, h)
        left_outer = self._get_point(landmarks, LEFT_EYE_OUTER, w, h)
        right_inner = self._get_point(landmarks, RIGHT_EYE_INNER, w, h)
        right_outer = self._get_point(landmarks, RIGHT_EYE_OUTER, w, h)

        left_ratio = self._iris_position_ratio(left_iris_center, left_inner, left_outer)
        right_ratio = self._iris_position_ratio(right_iris_center, right_inner, right_outer)

        if left_ratio is not None and right_ratio is not None:
            avg_ratio = (left_ratio + right_ratio) / 2
            result["iris_position"] = round(avg_ratio, 3)

            if avg_ratio < 0.30:
                result["gaze_direction"] = "LEFT"
                result["looking_at_screen"] = False
            elif avg_ratio > 0.70:
                result["gaze_direction"] = "RIGHT"
                result["looking_at_screen"] = False
            else:
                result["gaze_direction"] = "CENTER"
                result["looking_at_screen"] = True

        yaw, pitch = self._estimate_head_pose(landmarks, w, h)
        result["head_pose"] = {"yaw": round(yaw, 1), "pitch": round(pitch, 1)}

        if abs(yaw) > 30:
            result["looking_at_screen"] = False
            result["gaze_direction"] = "LEFT" if yaw < 0 else "RIGHT"

        if abs(pitch) > 25:
            result["looking_at_screen"] = False
            result["gaze_direction"] = "DOWN" if pitch > 0 else "UP"

        return result

    def _get_iris_center(self, landmarks, iris_indices, w, h):
        points = []
        for idx in iris_indices:
            lm = landmarks.landmark[idx]
            points.append((lm.x * w, lm.y * h))
        if points:
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)
            return (cx, cy)
        return None

    def _get_point(self, landmarks, idx, w, h):
        lm = landmarks.landmark[idx]
        return (lm.x * w, lm.y * h)

    def _iris_position_ratio(self, iris_center, eye_inner, eye_outer):
        if iris_center is None or eye_inner is None or eye_outer is None:
            return None
        eye_width = np.sqrt((eye_outer[0] - eye_inner[0])**2 + (eye_outer[1] - eye_inner[1])**2)
        if eye_width < 1:
            return None
        iris_dist = np.sqrt((iris_center[0] - eye_inner[0])**2 + (iris_center[1] - eye_inner[1])**2)
        return min(max(iris_dist / eye_width, 0), 1)

    def _estimate_head_pose(self, landmarks, w, h):
        nose = self._get_point(landmarks, NOSE_TIP, w, h)
        left_eye = self._get_point(landmarks, LEFT_EYE_LEFT, w, h)
        right_eye = self._get_point(landmarks, RIGHT_EYE_RIGHT, w, h)
        left_mouth = self._get_point(landmarks, LEFT_MOUTH, w, h)
        right_mouth = self._get_point(landmarks, RIGHT_MOUTH, w, h)
        chin = self._get_point(landmarks, CHIN, w, h)

        eye_center_x = (left_eye[0] + right_eye[0]) / 2
        mouth_center_x = (left_mouth[0] + right_mouth[0]) / 2
        face_center_x = (eye_center_x + mouth_center_x) / 2
        face_width = abs(right_eye[0] - left_eye[0])

        if face_width < 1:
            return 0, 0

        yaw_offset = (nose[0] - face_center_x) / face_width
        yaw = yaw_offset * 90

        eye_center_y = (left_eye[1] + right_eye[1]) / 2
        nose_to_eyes = nose[1] - eye_center_y
        nose_to_chin = chin[1] - nose[1]

        if nose_to_chin > 0:
            pitch_ratio = nose_to_eyes / nose_to_chin
            pitch = (pitch_ratio - 0.7) * 60
        else:
            pitch = 0

        return yaw, pitch
'''

# ============================================================
# ai_engine/audio_monitor.py
# ============================================================
files[os.path.join("ai_engine", "audio_monitor.py")] = '''
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger("ai_engine.audio")


class AudioMonitor:
    def __init__(self):
        self.vad_loaded = False
        self.ambient_rms_baseline = None
        self.calibration_frames = 0
        self.calibration_rms_sum = 0.0

        try:
            import torch
            self.vad_model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self.get_speech_timestamps = utils[0]
            self.vad_loaded = True
            logger.info("Silero VAD loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load Silero VAD: {e}")
            logger.warning("Using energy-based speech detection")

    def analyze_chunk(self, audio_data, sample_rate=16000):
        result = {
            "has_speech": False,
            "speech_confidence": 0.0,
            "audio_rms": 0.0,
            "is_silent": False,
            "flags": [],
        }

        audio = np.array(audio_data, dtype=np.float32)
        if len(audio) == 0:
            return result

        rms = float(np.sqrt(np.mean(audio ** 2)))
        result["audio_rms"] = round(rms, 6)

        if self.calibration_frames < 5:
            self.calibration_rms_sum += rms
            self.calibration_frames += 1
            if self.calibration_frames == 5:
                self.ambient_rms_baseline = self.calibration_rms_sum / 5
            return result

        if self.ambient_rms_baseline and rms < self.ambient_rms_baseline * 0.05:
            result["is_silent"] = True

        if self.vad_loaded:
            try:
                import torch
                tensor = torch.from_numpy(audio)
                if tensor.dim() == 1:
                    tensor = tensor.unsqueeze(0)
                speech_timestamps = self.get_speech_timestamps(tensor.squeeze(), self.vad_model, sampling_rate=16000)
                if speech_timestamps:
                    result["has_speech"] = True
                    total_speech = sum(ts["end"] - ts["start"] for ts in speech_timestamps)
                    result["speech_confidence"] = min(total_speech / tensor.shape[-1], 1.0)
            except Exception:
                result["has_speech"] = self._energy_based_vad(audio)
        else:
            result["has_speech"] = self._energy_based_vad(audio)

        if result["has_speech"]:
            result["flags"].append({
                "flag_type": "SPEECH_DETECTED",
                "severity": "MEDIUM",
                "message": "Voice activity detected",
                "risk_points": 2,
            })

        return result

    def _energy_based_vad(self, audio):
        rms = np.sqrt(np.mean(audio ** 2))
        zero_crossings = np.sum(np.abs(np.diff(np.sign(audio)))) / (2 * len(audio))
        if self.ambient_rms_baseline:
            energy_threshold = self.ambient_rms_baseline * 3
        else:
            energy_threshold = 0.01
        return rms > energy_threshold and 0.02 < zero_crossings < 0.25
'''

# ============================================================
# ai_engine/risk_scorer.py
# ============================================================
files[os.path.join("ai_engine", "risk_scorer.py")] = '''
from typing import List, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("ai_engine.risk")

DEFAULT_RISK_POINTS = {
    "NO_FACE_DETECTED": 3,
    "MULTIPLE_FACES": 8,
    "IDENTITY_MISMATCH": 10,
    "BANNED_OBJECT_CELL_PHONE": 8,
    "BANNED_OBJECT_BOOK": 3,
    "BANNED_OBJECT_LAPTOP": 5,
    "BANNED_OBJECT_TV": 6,
    "MULTIPLE_PERSONS_IN_FRAME": 6,
    "GAZE_AWAY_SUSTAINED": 4,
    "SPEECH_DETECTED": 2,
    "APP_LOST_FOCUS": 7,
    "COPY_PASTE_ATTEMPT": 5,
    "BLOCKED_PROCESS_RUNNING": 8,
    "TAB_SWITCH_ATTEMPT": 6,
}

SEVERITY_MULTIPLIER = {
    "CRITICAL": 2.0,
    "HIGH": 1.5,
    "MEDIUM": 1.0,
    "LOW": 0.5,
}


class RiskScorer:
    def __init__(self, auto_terminate_threshold=100):
        self.auto_terminate_threshold = auto_terminate_threshold
        self.recent_flags = {}
        self.cooldown_seconds = 30

    def compute_flag_points(self, flag):
        flag_type = flag.get("flag_type", "UNKNOWN")
        severity = flag.get("severity", "MEDIUM")

        now = datetime.utcnow()
        last_seen = self.recent_flags.get(flag_type)

        if last_seen and (now - last_seen) < timedelta(seconds=self.cooldown_seconds):
            multiplier = 0.3
        else:
            multiplier = 1.0

        self.recent_flags[flag_type] = now

        base_points = flag.get("risk_points", DEFAULT_RISK_POINTS.get(flag_type, 2))
        severity_mult = SEVERITY_MULTIPLIER.get(severity, 1.0)

        return max(1, int(base_points * severity_mult * multiplier))

    def compute_risk_level(self, total_score):
        if total_score >= 76:
            return "RED"
        elif total_score >= 51:
            return "ORANGE"
        elif total_score >= 26:
            return "YELLOW"
        return "GREEN"

    def should_auto_terminate(self, total_score):
        return total_score >= self.auto_terminate_threshold

    def generate_recommendation(self, total_score, flags):
        if total_score < 15:
            return "CLEAN"
        critical_flags = [f for f in flags if f.get("severity") == "CRITICAL"]
        if critical_flags or total_score >= 60:
            return "FLAGGED"
        return "REVIEW"
'''

# ============================================================
# main.py
# ============================================================
files["main.py"] = '''
import sys
import os
import logging
from contextlib import asynccontextmanager

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
from routers import sessions, websocket_handler


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
    logger.info("  Dashboard: http://localhost:" + str(settings.PORT) + "/dashboard/")
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

dashboard_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
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
'''

# ============================================================
# config.py
# ============================================================
files["config.py"] = '''
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "ProctorShield"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str = "sqlite+aiosqlite:///./proctorshield.db"

    JWT_SECRET: str = "proctorshield-dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"

    BASE_DIR: Path = Path(__file__).parent
    RECORDINGS_DIR: Path = Path(__file__).parent / "recordings"
    FRAMES_DIR: Path = Path(__file__).parent / "frames"

    FACE_SIMILARITY_THRESHOLD: float = 0.45
    OBJECT_DETECTION_CONFIDENCE: float = 0.50
    GAZE_AWAY_THRESHOLD_SECONDS: float = 8.0
    RISK_SCORE_AUTO_TERMINATE: int = 100

    FRAME_PROCESS_INTERVAL: float = 3.0

    class Config:
        env_file = ".env"


settings = Settings()

settings.RECORDINGS_DIR.mkdir(exist_ok=True)
settings.FRAMES_DIR.mkdir(exist_ok=True)
'''

# ============================================================
# database.py
# ============================================================
files["database.py"] = '''
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
'''

# ============================================================
# WRITE ALL FILES
# ============================================================
print("Writing all backend files...")
for filepath, content in files.items():
    # Ensure directory exists
    dirpath = os.path.dirname(filepath)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

    # Count lines
    line_count = len(content.strip().split("\n"))
    print(f"  Wrote {filepath} ({line_count} lines)")

print()
print("All files written successfully!")
print("Now run: python main.py")