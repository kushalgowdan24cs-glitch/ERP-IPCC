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


# ── Banned-object snippet for secondary camera ────────────────
def save_banned_object_snippet(session_id, cropped_frame, detection):
    """
    Save a cropped image snippet of a banned object detected on the
    secondary (phone) camera.  Returns a dict with the local filepath
    and the URL that the ERP backend can use to fetch the image.
    """
    session_dir = os.path.join(EVIDENCE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%H%M%S%f")[:9]  # HHMMSSmmm
    class_tag = detection["class_name"].upper().replace(" ", "_")
    conf_pct = round(detection["confidence"] * 100)
    filename = f"{timestamp}_BANNED_{class_tag}_{conf_pct}pct.jpg"
    filepath = os.path.join(session_dir, filename)

    # Annotate the cropped snippet
    annotated = cropped_frame.copy()
    label = f"{detection['class_name']} {conf_pct}%"
    cv2.putText(annotated, label, (4, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.rectangle(annotated, (0, 0),
                  (annotated.shape[1] - 1, annotated.shape[0] - 1),
                  (0, 0, 255), 2)

    cv2.imwrite(filepath, annotated)
    url = f"/api/v1/report/evidence/{session_id}/{filename}"
    logger.info(f"📸 Banned-object snippet saved: {filepath}")

    return {"filepath": filepath, "url": url, "filename": filename}


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
