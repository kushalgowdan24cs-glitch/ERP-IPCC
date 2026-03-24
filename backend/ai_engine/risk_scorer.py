"""
Risk scoring engine — aggregates flags into a single risk assessment.
"""

from typing import List, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("ai_engine.risk")


# Flag type → default risk points (can be overridden per-flag)
DEFAULT_RISK_POINTS = {
    "NO_FACE_DETECTED": 3,
    "MULTIPLE_FACES": 8,
    "IDENTITY_MISMATCH": 10,
    "BANNED_OBJECT_CELL_PHONE": 8,
    "BANNED_OBJECT_BOOK": 3,
    "BANNED_OBJECT_LAPTOP": 5,
    "BANNED_OBJECT_TV": 6,
    "MULTIPLE_PERSONS_IN_FRAME": 6,
    "GAZE_AWAY_SUSTAINED": 4,
    "SPEECH_DETECTED": 2,
    "APP_LOST_FOCUS": 7,
    "COPY_PASTE_ATTEMPT": 5,
    "BLOCKED_PROCESS_RUNNING": 8,
    "TAB_SWITCH_ATTEMPT": 6,
    "SUSPICIOUS_SILENCE": 2,
}

SEVERITY_MULTIPLIER = {
    "CRITICAL": 2.0,
    "HIGH": 1.5,
    "MEDIUM": 1.0,
    "LOW": 0.5,
}


class RiskScorer:
    def __init__(self, auto_terminate_threshold: int = 100):
        self.auto_terminate_threshold = auto_terminate_threshold
        # Track recent flags to implement cooldown
        # (don't double-count the same flag type within 30 seconds)
        self.recent_flags: Dict[str, datetime] = {}
        self.cooldown_seconds = 30

    def compute_flag_points(self, flag: dict) -> int:
        """Compute risk points for a single flag."""
        flag_type = flag.get("flag_type", "UNKNOWN")
        severity = flag.get("severity", "MEDIUM")

        # Check cooldown — same flag type within 30 seconds gets reduced points
        now = datetime.utcnow()
        last_seen = self.recent_flags.get(flag_type)

        if last_seen and (now - last_seen) < timedelta(seconds=self.cooldown_seconds):
            # Repeat flag within cooldown — reduced weight
            multiplier = 0.3
        else:
            multiplier = 1.0

        self.recent_flags[flag_type] = now

        base_points = flag.get("risk_points", DEFAULT_RISK_POINTS.get(flag_type, 2))
        severity_mult = SEVERITY_MULTIPLIER.get(severity, 1.0)

        return max(1, int(base_points * severity_mult * multiplier))

    def compute_risk_level(self, total_score: float) -> str:
        if total_score >= 76:
            return "RED"
        elif total_score >= 51:
            return "ORANGE"
        elif total_score >= 26:
            return "YELLOW"
        return "GREEN"

    def should_auto_terminate(self, total_score: float) -> bool:
        return total_score >= self.auto_terminate_threshold

    def generate_recommendation(self, total_score: float, flags: List[dict]) -> str:
        """Generate final recommendation for the ERP."""
        if total_score < 15:
            return "CLEAN"

        critical_flags = [f for f in flags if f.get("severity") == "CRITICAL"]
        if critical_flags or total_score >= 60:
            return "FLAGGED"

        return "REVIEW"