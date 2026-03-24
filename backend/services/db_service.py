from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy import select

from database import AsyncSessionLocal, ExamSession, ViolationLog


async def save_or_update_session(session_data: Dict[str, Any]) -> None:
    """Upserts the exam session into Postgres."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ExamSession).where(
                ExamSession.session_id == session_data["session_id"]
            )
        )
        db_session = result.scalars().first()

        if not db_session:
            db_session = ExamSession(**session_data)
            db.add(db_session)
        else:
            for key, value in session_data.items():
                setattr(db_session, key, value)

        await db.commit()


async def save_violation(session_id: str, flag: Dict[str, Any]) -> None:
    """Saves a single AI violation event to Postgres and updates risk score."""
    async with AsyncSessionLocal() as db:
        new_violation = ViolationLog(
            session_id=session_id,
            flag_type=flag.get("flag_type"),
            severity=flag.get("severity", "MEDIUM"),
            risk_points=flag.get("risk_points", 0.0),
            timestamp=flag.get("timestamp", datetime.utcnow().timestamp()),
            evidence_url=flag.get("evidence_url"),
        )
        db.add(new_violation)

        # Recalculate and update the total risk score for the session
        result = await db.execute(
            select(ExamSession).where(ExamSession.session_id == session_id)
        )
        db_session = result.scalars().first()
        if db_session:
            db_session.risk_score += float(flag.get("risk_points", 0.0))

            # Simple risk bucket logic as a backup (your ai.risk is primary)
            if db_session.risk_score >= 100:
                db_session.risk_level = "RED"
            elif db_session.risk_score >= 50:
                db_session.risk_level = "ORANGE"

        await db.commit()


async def get_all_sessions() -> List[Dict[str, Any]]:
    """Return a simple list of all sessions for history endpoints."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ExamSession).order_by(ExamSession.started_at.desc()))
        sessions = result.scalars().all()

        payload: List[Dict[str, Any]] = []
        for s in sessions:
            payload.append(
                {
                    "session_id": s.session_id,
                    "student_id": s.student_id,
                    "exam_id": s.exam_id,
                    "status": s.status,
                    "risk_score": s.risk_score,
                    "risk_level": s.risk_level,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
            )
        return payload


async def get_session_report(session_id: str) -> Dict[str, Any] | None:
    """Return a basic session report + all violation logs."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ExamSession).where(ExamSession.session_id == session_id)
        )
        s = result.scalars().first()
        if not s:
            return None

        v_result = await db.execute(
            select(ViolationLog).where(ViolationLog.session_id == session_id).order_by(
                ViolationLog.timestamp
            )
        )
        violations = v_result.scalars().all()

        events = [
            {
                "flag_type": v.flag_type,
                "severity": v.severity,
                "risk_points": v.risk_points,
                "timestamp": v.timestamp,
                "evidence_url": v.evidence_url,
            }
            for v in violations
        ]

        return {
            "session": {
                "session_id": s.session_id,
                "student_id": s.student_id,
                "exam_id": s.exam_id,
                "status": s.status,
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            },
            "events": events,
            "answers": [],  # Answers table not yet modeled in Postgres version
            "summary": {
                "total_flags": len(events),
                "critical_flags": sum(
                    1 for e in events if e["severity"] == "CRITICAL"
                ),
                "high_flags": sum(1 for e in events if e["severity"] == "HIGH"),
                "medium_flags": sum(1 for e in events if e["severity"] == "MEDIUM"),
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
            },
        }


async def save_admin_audit_log(audit_entry: Dict[str, Any]) -> None:
    """Saves admin intervention actions for legal compliance and audit trails."""
    from models import AdminAuditLog
    async with AsyncSessionLocal() as db:
        log = AdminAuditLog(
            session_id=audit_entry["session_id"],
            admin_id=audit_entry.get("admin_id", "SYSTEM"),
            action=audit_entry["action"],
            message=audit_entry.get("message", ""),
            ip_address=audit_entry.get("ip_address"),
            timestamp=audit_entry.get("timestamp", datetime.utcnow())
        )
        db.add(log)
        await db.commit()


# ═══════════════════════════════════════════════════════════════
#  BACKWARD COMPATIBILITY ALIASES
#  (Maps old function names to new ones)
# ═══════════════════════════════════════════════════════════════

async def save_session_to_db(data):
    """Legacy alias: Maps old save_session_to_db to new save_or_update_session."""
    return await save_or_update_session(data)


async def save_event_to_db(session_id, event):
    """Legacy alias: Maps old save_event_to_db to new save_violation."""
    # This maps the old event system to the new violation system
    return await save_violation(session_id, event)


async def save_answer_to_db(session_id, answer):
    """Legacy alias: Placeholder for old save_answer_to_db.
    
    For now, we just pass since we are focusing on proctoring.
    Answer storage is handled separately or will be implemented later.
    """
    pass
