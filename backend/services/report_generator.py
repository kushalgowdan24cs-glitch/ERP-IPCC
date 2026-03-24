import json
import os
from datetime import datetime
from config import settings
import logging

logger = logging.getLogger("reports")

REPORTS_DIR = os.path.join(str(settings.BASE_DIR), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def generate_report(session, evidence_files=None):
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "session": {
            "session_id": session.session_id,
            "session_code": session.session_code,
            "student_id": session.student_id,
            "student_name": session.student_name,
            "exam_id": session.exam_id,
            "exam_title": session.exam_title,
            "status": session.status,
            "started_at": session.started_at.isoformat() if session.started_at else None,
        },
        "risk_assessment": {
            "final_score": round(session.risk_score, 1),
            "risk_level": session.risk_level,
            "recommendation": get_recommendation(session.risk_score, session.flags),
            "total_flags": len(session.flags),
        },
        "flag_breakdown": {
            "CRITICAL": [],
            "HIGH": [],
            "MEDIUM": [],
            "LOW": [],
        },
        "answers": session.answers,
        "evidence_count": len(evidence_files) if evidence_files else 0,
    }

    for flag in session.flags:
        severity = flag.get("severity", "LOW")
        if severity in report["flag_breakdown"]:
            report["flag_breakdown"][severity].append({
                "type": flag.get("flag_type"),
                "message": flag.get("message"),
                "timestamp": flag.get("timestamp"),
                "risk_points": flag.get("risk_points", 0),
            })

    # Save to file
    filepath = os.path.join(REPORTS_DIR, f"{session.session_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved: {filepath}")
    return report


def get_recommendation(score, flags):
    critical = sum(1 for f in flags if f.get("severity") == "CRITICAL")
    if score < 15 and critical == 0:
        return "CLEAN"
    elif score >= 60 or critical >= 3:
        return "FLAGGED"
    else:
        return "REVIEW"
