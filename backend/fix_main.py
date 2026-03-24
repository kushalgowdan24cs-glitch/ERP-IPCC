content = """import sys
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

# Dashboard - use absolute path
dashboard_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")
dashboard_dir = os.path.abspath(dashboard_dir)
logger.info(f"Looking for dashboard at: {dashboard_dir}")
if os.path.exists(dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")
    logger.info(f"Dashboard mounted successfully")
else:
    logger.warning(f"Dashboard directory not found!")


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
"""

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("main.py updated successfully!")