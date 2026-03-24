"""
Object detection using YOLOv8.
Detects phones, books, additional screens, and other banned items.
"""

import numpy as np
from ultralytics import YOLO
from typing import List
import logging

logger = logging.getLogger("ai_engine.objects")

# COCO class IDs we care about
BANNED_OBJECTS = {
    67: ("cell phone", "CRITICAL", 8),
    73: ("book", "MEDIUM", 3),
    63: ("laptop", "HIGH", 5),         # second laptop
    62: ("tv", "HIGH", 6),             # external monitor/screen
    74: ("clock", "LOW", 0),           # not banned, just noted
    0:  ("person", "INFO", 0),         # tracked separately
    64: ("mouse", "LOW", 0),
    66: ("keyboard", "LOW", 0),
}

ALERT_CLASSES = {67, 73, 63, 62}  # Classes that trigger flags


class ObjectDetector:
    def __init__(self, model_name: str = "yolov8n.pt"):
        self.model = YOLO(model_name)
        self.model.fuse()
        logger.info(f"YOLOv8 loaded: {model_name}")

    def detect(self, frame: np.ndarray, confidence: float = 0.50) -> dict:
        """
        Run object detection on a frame.
        Returns detected objects and any flags.
        """
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

                if cls_id == 0:  # person
                    person_count += 1

                obj_info = {
                    "class_id": cls_id,
                    "class_name": class_name,
                    "confidence": round(conf, 3),
                    "bbox": [int(b) for b in bbox],
                }
                detected_objects.append(obj_info)

                # Check if this is a banned object
                if cls_id in ALERT_CLASSES:
                    label, severity, risk_points = BANNED_OBJECTS[cls_id]
                    flags.append({
                        "flag_type": f"BANNED_OBJECT_{class_name.upper().replace(' ', '_')}",
                        "severity": severity,
                        "message": f"Detected: {class_name} (confidence: {conf:.0%})",
                        "risk_points": risk_points,
                        "details": {"object": class_name, "confidence": conf, "bbox": bbox},
                    })

        # Flag if more than 1 person detected (by object detector)
        if person_count > 1:
            flags.append({
                "flag_type": "MULTIPLE_PERSONS_IN_FRAME",
                "severity": "HIGH",
                "message": f"{person_count} people detected in frame",
                "risk_points": 6,
            })

        return {
            "objects": detected_objects,
            "person_count": person_count,
            "flags": flags,
        }