import os
import asyncio
import logging
import json
from datetime import datetime
import asyncpg
from redis.asyncio import Redis

# ─── CONFIGURATION ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProctorEngine")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:supersecretpassword@localhost:5435/proctorshield")

STREAM_IN = "raw_ai_detections"
GROUP_NAME = "logic_swarm"
WORKER_NAME = f"logic_{os.getpid()}"

# ─── TEMPORAL RULES ───
CONSECUTIVE_FRAMES_NEEDED = 3  # Must see the object for 3 seconds straight
COOLDOWN_PERIOD_SECONDS = 15   # Don't spam the DB if they hold the phone for 20 seconds

redis_client = Redis.from_url(REDIS_URL)

# In-memory state tracker for active exams
# Format: { "STU_123": { "phone_count": 2, "last_flagged": 1620000000 } }
student_state = {}

async def setup_redis_group():
    try:
        await redis_client.xgroup_create(STREAM_IN, GROUP_NAME, id="0", mkstream=True)
        logger.info(f"Consumer group '{GROUP_NAME}' ready.")
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            logger.error(f"Redis Group Error: {e}")

async def record_violation(db_pool, student_id, violation_type, severity, timestamp):
    """Saves the confirmed violation to PostgreSQL and updates the risk score."""
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # 1. Get the active session ID for this student
            session = await conn.fetchrow(
                "SELECT id, risk_score FROM exam_sessions WHERE student_id = $1 AND state = 'IN_PROGRESS'",
                student_id
            )
            
            if not session:
                return # Exam is paused or already submitted, ignore late frames
            
            session_id = session['id']
            current_risk = session['risk_score']
            
            # 2. Insert the Violation
            await conn.execute(
                """
                INSERT INTO violations (session_id, violation_type, severity, frame_timestamp, duration_seconds)
                VALUES ($1, $2, $3, $4, $5)
                """,
                session_id, violation_type, severity, float(timestamp), CONSECUTIVE_FRAMES_NEEDED
            )
            
            # 3. Update the Risk Score (+25 points for a phone)
            new_risk = min(current_risk + 25.0, 100.0)
            risk_level = "RED" if new_risk >= 75 else "YELLOW" if new_risk >= 40 else "GREEN"
            
            await conn.execute(
                "UPDATE exam_sessions SET risk_score = $1, risk_level = $2 WHERE id = $3",
                new_risk, risk_level, session_id
            )
            
            # 4. Push to Admin Dashboard WebSockets via Redis Pub/Sub
            alert_payload = {
                "student_id": student_id,
                "violation": violation_type,
                "risk_level": risk_level
            }
            await redis_client.publish("admin_live_alerts", json.dumps(alert_payload))
            logger.warning(f"🚨 CRITICAL VIOLATION LOGGED: {student_id} -> {violation_type}")

async def process_logic_stream(db_pool):
    """Pulls raw detections, applies temporal logic, and flags cheating."""
    while True:
        try:
            # Pull new AI results from Redis
            messages = await redis_client.xreadgroup(
                GROUP_NAME, WORKER_NAME, {STREAM_IN: '>'}, count=50, block=1000
            )

            if not messages:
                continue

            stream_data = messages[0][1]
            pipe = redis_client.pipeline()
            
            for msg_id, data in stream_data:
                student_id = data[b'student_id'].decode('utf-8')
                timestamp = float(data[b'timestamp'].decode('utf-8'))
                has_phone = data[b'yolo_phone_detected'].decode('utf-8') == 'True'
                
                # Initialize student state if missing
                if student_id not in student_state:
                    student_state[student_id] = {"phone_count": 0, "last_flagged": 0.0}
                
                state = student_state[student_id]
                
                # Apply Temporal Logic
                if has_phone:
                    # Is it in cooldown?
                    if timestamp - state["last_flagged"] > COOLDOWN_PERIOD_SECONDS:
                        state["phone_count"] += 1
                        
                        # Did it hit the 3-second threshold?
                        if state["phone_count"] >= CONSECUTIVE_FRAMES_NEEDED:
                            await record_violation(db_pool, student_id, "UNAUTHORIZED_DEVICE_PHONE", "CRITICAL", timestamp)
                            state["phone_count"] = 0 # Reset counter
                            state["last_flagged"] = timestamp # Enter cooldown
                else:
                    # The moment the phone disappears, reset the consecutive counter
                    state["phone_count"] = 0

                # Acknowledge message so it leaves the queue
                pipe.xack(STREAM_IN, GROUP_NAME, msg_id)
            
            await pipe.execute()

        except Exception as e:
            logger.error(f"Logic Engine Error: {e}")
            await asyncio.sleep(1)

async def main():
    await setup_redis_group()
    
    # Spin up the Database Pool for the Logic Engine
    logger.info("Connecting to PostgreSQL...")
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    
    logger.info(f"{WORKER_NAME} is actively hunting for violations...")
    try:
        await process_logic_stream(db_pool)
    finally:
        await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())