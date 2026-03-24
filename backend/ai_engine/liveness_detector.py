"""
backend/ai_engine/liveness_detector.py

Anti-Spoofing: 3-Layer Active Liveness + Legacy Passive Check
==============================================================
Layer 1 — Texture Analysis    : FFT frequency scan catches screens/prints
Layer 2 — Active Challenges   : Strictly BLINK challenge (optimized for lag)
Layer 3 — Micro-Movement      : Optical flow detects frozen images

LivenessDetector (bottom)     : Legacy MiniFASNet passive check — still used
                                 inside verify_frame() during the exam.
"""

import os
import cv2
import numpy as np
import logging
import time
import random
import torch
import torch.nn.functional as F
import mediapipe as mp
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ai_engine.liveness")


# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS — MediaPipe Face Mesh Landmark Indices
# ═══════════════════════════════════════════════════════════════════

RIGHT_EYE_IDX = [33, 160, 158, 133, 153, 144]
LEFT_EYE_IDX  = [362, 385, 387, 263, 373, 380]

NOSE_TIP        = 1
CHIN            = 152
LEFT_EYE_OUTER  = 263
RIGHT_EYE_OUTER = 33
LEFT_MOUTH      = 61
RIGHT_MOUTH     = 291
UPPER_LIP       = 13
LOWER_LIP       = 14


# ═══════════════════════════════════════════════════════════════════
#  ENUMS & DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

class ChallengeType(str, Enum):
    BLINK = "BLINK"
    # Removed TURN_LEFT, TURN_RIGHT, NOD_UP, OPEN_MOUTH for stability


class SessionState(str, Enum):
    PASSIVE_CHECK = "PASSIVE_CHECK"
    CHALLENGING   = "CHALLENGING"
    PASSED        = "PASSED"
    FAILED        = "FAILED"


class ChallengeState(str, Enum):
    PENDING   = "PENDING"
    ACTIVE    = "ACTIVE"
    COMPLETED = "COMPLETED"


CHALLENGE_INSTRUCTIONS = {
    ChallengeType.BLINK: "Blink your eyes 3 times",
}


@dataclass
class Challenge:
    type: ChallengeType
    state: ChallengeState = ChallengeState.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    timeout: float = 30.0  # Kept at 30 seconds to account for lag

    @property
    def instruction(self) -> str:
        return CHALLENGE_INSTRUCTIONS[self.type]

    @property
    def time_remaining(self) -> float:
        if self.started_at is None:
            return self.timeout
        return max(0.0, self.timeout - (time.time() - self.started_at))

    @property
    def is_timed_out(self) -> bool:
        return self.started_at is not None and self.time_remaining <= 0


@dataclass
class LivenessSession:
    student_id: str
    state: SessionState = SessionState.PASSIVE_CHECK
    challenges: list = field(default_factory=list)
    current_challenge_idx: int = 0
    passive_scores: list = field(default_factory=list)
    movement_frames: list = field(default_factory=list)
    fail_reason: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    # Restored to the snappy, responsive tracking
    blink_count: int = 0
    eye_was_closed: bool = False
    REQUIRED_BLINKS: int = 3

    @property
    def current_challenge(self) -> Optional[Challenge]:
        if self.current_challenge_idx < len(self.challenges):
            return self.challenges[self.current_challenge_idx]
        return None

    @property
    def all_challenges_done(self) -> bool:
        return all(c.state == ChallengeState.COMPLETED for c in self.challenges)

    @property
    def progress(self) -> dict:
        done = sum(1 for c in self.challenges if c.state == ChallengeState.COMPLETED)
        total = len(self.challenges)
        return {
            "completed": done,
            "total": total,
            "percent": int(done / max(total, 1) * 100),
        }

    def reset_action_state(self):
        """Reset per-challenge tracking when moving to next challenge."""
        self.blink_count = 0
        self.eye_was_closed = False


# ═══════════════════════════════════════════════════════════════════
#  LAYER 1 — TEXTURE ANALYZER
#  Catches phone screens (moiré) and printed photos (flat texture)
# ═══════════════════════════════════════════════════════════════════

class TextureAnalyzer:

    def __init__(self):
        self.FREQ_RATIO_THRESHOLD = 2.2
        self.LBP_VAR_THRESHOLD    = 18.0
        self.COLOR_STD_THRESHOLD  = 12.0

    def analyze(self, face_crop: np.ndarray) -> dict:
        if face_crop is None or face_crop.size == 0:
            return {"is_spoof": False, "confidence": 0, "reason": "no_face_crop"}
        if face_crop.shape[0] < 50 or face_crop.shape[1] < 50:
            return {"is_spoof": False, "confidence": 0, "reason": "face_too_small"}

        signals = 0
        total = 3
        details = {}

        # Check 1 — FFT frequency analysis
        freq_ratio, has_moire = self._fft_analysis(face_crop)
        details["freq_ratio"] = round(freq_ratio, 3)
        details["has_moire"] = has_moire
        if freq_ratio > self.FREQ_RATIO_THRESHOLD or has_moire:
            signals += 1

        # Check 2 — Texture variance (edge filter as LBP proxy)
        lbp_var = self._texture_variance(face_crop)
        details["texture_variance"] = round(lbp_var, 2)
        if lbp_var < self.LBP_VAR_THRESHOLD:
            signals += 1

        # Check 3 — Color saturation distribution
        color_std = self._color_analysis(face_crop)
        details["color_std"] = round(color_std, 2)
        if color_std < self.COLOR_STD_THRESHOLD:
            signals += 1

        confidence = signals / total
        is_spoof = signals >= 2

        return {"is_spoof": is_spoof, "confidence": round(confidence, 3),
                "signals": signals, **details}

    # ---- internals ----

    def _fft_analysis(self, crop: np.ndarray):
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (128, 128))

        f = np.fft.fft2(gray.astype(np.float32))
        f_shift = np.fft.fftshift(f)
        mag = np.log(np.abs(f_shift) + 1)

        h, w = mag.shape
        cy, cx = h // 2, w // 2
        y, x = np.ogrid[:h, :w]
        dist = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)

        r_low = min(h, w) // 8
        r_mid = min(h, w) // 4

        low  = np.mean(mag[dist <= r_low])
        mid  = np.mean(mag[(dist > r_low) & (dist <= r_mid)])
        high = np.mean(mag[dist > r_mid])

        ratio = (mid + high) / (low + 1e-6)

        # moiré peak detection
        h_slice = mag[cy, cx + 5:]
        peaks = 0
        if len(h_slice) > 10:
            mean_val = np.mean(h_slice)
            for i in range(1, len(h_slice) - 1):
                if h_slice[i] > h_slice[i-1] and h_slice[i] > h_slice[i+1]:
                    if h_slice[i] > mean_val * 1.5:
                        peaks += 1

        return ratio, peaks > 4

    def _texture_variance(self, crop: np.ndarray):
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (128, 128))
        kernel = np.array([[-1, -1, -1],
                           [-1,  8, -1],
                           [-1, -1, -1]], dtype=np.float32)
        edges = cv2.filter2D(gray.astype(np.float32), -1, kernel)
        return float(np.var(edges))

    def _color_analysis(self, crop: np.ndarray):
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1].astype(np.float32)
        return float(np.std(saturation))


# ═══════════════════════════════════════════════════════════════════
#  LAYER 2 — ACTIVE CHALLENGE DETECTOR
#  Uses MediaPipe Face Mesh — photos can't blink
# ═══════════════════════════════════════════════════════════════════

class ActiveChallengeDetector:

    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            static_image_mode=False,
        )
        self.EAR_CLOSED = 0.21  # Restored to original working value for snappy detection

    def extract_metrics(self, frame: np.ndarray) -> Optional[dict]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.face_mesh.process(rgb)

        if not result.multi_face_landmarks:
            return None

        lm = result.multi_face_landmarks[0].landmark
        h, w = frame.shape[:2]

        def pt(idx):
            return np.array([lm[idx].x * w, lm[idx].y * h])

        ear_l = self._ear(pt, LEFT_EYE_IDX)
        ear_r = self._ear(pt, RIGHT_EYE_IDX)
        ear   = (ear_l + ear_r) / 2.0

        yaw, pitch, roll = self._head_pose(pt, w, h)
        mar = self._mar(pt)

        return {"ear": ear, "yaw": yaw, "pitch": pitch, "roll": roll, "mar": mar}

    def check(self, metrics: dict, challenge: Challenge,
              session: LivenessSession) -> bool:
        ct = challenge.type

        if ct == ChallengeType.BLINK:
            return self._check_blink(metrics["ear"], session)
        return False

    # ---- helpers ----

    def _check_blink(self, ear: float, session: LivenessSession) -> bool:
        # Restored to the fast boolean logic without the cooldown block
        if ear < self.EAR_CLOSED:
            if not session.eye_was_closed:
                session.eye_was_closed = True
        else:
            if session.eye_was_closed:
                session.blink_count += 1
                session.eye_was_closed = False
                
        return session.blink_count >= session.REQUIRED_BLINKS

    def _ear(self, pt, indices) -> float:
        p1, p2, p3, p4, p5, p6 = [pt(i) for i in indices]
        v1 = np.linalg.norm(p2 - p6)
        v2 = np.linalg.norm(p3 - p5)
        h  = np.linalg.norm(p1 - p4)
        return (v1 + v2) / (2.0 * h + 1e-6)

    def _head_pose(self, pt, img_w, img_h):
        model_3d = np.array([
            [0, 0, 0],          # nose tip
            [0, -330, -65],     # chin
            [-225, 170, -135],  # left eye outer
            [225, 170, -135],   # right eye outer
            [-150, -150, -125], # left mouth
            [150, -150, -125],  # right mouth
        ], dtype=np.float64)

        pts_2d = np.array([
            pt(NOSE_TIP), pt(CHIN),
            pt(LEFT_EYE_OUTER), pt(RIGHT_EYE_OUTER),
            pt(LEFT_MOUTH), pt(RIGHT_MOUTH),
        ], dtype=np.float64)

        focal = float(img_w)
        cam = np.array([
            [focal, 0, img_w / 2],
            [0, focal, img_h / 2],
            [0, 0, 1],
        ], dtype=np.float64)

        ok, rvec, tvec = cv2.solvePnP(
            model_3d, pts_2d, cam, np.zeros((4, 1)),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return 0.0, 0.0, 0.0

        rmat, _ = cv2.Rodrigues(rvec)
        sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)

        if sy > 1e-6:
            pitch = float(np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2])))
            yaw   = float(np.degrees(np.arctan2(-rmat[2, 0], sy)))
            roll  = float(np.degrees(np.arctan2(rmat[1, 0], rmat[0, 0])))
        else:
            pitch = float(np.degrees(np.arctan2(-rmat[1, 2], rmat[1, 1])))
            yaw   = float(np.degrees(np.arctan2(-rmat[2, 0], sy)))
            roll  = 0.0

        return yaw, pitch, roll

    def _mar(self, pt) -> float:
        upper = pt(UPPER_LIP)
        lower = pt(LOWER_LIP)
        left  = pt(LEFT_MOUTH)
        right = pt(RIGHT_MOUTH)
        v = np.linalg.norm(upper - lower)
        h = np.linalg.norm(left - right)
        return v / (h + 1e-6)

    def close(self):
        self.face_mesh.close()


# ═══════════════════════════════════════════════════════════════════
#  LAYER 3 — MICRO-MOVEMENT ANALYZER
#  Real faces have involuntary sway; photos are dead-still
# ═══════════════════════════════════════════════════════════════════

class MicroMovementAnalyzer:

    def __init__(self):
        self.NATURAL_MIN  = 0.25   # below = suspiciously still
        self.NATURAL_MAX  = 18.0   # above = shaking a phone
        self.VARIANCE_MIN = 0.02   # natural movement has variance
        self.MIN_FRAMES   = 8

    def analyze(self, frames: list) -> dict:
        if len(frames) < self.MIN_FRAMES:
            return {"natural": True, "reason": "not_enough_frames"}

        indices = np.linspace(0, len(frames) - 1,
                              min(20, len(frames)), dtype=int)
        sampled = [frames[i] for i in indices]

        movements = []
        prev_gray = cv2.cvtColor(sampled[0], cv2.COLOR_BGR2GRAY)

        for i in range(1, len(sampled)):
            curr_gray = cv2.cvtColor(sampled[i], cv2.COLOR_BGR2GRAY)
            corners = cv2.goodFeaturesToTrack(
                prev_gray, maxCorners=40, qualityLevel=0.01, minDistance=10,
            )
            if corners is None or len(corners) < 3:
                prev_gray = curr_gray
                continue

            nxt, status, _ = cv2.calcOpticalFlowPyrLK(
                prev_gray, curr_gray, corners, None,
            )
            if nxt is None:
                prev_gray = curr_gray
                continue

            good_old = corners[status.flatten() == 1]
            good_new = nxt[status.flatten() == 1]

            if len(good_old) > 0:
                diffs = np.linalg.norm(good_new - good_old, axis=1)
                movements.append(float(np.mean(diffs)))

            prev_gray = curr_gray

        if not movements:
            return {"natural": False, "reason": "no_trackable_points"}

        avg = float(np.mean(movements))
        var = float(np.var(movements))

        is_still   = avg < self.NATURAL_MIN
        is_shaky   = avg > self.NATURAL_MAX
        is_robotic = var < self.VARIANCE_MIN and avg < 2.0

        natural = not is_still and not is_shaky and not is_robotic

        return {
            "natural": natural,
            "avg_movement": round(avg, 3),
            "variance": round(var, 4),
            "is_still": is_still,
            "is_robotic": is_robotic,
            "frames_used": len(movements),
        }


# ═══════════════════════════════════════════════════════════════════
#  LIVENESS ENGINE — Orchestrates all 3 layers
# ═══════════════════════════════════════════════════════════════════

class LivenessEngine:
    """
    Usage from websocket_handler:
        engine = LivenessEngine()

        info = engine.create_session("STU001")       # → send to client
        for each incoming frame:
            result = engine.process_frame("STU001", frame)
            # send result to client
            if result["state"] == "PASSED":  → run face matching
            if result["state"] == "FAILED":  → reject
    """

    def __init__(self):
        self.texture  = TextureAnalyzer()
        self.detector = ActiveChallengeDetector()
        self.movement = MicroMovementAnalyzer()
        self.sessions: dict[str, LivenessSession] = {}
        logger.info("LivenessEngine initialised — 3 layers active")

    def create_session(self, student_id: str) -> dict:
        """Create a new liveness session using strictly BLINK."""
        
        # Strictly use BLINK to combat video latency
        challenges = [Challenge(type=ChallengeType.BLINK)]
        
        session = LivenessSession(
            student_id=student_id,
            state=SessionState.PASSIVE_CHECK,
            challenges=challenges,
        )
        self.sessions[student_id] = session

        return {
            "type": "liveness_session_created",
            "student_id": student_id,
            "challenges": [
                {"type": c.type.value, "instruction": c.instruction}
                for c in challenges
            ],
        }

    def process_frame(self, student_id: str, frame: np.ndarray) -> dict:
        """Feed one frame — returns current state + instructions."""

        session = self.sessions.get(student_id)
        if session is None:
            return {"state": "NO_SESSION",
                    "error": "Call create_session first"}

        if session.state in (SessionState.PASSED, SessionState.FAILED):
            return {"state": session.state.value,
                    "fail_reason": session.fail_reason}

        # store small frame for movement analysis
        small = cv2.resize(frame, (160, 120))
        session.movement_frames.append(small)
        if len(session.movement_frames) > 60:
            session.movement_frames = session.movement_frames[-60:]

        # ──── LAYER 1: PASSIVE TEXTURE CHECK (every frame) ────
        face_crop = self._crop_face(frame)
        if face_crop is not None:
            tex = self.texture.analyze(face_crop)
            session.passive_scores.append(tex)

            recent = session.passive_scores[-5:]
            spoof_hits = sum(1 for s in recent if s.get("is_spoof"))

            if len(recent) >= 3 and spoof_hits >= 3:
                session.state = SessionState.FAILED
                session.fail_reason = "SCREEN_OR_PHOTO_DETECTED"
                return {
                    "type": "liveness_result",
                    "state": "FAILED",
                    "fail_reason": "SCREEN_OR_PHOTO_DETECTED",
                    "message": "Photo or screen detected. Please use your real face.",
                }

        # ──── TRANSITION: passive → challenge ────
        if session.state == SessionState.PASSIVE_CHECK:
            if len(session.passive_scores) >= 3:
                session.state = SessionState.CHALLENGING
                ch = session.challenges[0]
                ch.state = ChallengeState.ACTIVE
                ch.started_at = time.time()

        # ──── LAYER 2: ACTIVE CHALLENGES ────
        if session.state == SessionState.CHALLENGING:
            ch = session.current_challenge
            if ch is None or ch.state != ChallengeState.ACTIVE:
                return {"type": "liveness_update", "state": session.state.value,
                        "message": "Waiting..."}

            # timeout
            if ch.is_timed_out:
                session.state = SessionState.FAILED
                session.fail_reason = f"TIMEOUT_{ch.type.value}"
                return {
                    "type": "liveness_result",
                    "state": "FAILED",
                    "fail_reason": session.fail_reason,
                    "message": f"Timed out on: {ch.instruction}",
                }

            metrics = self.detector.extract_metrics(frame)
            if metrics is None:
                return {
                    "type": "liveness_update",
                    "state": "CHALLENGING",
                    "current_challenge": ch.type.value,
                    "instruction": "Face not visible — look at the camera",
                    "progress": session.progress,
                    "time_remaining": round(ch.time_remaining, 1),
                }

            passed = self.detector.check(metrics, ch, session)

            if passed:
                ch.state = ChallengeState.COMPLETED
                ch.completed_at = time.time()
                session.current_challenge_idx += 1
                session.reset_action_state()

                if session.all_challenges_done:
                    # ──── LAYER 3: MICRO-MOVEMENT ────
                    mv = self.movement.analyze(session.movement_frames)

                    if not mv.get("natural", True):
                        session.state = SessionState.FAILED
                        session.fail_reason = "UNNATURAL_MOVEMENT"
                        return {
                            "type": "liveness_result",
                            "state": "FAILED",
                            "fail_reason": "UNNATURAL_MOVEMENT",
                            "message": "Unnatural movement detected. Are you using a screen?",
                        }

                    session.state = SessionState.PASSED
                    return {
                        "type": "liveness_result",
                        "state": "PASSED",
                        "message": "Liveness verified",
                        "progress": session.progress,
                    }

                # activate next challenge (not applicable since it's only blink now, but keeps loop safe)
                nxt = session.current_challenge
                nxt.state = ChallengeState.ACTIVE
                nxt.started_at = time.time()

                return {
                    "type": "liveness_update",
                    "state": "CHALLENGING",
                    "prev_completed": ch.type.value,
                    "current_challenge": nxt.type.value,
                    "instruction": nxt.instruction,
                    "progress": session.progress,
                    "time_remaining": nxt.timeout,
                }

            # still in progress — send feedback
            feedback = {
                "ear":   round(metrics["ear"], 3),
                "yaw":   round(metrics["yaw"], 1),
                "pitch": round(metrics["pitch"], 1),
                "mar":   round(metrics["mar"], 3),
            }
            if ch.type == ChallengeType.BLINK:
                feedback["blinks_detected"] = session.blink_count
                feedback["blinks_needed"]   = session.REQUIRED_BLINKS

            return {
                "type": "liveness_update",
                "state": "CHALLENGING",
                "current_challenge": ch.type.value,
                "instruction": ch.instruction,
                "progress": session.progress,
                "time_remaining": round(ch.time_remaining, 1),
                "feedback": feedback,
            }

        # still in passive check
        return {
            "type": "liveness_update",
            "state": "PASSIVE_CHECK",
            "message": "Analysing face texture...",
            "frames_analysed": len(session.passive_scores),
        }

    # ---- helpers ----

    def _crop_face(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Quick Haar-cascade crop — just for texture analysis."""
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.3, 5, minSize=(80, 80))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        pad = int(max(w, h) * 0.2)
        fh, fw = frame.shape[:2]
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(fw, x + w + pad)
        y2 = min(fh, y + h + pad)
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size > 0 else None

    def remove_session(self, student_id: str):
        self.sessions.pop(student_id, None)

    def close(self):
        self.detector.close()
        self.sessions.clear()


# ═══════════════════════════════════════════════════════════════════
#  LEGACY — MiniFASNet Passive Liveness Detector
#  Still used by face_verifier.verify_frame() during exam.
#  DO NOT DELETE — the exam-time per-frame spoof check uses this.
# ═══════════════════════════════════════════════════════════════════

class LivenessDetector:
    """Passive single-frame anti-spoof via MiniFASNet."""

    def __init__(self, model_path="anti_spoof/2.7_80x80_MiniFASNetV2.pth"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        try:
            from .anti_spoof.MiniFASNet import MiniFASNetV2
            self.model = MiniFASNetV2(conv6_kernel=(7, 7)).to(self.device)
            full_path = os.path.join(os.path.dirname(__file__), model_path)
            state_dict = torch.load(full_path, map_location=self.device)
            self.model.load_state_dict(state_dict, strict=False)
            self.model.eval()
            logger.info(f"Legacy LivenessDetector (MiniFASNet) loaded on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load MiniFASNet: {e}")
            self.model = None

    def check_liveness(self, face_crop: np.ndarray) -> tuple:
        """Returns (is_real: bool, confidence: float)"""
        if self.model is None or face_crop is None or face_crop.size == 0:
            return True, 1.0

        try:
            img = cv2.resize(face_crop, (80, 80))
            tensor = (torch.from_numpy(img).float()
                      .permute(2, 0, 1).unsqueeze(0).to(self.device))

            with torch.no_grad():
                out = self.model(tensor)
                prob = F.softmax(out, dim=-1).cpu().numpy()[0]
                score = float(prob[1])
                is_real = bool(np.argmax(prob) == 1)
                return is_real, score
        except Exception as e:
            logger.error(f"MiniFASNet inference error: {e}")
            return True, 1.0