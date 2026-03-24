import os
import jwt
import time
import logging
from fastapi import FastAPI, Request
from pydantic import BaseModel

# ─── CONFIGURATION ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Mock_Java_ERP")

# This must match the secret in your main backend .env
ERP_JWT_SECRET = os.getenv("ERP_JWT_SECRET", "shared-secret-with-java-erp")

app = FastAPI(title="Mock College Java ERP")

# ─── 1. THE TOKEN GENERATOR (For Your Pitch Demo) ───
@app.get("/generate-token/{student_id}/{exam_code}")
async def generate_mock_token(student_id: str, exam_code: str):
    """
    Run this in your browser before your demo to get a valid JWT.
    Paste the resulting token into your React App's login screen.
    """
    payload = {
        "sub": student_id,
        "name": "Demo Student",
        "exam_code": exam_code,
        "exp": int(time.time()) + 3600 # Expires in 1 hour
    }
    
    token = jwt.encode(payload, ERP_JWT_SECRET, algorithm="HS256")
    
    return {
        "student_id": student_id,
        "exam_code": exam_code,
        "copy_this_token": token
    }

# ─── 2. THE WEBHOOK CATCHER ───
@app.post("/api/v1/exam-results")
async def receive_exam_results(request: Request):
    """
    When the student clicks 'Submit', your FastAPI server will send the final 
    grade and video evidence here. This proves to the judges that the system works.
    """
    payload = await request.json()
    
    logger.info("==================================================")
    logger.info("🎓 THE JAVA ERP RECEIVED THE FINAL EXAM RESULTS 🎓")
    logger.info("==================================================")
    logger.info(f"Student: {payload.get('student_id')}")
    logger.info(f"Trust Score: {payload.get('trust_score')}/100")
    logger.info(f"Risk Level: {payload.get('risk_level')}")
    logger.info(f"Total Violations: {payload.get('violations_count')}")
    logger.info(f"Evidence URL: {payload.get('video_evidence_url')}")
    logger.info("==================================================")
    
    return {"status": "success", "message": "Grade saved in Java ERP"}

if __name__ == "__main__":
    import uvicorn
    # Notice we run this on port 8080! 
    # Your main ProctorShield server runs on 8000.
    uvicorn.run(app, host="0.0.0.0", port=8080)