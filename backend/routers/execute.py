import base64
import binascii

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from backend.ai_engine import ai

router = APIRouter(tags=["Execution"])


class CodeExecutionRequest(BaseModel):
    language: str
    code: str
    question_id: int


class ObjectScanRequest(BaseModel):
    image_base64: str


# Official Judge0 v1.13+ Language IDs
LANGUAGE_MAP = {
    "python": 71,
    "cpp": 54,
    "java": 62,
}

# Default port for a local Judge0 Docker container
JUDGE0_URL = "http://localhost:2358"


@router.post("/execute")
async def execute_code(req: CodeExecutionRequest):
    lang_id = LANGUAGE_MAP.get(req.language.lower())
    if not lang_id:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language}")

    # The payload we send to Judge0
    # Note: We are ignoring 'question_id' for this exact moment because we are just testing raw compilation
    payload = {
        "source_code": req.code,
        "language_id": lang_id,
        # Docker Desktop on Windows often lacks the cgroup layout expected by isolate.
        # These flags force Judge0 to use non-cgroup mode and prevent Internal Error.
        "enable_per_process_and_thread_time_limit": True,
        "enable_per_process_and_thread_memory_limit": True,
    }

    try:
        # wait=true tells Judge0 to hold the connection until the code finishes running!
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{JUDGE0_URL}/submissions?base64_encoded=false&wait=true",
                json=payload,
                timeout=15.0,
            )
            response.raise_for_status()
            result = response.json()

    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Could not connect to Judge0. Is Docker running? Error: {exc}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Judge0 returned an error: {exc}")

    # Parse the exact output from the Judge0 sandbox
    status = result.get("status", {}).get("description", "Unknown Error")
    stdout = result.get("stdout")
    stderr = result.get("stderr")
    compile_output = result.get("compile_output")

    output = stdout if stdout else ""
    error = stderr if stderr else compile_output if compile_output else ""

    # Return it in the exact JSON format your React frontend is expecting
    if status == "Accepted":
        return {"output": output, "status": status}

    # If it's a compile error, runtime error, or timeout, send it back as an error
    return {"error": f"Status: {status}\n\n{error}", "status": status}


@router.post("/proctor/object-scan")
async def object_scan(req: ObjectScanRequest):
    image_data = req.image_base64.strip()
    if not image_data:
        raise HTTPException(status_code=400, detail="image_base64 is required")

    # Accept both raw base64 and data URL forms.
    if image_data.startswith("data:"):
        parts = image_data.split(",", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid data URL image payload")
        image_data = parts[1]

    try:
        image_bytes = base64.b64decode(image_data, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="Invalid base64 image payload")

    nparr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Unable to decode image")

    detector = ai.ensure_object_detector()

    try:
        # Very strict mode: lower confidence to catch brief/partial appearances.
        result = detector.detect(frame, confidence=0.08)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Object detection failed: {exc}")

    banned_labels = {"cell phone", "laptop"}
    banned_class_ids = {67, 63}
    detected_banned = [
        obj
        for obj in result.get("objects", [])
        if obj.get("class_name") in banned_labels or obj.get("class_id") in banned_class_ids
    ]

    return {
        "detected": detected_banned,
        "flags": [
            {
                "object": obj.get("class_name"),
                "confidence": obj.get("confidence"),
            }
            for obj in detected_banned
        ],
    }
