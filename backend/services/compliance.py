"""
Pillar 12: The Automated Janitor (GDPR/DPDP Compliance)

Enterprise systems do not keep biometric data forever.
This module runs daily at 3:00 AM to purge personal data older than 30 days.
"""
import asyncio
from datetime import datetime, timedelta
from typing import List
import logging
from sqlalchemy import select, update
from database import AsyncSessionLocal, ExamSession
from services.storage_service import s3_client, BUCKET_NAME

logger = logging.getLogger("proctorshield.compliance")

RETENTION_DAYS = 30  # Configurable retention period


async def daily_data_purge():
    """
    Runs at 3 AM daily. Deletes all biometric and video data older than 30 days.
    Keeps anonymized analytics (risk scores) but removes PII.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    logger.info(f"🧹 Starting daily data purge. Cutoff date: {cutoff_date}")
    
    try:
        async with AsyncSessionLocal() as db:
            # 1. Find all completed exams older than 30 days
            result = await db.execute(
                select(ExamSession).where(
                    ExamSession.completed_at < cutoff_date,
                    ExamSession.status == "completed"
                )
            )
            old_sessions = result.scalars().all()
            
            purged_count = 0
            for session in old_sessions:
                try:
                    # 2. Delete the video file from MinIO (1GB+ per exam)
                    video_key = f"{session.session_id}_full_recording.mp4"
                    try:
                        s3_client.delete_object(Bucket=BUCKET_NAME, Key=video_key)
                        logger.info(f"🗑️ Deleted video: {video_key}")
                    except Exception as e:
                        logger.warning(f"Failed to delete video {video_key}: {e}")
                    
                    # 3. Anonymize the Postgres record
                    # Keep risk score for analytics, but remove PII
                    await db.execute(
                        update(ExamSession)
                        .where(ExamSession.id == session.id)
                        .values(
                            student_id="REDACTED",
                            student_name="REDACTED",
                            face_baseline=None,  # Delete biometric templates
                            voice_baseline=None,
                            answers=None,  # Delete exam answers
                            exam_data=None,  # Delete exam content
                        )
                    )
                    
                    logger.info(f"✅ Anonymized session: {session.session_id}")
                    purged_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to purge session {session.session_id}: {e}")
            
            await db.commit()
            logger.info(f"🧹 Purge complete. Anonymized {purged_count} sessions older than {cutoff_date}")
            
    except Exception as e:
        logger.error(f"Critical error during data purge: {e}")


async def purge_scheduler():
    """
    Background task that schedules the daily purge at 3:00 AM.
    Runs continuously in the background.
    """
    logger.info("🕐 Compliance purge scheduler started. Runs daily at 3:00 AM.")
    
    while True:
        now = datetime.utcnow()
        # Calculate next 3 AM
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        
        sleep_seconds = (next_run - now).total_seconds()
        logger.info(f"⏳ Next purge scheduled for {next_run} (in {sleep_seconds/3600:.1f} hours)")
        
        await asyncio.sleep(sleep_seconds)
        
        # Run the purge
        try:
            await daily_data_purge()
        except Exception as e:
            logger.error(f"Scheduled purge failed: {e}")
        
        # Sleep briefly to avoid multiple runs in the same minute
        await asyncio.sleep(60)
