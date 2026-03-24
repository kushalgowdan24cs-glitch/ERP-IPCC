from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey

# 1. THE CONNECTION (That we know works!)
DATABASE_URL = "postgresql+asyncpg://postgres:2006@localhost:5432/postgres"

# 2. CREATE ENGINE & SESSION
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# 3. THE BLUEPRINTS (This fixes your ImportError)
class ExamSession(Base):
    __tablename__ = "exam_sessions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    student_id = Column(String, index=True)
    exam_id = Column(String, index=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String, default="LOW")
    evidence_url = Column(String, nullable=True)

class ViolationLog(Base):
    __tablename__ = "violation_logs"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("exam_sessions.session_id"))
    flag_type = Column(String)
    description = Column(String)
    timestamp = Column(Float)
    severity = Column(String)
    risk_points = Column(Float)

# 4. STARTUP SCRIPT
async def init_db():
    print("🚀 Booting up the Database Engine...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ SUCCESS: Postgres Database Connected and Tables Built!")