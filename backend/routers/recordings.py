from fastapi import APIRouter, UploadFile, File, Request, HTTPException, Form
from fastapi.responses import FileResponse
import os
import shutil

router = APIRouter()
RECORDINGS_DIR = "evidence/recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

@router.post("/sessions/{session_id}/recording/snippet")
async def upload_snippet(
    session_id: str, 
    camera_type: str = Form(...),
    flag_type: str = Form(...),
    timestamp: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Receives a 10s WebM video snippet from the student client and saves it to disk.
    Expected form data: camera_type ('main' or 'secondary'), flag_type, timestamp, file
    """
    if camera_type not in ["main", "secondary"]:
        raise HTTPException(status_code=400, detail="Invalid camera_type. Must be 'main' or 'secondary'")
        
    try:
        ts_int = int(float(timestamp))
    except ValueError:
        ts_int = 0
        
    filename = f"{session_id}_{flag_type}_{ts_int}_{camera_type}.webm"
    file_path = os.path.join(RECORDINGS_DIR, filename)
    
    # Save the snippet
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save snippet: {e}")
        
    return {"status": "success", "message": f"Snippet saved", "filename": filename}


@router.get("/sessions/{session_id}/recording/snippet/{filename}")
async def get_snippet(session_id: str, filename: str, request: Request):
    """
    Serves a specific WebM video snippet for playback in the timeline.
    """
    # Ensure filename doesn't contain path traversal
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(RECORDINGS_DIR, safe_filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Snippet not found")
        
    return FileResponse(
        path=file_path,
        media_type="video/webm",
        filename=safe_filename,
        headers={"Accept-Ranges": "bytes"}
    )
