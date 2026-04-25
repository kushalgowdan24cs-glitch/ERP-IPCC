# routers/admin_erp.py
# ─────────────────────────────────────────────────────────────────────────────
# RULES:
#   - asyncpg ONLY
#   - request.app.state.db_pool
#   - JWT decoded using SAME ERP_JWT_SECRET
#   - existing routers/admin.py (WebSocket) is NEVER touched
#   - existing tables (exam_sessions, violations) are READ-ONLY here
# ─────────────────────────────────────────────────────────────────────────────

import os
import jwt
import json
import logging
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
bearer = HTTPBearer()

ERP_JWT_SECRET = os.getenv("ERP_JWT_SECRET", "shared-secret-with-java-erp")


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1: JWT dependency — admin only
# ═════════════════════════════════════════════════════════════════════════════

def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    """Validates ERP JWT and confirms role == admin."""
    try:
        payload = jwt.decode(
            credentials.credentials, ERP_JWT_SECRET, algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access only")

    return payload


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2: Pydantic schemas
# ═════════════════════════════════════════════════════════════════════════════

class CreateUserRequest(BaseModel):
    name:        str
    email:       str
    password:    str
    role:        str          # student / teacher / admin
    # student fields
    branch:      Optional[str] = None
    section:     Optional[str] = None
    roll_number: Optional[str] = None
    semester:    Optional[int] = None
    batch_year:  Optional[int] = None
    # teacher fields
    department:  Optional[str] = None
    employee_id: Optional[str] = None


class BlockUserRequest(BaseModel):
    user_id:    str
    is_active:  bool          # False = block, True = unblock


class AssignTeacherRequest(BaseModel):
    course_id:  str
    teacher_id: str


class ToggleExamRequest(BaseModel):
    exam_id:      str
    is_published: bool


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3: USER MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/users")
async def get_all_users(
    request: Request,
    role: Optional[str] = None,          # ?role=student  filter
    current_user: dict = Depends(get_current_admin),
):
    """Returns all users. Optional ?role= filter."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        if role:
            rows = await conn.fetch(
                """
                SELECT
                    u.id, u.name, u.email, u.role, u.is_active, u.created_at,
                    s.branch, s.section, s.roll_number,
                    t.department, t.employee_id
                FROM erp_users u
                LEFT JOIN erp_students s ON s.id = u.id
                LEFT JOIN erp_teachers t ON t.id = u.id
                WHERE u.role = $1::erp_role
                ORDER BY u.created_at DESC
                """,
                role,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    u.id, u.name, u.email, u.role, u.is_active, u.created_at,
                    s.branch, s.section, s.roll_number,
                    t.department, t.employee_id
                FROM erp_users u
                LEFT JOIN erp_students s ON s.id = u.id
                LEFT JOIN erp_teachers t ON t.id = u.id
                ORDER BY u.created_at DESC
                """
            )

    return {
        "total": len(rows),
        "users": [
            {
                "id":          str(r["id"]),
                "name":        r["name"],
                "email":       r["email"],
                "role":        r["role"],
                "is_active":   r["is_active"],
                "created_at":  r["created_at"].isoformat(),
                # student fields
                "branch":      r["branch"],
                "section":     r["section"],
                "roll_number": r["roll_number"],
                # teacher fields
                "department":  r["department"],
                "employee_id": r["employee_id"],
            }
            for r in rows
        ],
    }


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    """Admin creates any user (student / teacher / admin)."""
    import bcrypt

    allowed = {"student", "teacher", "admin"}
    if body.role not in allowed:
        raise HTTPException(400, detail=f"role must be one of {allowed}")

    if body.role == "student" and (not body.branch or not body.section):
        raise HTTPException(400, detail="branch and section required for students")

    pw_hash = bcrypt.hashpw(
        body.password.encode(), bcrypt.gensalt(rounds=12)
    ).decode()

    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        async with conn.transaction():

            exists = await conn.fetchval(
                "SELECT id FROM erp_users WHERE email = $1", body.email
            )
            if exists:
                raise HTTPException(409, detail="Email already registered")

            user_id = await conn.fetchval(
                """
                INSERT INTO erp_users (name, email, password_hash, role)
                VALUES ($1, $2, $3, $4::erp_role)
                RETURNING id
                """,
                body.name, body.email, pw_hash, body.role,
            )

            if body.role == "student":
                await conn.execute(
                    """
                    INSERT INTO erp_students
                        (id, roll_number, branch, section, semester, batch_year)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    """,
                    user_id, body.roll_number, body.branch,
                    body.section, body.semester, body.batch_year,
                )
            elif body.role == "teacher":
                await conn.execute(
                    "INSERT INTO erp_teachers (id, department, employee_id) VALUES ($1,$2,$3)",
                    user_id, body.department, body.employee_id,
                )
            elif body.role == "admin":
                await conn.execute(
                    """
                    INSERT INTO erp_admins (id, is_super_admin)
                    VALUES ($1, FALSE)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    user_id,
                )

    return {"message": "User created", "user_id": str(user_id)}


@router.patch("/users/block")
async def block_or_unblock_user(
    body: BlockUserRequest,
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    """Block (is_active=False) or unblock (is_active=True) any user."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE erp_users SET is_active = $1, updated_at = now() WHERE id = $2",
            body.is_active, UUID(body.user_id),
        )

    if result == "UPDATE 0":
        raise HTTPException(404, detail="User not found")

    action = "unblocked" if body.is_active else "blocked"
    return {"message": f"User {action} successfully"}


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4: COURSE MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/courses")
async def get_all_courses(
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    """All courses with teacher info and exam count."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id          AS course_id,
                c.course_code,
                c.course_name,
                c.credits,
                c.is_active,
                u.name        AS teacher_name,
                u.email       AS teacher_email,
                COUNT(e.id)   AS exam_count
            FROM erp_courses c
            JOIN erp_teachers t ON t.id = c.teacher_id
            JOIN erp_users    u ON u.id = t.id
            LEFT JOIN erp_exams e ON e.course_id = c.id
            GROUP BY c.id, c.course_code, c.course_name, c.credits,
                     c.is_active, u.name, u.email
            ORDER BY c.course_name
            """
        )

    return {
        "total":   len(rows),
        "courses": [
            {
                "course_id":     str(r["course_id"]),
                "course_code":   r["course_code"],
                "course_name":   r["course_name"],
                "credits":       r["credits"],
                "is_active":     r["is_active"],
                "teacher_name":  r["teacher_name"],
                "teacher_email": r["teacher_email"],
                "exam_count":    r["exam_count"],
            }
            for r in rows
        ],
    }


@router.patch("/courses/assign-teacher")
async def assign_teacher_to_course(
    body: AssignTeacherRequest,
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    """Reassign a course to a different teacher."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        # Verify teacher exists
        teacher = await conn.fetchval(
            "SELECT id FROM erp_teachers WHERE id = $1", UUID(body.teacher_id)
        )
        if not teacher:
            raise HTTPException(404, detail="Teacher not found")

        result = await conn.execute(
            "UPDATE erp_courses SET teacher_id = $1 WHERE id = $2",
            UUID(body.teacher_id), UUID(body.course_id),
        )

    if result == "UPDATE 0":
        raise HTTPException(404, detail="Course not found")

    return {"message": "Teacher assigned successfully"}

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5: EXAM MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/exams")
async def get_all_exams(
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    """All exams with submission counts and status."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                e.id            AS exam_id,
                e.exam_code,
                e.title,
                e.exam_type,
                e.target_branch,
                e.target_section,
                e.start_time,
                e.end_time,
                e.is_published,
                c.course_name,
                u.name          AS teacher_name,
                COUNT(sub.id)   AS submission_count,

                -- Live session count from EXISTING table (read-only)
                (
                    SELECT COUNT(*) FROM exam_sessions es
                    WHERE es.exam_code = e.exam_code
                      AND es.state = 'IN_PROGRESS'
                ) AS active_students

            FROM erp_exams e
            JOIN erp_courses  c   ON c.id = e.course_id
            JOIN erp_teachers t   ON t.id = e.created_by
            JOIN erp_users    u   ON u.id = t.id
            LEFT JOIN erp_submissions sub ON sub.exam_id = e.id
            GROUP BY e.id, e.exam_code, e.title, e.exam_type,
                     e.target_branch, e.target_section,
                     e.start_time, e.end_time, e.is_published,
                     c.course_name, u.name
            ORDER BY e.start_time DESC
            """
        )

    return {
        "total": len(rows),
        "exams": [
            {
                "exam_id":          str(r["exam_id"]),
                "exam_code":        r["exam_code"],
                "title":            r["title"],
                "exam_type":        r["exam_type"],
                "target_branch":    r["target_branch"],
                "target_section":   r["target_section"],
                "start_time":       r["start_time"].isoformat(),
                "end_time":         r["end_time"].isoformat(),
                "is_published":     r["is_published"],
                "course_name":      r["course_name"],
                "teacher_name":     r["teacher_name"],
                "submission_count": r["submission_count"],
                "active_students":  r["active_students"],
            }
            for r in rows
        ],
    }


@router.patch("/exams/toggle")
async def toggle_exam_publish(
    body: ToggleExamRequest,
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    """Enable or disable (publish/unpublish) any exam."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE erp_exams SET is_published = $1, updated_at = now() WHERE id = $2",
            body.is_published, UUID(body.exam_id),
        )

    if result == "UPDATE 0":
        raise HTTPException(404, detail="Exam not found")

    state = "published" if body.is_published else "unpublished"
    return {"message": f"Exam {state} successfully"}


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 6: LIVE PROCTORING MONITOR
# Reads EXISTING exam_sessions + violations — never writes to them
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/sessions")
async def get_live_sessions(
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    """
    Live exam session monitor.
    Joins existing exam_sessions with erp_exams + erp_users for full context.
    READ-ONLY — never writes to exam_sessions.
    """
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                es.id           AS session_id,
                es.exam_code,
                es.student_id,
                es.state,
                es.scheduled_at,
                es.identity_at,
                es.livekit_room,

                -- ERP context
                e.title         AS exam_title,
                e.target_branch,
                e.target_section,
                u.name          AS student_name,
                u.email         AS student_email

            FROM exam_sessions es

            -- Join ERP exam via exam_code (app-level relationship)
            LEFT JOIN erp_exams   e ON e.exam_code  = es.exam_code

            -- Join ERP student — exam_sessions.student_id is TEXT
            LEFT JOIN erp_users   u ON u.id::TEXT    = es.student_id

            ORDER BY es.scheduled_at DESC
            LIMIT 500
            """
        )

    return {
        "total":    len(rows),
        "sessions": [
            {
                "session_id":     str(r["session_id"]),
                "exam_code":      r["exam_code"],
                "student_id":     r["student_id"],
                "student_name":   r["student_name"],
                "student_email":  r["student_email"],
                "state":          r["state"],
                "exam_title":     r["exam_title"],
                "target_branch":  r["target_branch"],
                "target_section": r["target_section"],
                "livekit_room":   r["livekit_room"],
                "scheduled_at":   r["scheduled_at"].isoformat() if r["scheduled_at"] else None,
                "identity_at":    r["identity_at"].isoformat()  if r["identity_at"]  else None,
            }
            for r in rows
        ],
    }


@router.get("/violations")
async def get_violations(
    request: Request,
    exam_code:  Optional[str] = None,
    student_id: Optional[str] = None,
    current_user: dict = Depends(get_current_admin),
):
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        filters = ["1=1"]
        params  = []
        idx     = 1
        if exam_code:
            filters.append(f"es.exam_code = ${idx}")
            params.append(exam_code); idx += 1
        if student_id:
            filters.append(f"es.student_id = ${idx}")
            params.append(student_id); idx += 1
        where = "WHERE " + " AND ".join(filters)
        rows = await conn.fetch(
            f"""
            SELECT
                v.id              AS viol_id,
                v.violation_type,
                v.severity::TEXT  AS severity,
                v.confidence,
                v.description,
                v.created_at,
                es.exam_code,
                es.student_id,
                u.name            AS student_name,
                u.email           AS student_email,
                e.title           AS exam_title
            FROM violations v
            JOIN  exam_sessions es ON es.id       = v.session_id
            LEFT JOIN erp_users u  ON u.id::TEXT  = es.student_id
            LEFT JOIN erp_exams e  ON e.exam_code = es.exam_code
            {where}
            ORDER BY v.created_at DESC
            LIMIT 1000
            """,
            *params,
        )
    return {
        "total": len(rows),
        "violations": [
            {
                "id":             r["viol_id"],
                "exam_code":      r["exam_code"],
                "student_id":     r["student_id"],
                "student_name":   r["student_name"],
                "student_email":  r["student_email"],
                "exam_title":     r["exam_title"],
                "violation_type": r["violation_type"],
                "severity":       r["severity"],
                "confidence":     r["confidence"],
                "description":    r["description"],
                "created_at":     r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 7: DASHBOARD SUMMARY
# Single endpoint powering the admin dashboard cards
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def get_admin_dashboard(
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    try:
        pool = request.app.state.db_pool
        async with pool.acquire() as conn:
            # Stats queries with null/missing safety
            total_students    = await conn.fetchval("SELECT COUNT(*) FROM erp_students") or 0
            total_teachers    = await conn.fetchval("SELECT COUNT(*) FROM erp_teachers") or 0
            total_courses     = await conn.fetchval("SELECT COUNT(*) FROM erp_courses") or 0
            total_exams       = await conn.fetchval("SELECT COUNT(*) FROM erp_exams") or 0
            published_exams   = await conn.fetchval("SELECT COUNT(*) FROM erp_exams WHERE is_published = TRUE") or 0
            total_submissions = await conn.fetchval("SELECT COUNT(*) FROM erp_submissions") or 0
            
            pending_eval      = await conn.fetchval(
                "SELECT COUNT(*) FROM erp_submissions WHERE status = 'submitted'::submission_status"
            ) or 0
            
            active_sessions   = await conn.fetchval(
                "SELECT COUNT(*) FROM exam_sessions WHERE state = 'IN_PROGRESS'::exam_state"
            ) or 0
            
            total_violations  = await conn.fetchval("SELECT COUNT(*) FROM violations") or 0

            # Recent Violations Join
            recent_violations = await conn.fetch(
                """
                SELECT
                    v.violation_type,
                    v.severity::TEXT AS severity,
                    v.created_at,
                    es.exam_code,
                    es.student_id,
                    u.name           AS student_name
                FROM violations v
                JOIN  exam_sessions es ON es.id      = v.session_id
                LEFT JOIN erp_users u  ON u.id::TEXT = es.student_id
                ORDER BY v.created_at DESC
                LIMIT 5
                """
            )
            
            # Live Exams Join
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            live_exams = await conn.fetch(
                """
                SELECT e.id, e.exam_code, e.title, e.target_branch, e.target_section,
                       c.course_name
                FROM erp_exams e
                JOIN erp_courses c ON c.id = e.course_id
                WHERE e.is_published = TRUE
                  AND e.start_time  <= $1
                  AND e.end_time    >= $1
                """,
                now,
            )

        return {
            "stats": {
                "total_students":    int(total_students),
                "total_teachers":    int(total_teachers),
                "total_courses":     int(total_courses),
                "total_exams":       int(total_exams),
                "published_exams":   int(published_exams),
                "total_submissions": int(total_submissions),
                "pending_eval":      int(pending_eval),
                "active_sessions":   int(active_sessions),
                "total_violations":  int(total_violations),
            },
            "live_exams": [
                {
                    "exam_id":        str(r["id"]),
                    "exam_code":      r["exam_code"] or "N/A",
                    "title":          r["title"] or "Untitled",
                    "course_name":    r["course_name"] or "Unknown Course",
                    "target_branch":  r["target_branch"] or "All",
                    "target_section": r["target_section"] or "All",
                }
                for r in live_exams
            ],
            "recent_violations": [
                {
                    "exam_code":      r["exam_code"] or "N/A",
                    "student_id":     r["student_id"] or "N/A",
                    "student_name":   r["student_name"] or "Unknown",
                    "violation_type": r["violation_type"] or "Unknown",
                    "severity":       r["severity"] or "LOW",
                    "created_at":     r["created_at"].isoformat() if (r["created_at"] and hasattr(r["created_at"], 'isoformat')) else str(r["created_at"]),
                }
                for r in recent_violations
            ],
        }
    except Exception as e:
        logger.error(f"Dashboard calculation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))





# ═════════════════════════════════════════════════════════════════════════════
# SECTION 8: AUDIT LOG VIEW
# Reads erp_submissions as an audit trail
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/audit")
async def get_audit_log(
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    """Submission-level audit log for all exams."""
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                sub.id              AS submission_id,
                sub.status,
                sub.started_at,
                sub.submitted_at,
                sub.evaluated_at,
                sub.obtained_marks,
                sub.total_marks,
                e.title             AS exam_title,
                e.exam_code,
                u.name              AS student_name,
                u.email             AS student_email,
                t.name              AS evaluated_by_name
            FROM erp_submissions sub
            JOIN erp_exams   e  ON e.id  = sub.exam_id
            JOIN erp_users   u  ON u.id  = sub.student_id
            LEFT JOIN erp_users t ON t.id = sub.evaluated_by
            ORDER BY sub.started_at DESC
            LIMIT 500
            """
        )

    return {
        "total": len(rows),
        "audit": [
            {
                "submission_id":    str(r["submission_id"]),
                "status":           r["status"],
                "exam_title":       r["exam_title"],
                "exam_code":        r["exam_code"],
                "student_name":     r["student_name"],
                "student_email":    r["student_email"],
                "obtained_marks":   float(r["obtained_marks"]) if r["obtained_marks"] else None,
                "total_marks":      float(r["total_marks"])    if r["total_marks"]    else None,
                "evaluated_by":     r["evaluated_by_name"],
                "started_at":       r["started_at"].isoformat()    if r["started_at"]    else None,
                "submitted_at":     r["submitted_at"].isoformat()  if r["submitted_at"]  else None,
                "evaluated_at":     r["evaluated_at"].isoformat()  if r["evaluated_at"]  else None,
            }
            for r in rows
        ],
    }


# ═════════════════════════════════════════════════════════════════════════════
# BRANCH MANAGEMENT (admin only)
# ═════════════════════════════════════════════════════════════════════════════

class BranchRequest(BaseModel):
    name: str
    code: str


@router.get("/branches")
async def get_branches(
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, code, is_active FROM erp_branches ORDER BY name"
        )
    return {
        "branches": [
            {
                "id":        str(r["id"]),
                "name":      r["name"],
                "code":      r["code"],
                "is_active": r["is_active"],
            }
            for r in rows
        ]
    }


@router.post("/branches", status_code=201)
async def create_branch(
    body: BranchRequest,
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    try:
        pool = request.app.state.db_pool
        
        # Extract admin ID from JWT token safely
        admin_id = current_user.get("id") or current_user.get("sub")
        
        if not admin_id:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid token: missing admin ID. Payload={current_user}"
            )
        
        try:
            admin_uuid = UUID(admin_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid admin UUID: {admin_id}, error: {e}")
            raise HTTPException(status_code=400, detail="Invalid admin ID format")
        
        async with pool.acquire() as conn:
            # Check if branch already exists
            exists = await conn.fetchval(
                "SELECT id FROM erp_branches WHERE code = $1",
                body.code.upper()
            )
            if exists:
                raise HTTPException(status_code=409, detail="Branch code already exists")
            
            # Create the branch
            bid = await conn.fetchval(
                """
                INSERT INTO erp_branches (name, code, created_by, is_active)
                VALUES ($1, $2, $3, TRUE)
                RETURNING id
                """,
                body.name, body.code.upper(), admin_uuid,
            )

        return {"message": "Branch created", "branch_id": str(bid)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"BRANCH CREATION ERROR: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




# ═════════════════════════════════════════════════════════════════════════════
# COURSE CREATE (admin)
# ═════════════════════════════════════════════════════════════════════════════

class CreateCourseRequest(BaseModel):
    course_code: str
    course_name: str
    teacher_id:  str
    branch:      str
    semester:    int
    credits:     Optional[int] = None


@router.post("/courses", status_code=201)
async def create_course_admin(
    body: CreateCourseRequest,
    request: Request,
    current_user: dict = Depends(get_current_admin),
):
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        cid = await conn.fetchval(
            """
            INSERT INTO erp_courses
                (course_code, course_name, teacher_id, branch, semester, credits)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            body.course_code, body.course_name,
            UUID(body.teacher_id), body.branch,
            body.semester, body.credits,
        )
    return {"message": "Course created", "course_id": str(cid)}