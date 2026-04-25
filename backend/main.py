import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncpg

from backend.routers.erp_auth import router as erp_auth_router
from backend.routers.student import router as student_router
from backend.routers.teacher import router as teacher_router
from backend.routers.admin_erp import router as admin_erp_router
from backend.routers.admin import router as admin_router
from backend.routers.websocket_handler import router as websocket_router
#import our secure enterprise routers
from backend.routers import auth, exam, telemetry, execute
# ─── LOGGING SETUP ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:supersecretpassword@localhost:5435/proctorshield")

# ─── LIFESPAN MANAGER (Enterprise Startup/Shutdown) ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: Create a resilient Database Connection Pool
    # min_size=5 keeps connections warm. max_size=20 prevents DB overwhelming.
    logger.info("Initializing PostgreSQL Connection Pool...")
    try:
        app.state.db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
        logger.info("Database Pool Ready. System Online.")
    except Exception as e:
        logger.error(f"Failed to initialize Database Pool: {e}")
        raise e
    
    yield # App runs here
    
    # SHUTDOWN: Cleanly close the pool
    logger.info("Closing PostgreSQL Connection Pool...")
    if hasattr(app.state, 'db_pool'):
        await app.state.db_pool.close()

# ─── APP INITIALIZATION ───
app = FastAPI(title="ProctorShield Enterprise API", lifespan=lifespan)

# ─── CORS CONFIGURATION (Crucial for Tauri/React) ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Note: In production, change this to your exact Tauri/React domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── ROUTER WIRING ───
# This connects all the logic we just built into the main server
app.include_router(auth.router)
app.include_router(exam.router)
app.include_router(telemetry.router) 
app.include_router(execute.router, prefix="/api/v1")
app.include_router(student_router)
app.include_router(teacher_router)
app.include_router(admin_erp_router)
app.include_router(admin_router)
app.include_router(websocket_router)

app.include_router(erp_auth_router)

student_photos_dir = Path(__file__).resolve().parent / "student_photos"
if student_photos_dir.exists():
    app.mount("/student_photos", StaticFiles(directory=str(student_photos_dir)), name="student_photos")

# ─── FRONTEND STATIC FILES ───
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/frontend", StaticFiles(directory=str(frontend_dir)), name="frontend")

# ─── HEALTH CHECK ───
@app.get("/health")
async def health_check():
    return {"status": "Enterprise Core is Online", "version": "1.0.0"}

# ─── METRICS SILENCER ───
@app.get("/metrics")
async def dummy_metrics():
    """Silences Docker/Prometheus scrapers looking for metrics."""
    return Response(content="metrics_silenced=1", media_type="text/plain")

# ─── LIVEKIT WEBHOOK RECEIVER ───
# LiveKit will automatically hit this endpoint when a student disconnects or an egress video finishes saving.
@app.post("/api/v1/livekit/webhook")
async def livekit_webhook(request: Request):
    body = await request.body()
    # In the future, you can parse the LiveKit event here (e.g., 'egress_ended') 
    # to update the database with the exact MinIO video URL.
    logger.info("Received LiveKit Webhook Event.")
    return {"status": "received"}