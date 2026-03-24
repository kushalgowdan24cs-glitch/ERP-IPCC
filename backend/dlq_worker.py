import os
import asyncio
import logging
import json
from datetime import datetime
import httpx
import asyncpg

# ─── CONFIGURATION ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DLQ_Worker")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:supersecretpassword@localhost:5435/proctorshield")
ERP_WEBHOOK_URL = os.getenv("ERP_WEBHOOK_URL", "http://localhost:8080/api/v1/exam-results")

# Maximum times to retry before triggering a critical admin alert
MAX_RETRIES = 5 

async def process_dlq():
    """
    Scans the webhook_dlq table for unresolved webhooks where the retry timer has elapsed.
    """
    logger.info("DLQ Worker started. Connecting to database...")
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"DLQ could not connect to database: {e}")
        return

    async with httpx.AsyncClient() as client:
        while True:
            try:
                # 1. Fetch pending webhooks that are due for a retry
                pending_tasks = await conn.fetch(
                    """
                    SELECT id, session_id, payload, retry_count 
                    FROM webhook_dlq 
                    WHERE resolved = FALSE AND next_retry_at <= NOW()
                    LIMIT 50
                    """
                )

                for task in pending_tasks:
                    dlq_id = task['id']
                    session_id = task['session_id']
                    payload_json = json.loads(task['payload'])
                    retry_count = task['retry_count'] + 1

                    logger.info(f"Retrying Webhook for Session {session_id} (Attempt {retry_count}/{MAX_RETRIES})")

                    # 2. Attempt to send to Java ERP
                    success = False
                    status_code = 500
                    try:
                        response = await client.post(ERP_WEBHOOK_URL, json=payload_json, timeout=10.0)
                        status_code = response.status_code
                        if status_code in [200, 201, 202]:
                            success = True
                    except Exception as e:
                        logger.warning(f"ERP Connection failed: {e}")

                    # 3. Handle the Result within a Transaction
                    async with conn.transaction():
                        if success:
                            # Mark as resolved and update the main exam session state
                            await conn.execute("UPDATE webhook_dlq SET resolved = TRUE, http_status = $1 WHERE id = $2", status_code, dlq_id)
                            await conn.execute("UPDATE exam_sessions SET state = 'ARCHIVED', erp_webhook_sent = TRUE WHERE id = $1", session_id)
                            logger.info(f"✅ Webhook recovery successful for Session {session_id}.")
                        else:
                            # Exponential Backoff: Wait 1m, then 4m, then 9m, etc.
                            delay_minutes = retry_count * retry_count 
                            
                            if retry_count >= MAX_RETRIES:
                                # Stop retrying automatically, requires manual admin intervention
                                logger.error(f"🚨 CRITICAL: Webhook permanently failed for Session {session_id} after {MAX_RETRIES} attempts.")
                                await conn.execute(
                                    "UPDATE webhook_dlq SET retry_count = $1, http_status = $2, next_retry_at = NULL WHERE id = $3",
                                    retry_count, status_code, dlq_id
                                )
                            else:
                                # Schedule next retry
                                await conn.execute(
                                    f"UPDATE webhook_dlq SET retry_count = $1, http_status = $2, next_retry_at = NOW() + INTERVAL '{delay_minutes} minutes' WHERE id = $3",
                                    retry_count, status_code, dlq_id
                                )
                                logger.warning(f"Scheduled next retry in {delay_minutes} minutes.")

            except Exception as e:
                logger.error(f"Unexpected error in DLQ loop: {e}")
            
            # Sleep for 60 seconds before checking the queue again
            await asyncio.sleep(60)

    await conn.close()

if __name__ == "__main__":
    asyncio.run(process_dlq())