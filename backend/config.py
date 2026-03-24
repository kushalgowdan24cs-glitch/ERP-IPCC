from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "ProctorShield"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Switch to Postgres for bulletproof, multi-worker-safe state
    DATABASE_URL: str = "postgresql+asyncpg://admin:supersecretpassword@localhost:5432/proctorshield"

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

    # ── Banned-object detection (secondary camera) ──
    ERP_WEBHOOK_URL: str = "http://localhost:9090/api/proctoring/violations"
    BANNED_OBJECT_CONFIDENCE: float = 0.75
    BANNED_OBJECT_COOLDOWN: float = 30.0

    # ── LiveKit Media Server ──
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "your-super-secret-key-that-is-long-enough-for-sha256-crypto"
    LIVEKIT_URL: str = "ws://127.0.0.1:7880"

    class Config:
        env_file = ".env"


settings = Settings()

settings.RECORDINGS_DIR.mkdir(exist_ok=True)
settings.FRAMES_DIR.mkdir(exist_ok=True)
