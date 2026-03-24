"""
backend/ai_engine/face_verifier.py

Face Verifier — Identity + Anti-Spoofing
==========================================
EXISTING (unchanged, used during exam):
  - verify_frame()       → per-frame AI analysis during exam
  - detect_faces()       → face detection helper
  - extract_embedding()  → embedding extraction helper
  - _compute_similarity()→ cosine similarity

NEW (used during pre-exam identity verification):
  - start_liveness()          → creates active liveness session
  - process_liveness_frame()  → feeds frames through 3-layer check
  - match_after_liveness()    → runs InsightFace match AFTER liveness passes
"""

import cv2
import numpy as np
import logging
from typing import Optional, List
from insightface.app import FaceAnalysis
from .liveness_detector import LivenessDetector, LivenessEngine

logger = logging.getLogger("ai_engine.face")


class FaceVerifier:

    def __init__(self, sim_threshold=0.4, pitch_limit=25, yaw_limit=30):
        logger.info("Initializing FaceVerifier (InsightFace)...")
        self.app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        self.app.prepare(ctx_id=-1, det_size=(640, 640))

        self.sim_threshold = sim_threshold
        self.pitch_limit = pitch_limit
        self.yaw_limit = yaw_limit

        # Legacy passive anti-spoof — used during exam in verify_frame()
        self.liveness = LivenessDetector()

        # NEW: Active 3-layer liveness engine — used during pre-exam verification
        self.liveness_engine = LivenessEngine()

        logger.info("FaceVerifier ready (InsightFace + LivenessDetector + LivenessEngine)")

    # ═══════════════════════════════════════════════════════════════
    #  NEW — Active Liveness Flow (pre-exam identity verification)
    # ═══════════════════════════════════════════════════════════════

    def start_liveness(self, student_id: str) -> dict:
        """
        Step 1: Create a liveness session with random challenges.
        Called when the student connects and begins identity verification.
        Returns challenge list to send to frontend.
        """
        return self.liveness_engine.create_session(student_id)

    def process_liveness_frame(self, student_id: str, frame: np.ndarray) -> dict:
        """
        Step 2: Feed each webcam frame through the 3-layer liveness check.
        Returns current state, challenge instructions, progress, etc.
        Keep calling this until state is PASSED or FAILED.
        """
        return self.liveness_engine.process_frame(student_id, frame)

    def match_after_liveness(self, student_id: str, frame: np.ndarray,
                             baseline_embedding: Optional[np.ndarray]) -> dict:
        """
        Step 3: Called ONLY after liveness state == PASSED.
        Extracts embedding from the live frame and compares against
        the ERP baseline photo embedding.

        Returns a dict with matched, confidence, message.
        """
        # Extract embedding from the live verified frame
        live_faces = self.app.get(frame)
        if not live_faces:
            return {
                "matched": False,
                "confidence": 0.0,
                "message": "No face detected in verification frame.",
            }

        # Take the largest face
        largest = max(live_faces,
                      key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        live_embedding = largest.embedding

        # If no ERP baseline exists → self-enroll
        if baseline_embedding is None:
            return {
                "matched": True,
                "confidence": 0.0,
                "embedding": live_embedding,
                "message": "No ERP photo on file — self-enrolled.",
                "self_enrolled": True,
            }

        # Compare against ERP baseline
        similarity = self._compute_similarity(baseline_embedding, live_embedding)
        matched = similarity >= 0.60  # stricter than exam-time threshold

        logger.info(
            f"Liveness match for {student_id}: sim={similarity:.3f} "
            f"threshold=0.60 matched={matched}"
        )

        return {
            "matched": matched,
            "confidence": round(float(similarity), 4),
            "embedding": live_embedding if matched else None,
            "message": (
                f"Identity verified (match: {similarity:.0%})"
                if matched
                else f"Face does not match college ID photo (sim: {similarity:.2f}). Try again."
            ),
            "self_enrolled": False,
        }

    def cleanup_liveness(self, student_id: str):
        """Remove the liveness session after verification completes."""
        self.liveness_engine.remove_session(student_id)

    # ═══════════════════════════════════════════════════════════════
    #  EXISTING — Unchanged methods used during exam
    # ═══════════════════════════════════════════════════════════════

    def _compute_similarity(self, emb1, emb2):
        """Calculates the cosine similarity between two face embeddings."""
        if emb1 is None or emb2 is None:
            return 0.0
        return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))

    def detect_faces(self, frame: np.ndarray) -> List[dict]:
        """Keep this for fallback compatibility just in case, though verify_frame is main entrypoint."""
        faces = self.app.get(frame)
        result_faces = []
        for face in faces:
            bbox = face.bbox.astype(int)
            h, w = frame.shape[:2]
            x1, y1 = max(0, bbox[0]), max(0, bbox[1])
            x2, y2 = min(w, bbox[2]), min(h, bbox[3])
            result_faces.append({
                "bbox": (x1, y1, x2, y2),
                "confidence": float(face.det_score),
                "crop": frame[y1:y2, x1:x2].copy(),
                "embedding": face.embedding,
                "pose": face.pose
            })
        return result_faces

    def extract_embedding(self, face_data) -> np.ndarray:
        if isinstance(face_data, dict) and "embedding" in face_data:
            return face_data["embedding"]
        faces = self.app.get(face_data)
        if len(faces) > 0:
            return faces[0].embedding
        return np.zeros(512)

    def verify_frame(self, frame: np.ndarray, baseline_embedding: Optional[np.ndarray]) -> dict:
        """Analyzes a single frame using exact ProctorEngine logic."""
        faces = self.app.get(frame)
        num_faces = len(faces)

        # Default state matching ProctorEngine
        report = {
            "face_count": num_faces,
            "face_detected": num_faces > 0,
            "is_absent": False,
            "multiple_people": False,
            "identity_verified": False,
            "is_looking_away": False,
            "is_spoof": False,
            "alerts": [],
            "flags": [],  # For websocket compatibility
            "similarity": 0.0,
            "face_bbox": None,
            "face_crop": None
        }

        # 1. Presence & Multiple People Check
        if num_faces == 0:
            report["is_absent"] = True
            report["alerts"].append("Student left the camera view.")
            report["flags"].append({
                "flag_type": "NO_FACE_DETECTED",
                "severity": "MEDIUM",
                "message": "Student left the camera view.",
                "risk_points": 8
            })
            return report  # Skip the rest if no one is there

        if num_faces > 1:
            report["multiple_people"] = True
            report["alerts"].append("Multiple people detected in the room.")
            report["flags"].append({
                "flag_type": "MULTIPLE_FACES",
                "severity": "CRITICAL",
                "message": "Multiple people detected in the room.",
                "risk_points": 8
            })

        # For identity and pose, we check the primary face (faces[0])
        primary_face = faces[0]

        # Populate old fields for compatibility
        bbox = primary_face.bbox.astype(int)
        h, w = frame.shape[:2]
        x1, y1 = max(0, bbox[0]), max(0, bbox[1])
        x2, y2 = min(w, bbox[2]), min(h, bbox[3])
        report["face_bbox"] = (x1, y1, x2, y2)
        report["face_crop"] = frame[y1:y2, x1:x2].copy()

        # 1.5 Liveness Detection (Anti-Spoofing Check) — legacy passive
        is_real, liveness_score = self.liveness.check_liveness(report["face_crop"])
        report["liveness_score"] = liveness_score

        if not is_real:
            report["is_spoof"] = True
            report["alerts"].append(f"Spoofing detected! (Fake face / Photo) [score: {liveness_score:.2f}]")
            report["flags"].append({
                "flag_type": "IDENTITY_MISMATCH",
                "severity": "CRITICAL",
                "message": f"Presentation Attack Detected (Spoofing). Please ensure you are a physical person.",
                "risk_points": 50
            })
            return report

        # 2. Identity Check
        if baseline_embedding is not None:
            similarity = self._compute_similarity(baseline_embedding, primary_face.embedding)
            report["similarity"] = similarity

            if similarity > self.sim_threshold:
                report["identity_verified"] = True
                report["identity_match"] = True
            else:
                report["alerts"].append("Identity mismatch. Unknown person detected.")
                report["flags"].append({
                    "flag_type": "IDENTITY_MISMATCH",
                    "severity": "CRITICAL",
                    "message": "Identity mismatch. Unknown person detected.",
                    "risk_points": 30
                })

        # 3. Head Pose Tracking
        pitch, yaw, roll = primary_face.pose
        report["pose"] = {"pitch": float(pitch), "yaw": float(yaw), "roll": float(roll)}

        if abs(yaw) > self.yaw_limit or abs(pitch) > self.pitch_limit:
            report["is_looking_away"] = True
            report["alerts"].append("Student is looking away from the screen.")
            report["flags"].append({
                "flag_type": "GAZE_AWAY_SUSTAINED",
                "severity": "MEDIUM",
                "message": "Student is looking away from the screen.",
                "risk_points": 10
            })

        return report