# routers/student.py
# ─────────────────────────────────────────────────────────────────────────────
# RULES:
#   - asyncpg ONLY  (no SQLAlchemy)
#   - request.app.state.db_pool  (same pattern as auth.py)
#   - JWT decoded using SAME ERP_JWT_SECRET from auth.py
#   - student_id always taken from JWT ("sub" claim) — NEVER from request body
#   - DO NOT modify exam_sessions, violations, or any existing table
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/student", tags=["student"])
bearer = HTTPBearer()

# Reuse the SAME secret your existing auth.py uses
ERP_JWT_SECRET = os.getenv("ERP_JWT_SECRET", "shared-secret-with-java-erp")


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1: JWT dependency
# ═════════════════════════════════════════════════════════════════════════════

def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    """Validates ERP JWT and confirms role == student."""
    try:
        payload = jwt.decode(
            credentials.credentials, ERP_JWT_SECRET, algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student access only")

    return payload


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2: Pydantic schemas
# ═════════════════════════════════════════════════════════════════════════════

class StartExamRequest(BaseModel):
    exam_id: str

class SubmitExamRequest(BaseModel):
    exam_id: str
    answers: dict   # { "<question_uuid>": <answer_data_dict> }


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3: Internal helper
# ═════════════════════════════════════════════════════════════════════════════

async def fetch_student_profile(conn, student_id: str) -> dict:
    row = await conn.fetchrow(
        """
        SELECT u.id, u.name, u.email,
               s.branch, s.section, s.roll_number, s.semester, s.batch_year
        FROM erp_users    u
        JOIN erp_students s ON s.id = u.id
        WHERE u.id = $1 AND u.is_active = TRUE
        """,
        UUID(student_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return dict(row)


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4: GET /student/courses
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/courses")
async def get_student_courses(
    request: Request,
    current_user: dict = Depends(get_current_student),
):
    pool = request.app.state.db_pool
    student_id = current_user["sub"]

    async with pool.acquire() as conn:
        profile = await fetch_student_profile(conn, student_id)

        rows = await conn.fetch(
            """
            SELECT DISTINCT
                c.id          AS course_id,
                c.course_code,
                c.course_name,
                c.credits,
                u.name        AS teacher_name
            FROM erp_courses c
            JOIN erp_teachers t ON t.id = c.teacher_id
            JOIN erp_users    u ON u.id = t.id
            WHERE EXISTS (
                SELECT 1 FROM erp_exams e
                WHERE e.course_id      = c.id
                  AND e.target_branch  = $1
                  AND e.target_section = $2
                  AND e.is_published   = TRUE
            )
            ORDER BY c.course_name
            """,
            profile["branch"],
            profile["section"],
        )

    return {
        "branch":  profile["branch"],
        "section": profile["section"],
        "courses": [
            {
                "course_id":    str(r["course_id"]),
                "course_code":  r["course_code"],
                "course_name":  r["course_name"],
                "credits":      r["credits"],
                "teacher_name": r["teacher_name"],
            }
            for r in rows
        ],
    }


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5: GET /student/exams
# Exam cards filtered to student's branch + section
# Also reads exam_sessions (existing table) for proctoring state — READ ONLY
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/exams")
async def get_student_exams(
    request: Request,
    current_user: dict = Depends(get_current_student),
):
    pool = request.app.state.db_pool
    student_id = current_user["sub"]

    async with pool.acquire() as conn:
        profile = await fetch_student_profile(conn, student_id)

        rows = await conn.fetch(
            """
            SELECT
                e.id              AS exam_id,
                e.exam_code,
                e.title,
                e.description,
                e.exam_type,
                e.duration_mins,
                e.total_marks,
                e.start_time,
                e.end_time,
                c.course_name,
                c.course_code,
                u.name            AS teacher_name,

                -- ERP submission status
                sub.status        AS submission_status,
                sub.obtained_marks,
                sub.percentage,

                -- Proctoring state from EXISTING table (read-only)
                es.state          AS session_state

            FROM erp_exams e
            JOIN erp_courses  c   ON c.id  = e.course_id
            JOIN erp_teachers t   ON t.id  = e.created_by
            JOIN erp_users    u   ON u.id  = t.id

            LEFT JOIN erp_submissions sub
                   ON sub.exam_id    = e.id
                  AND sub.student_id = $1

            -- exam_sessions.student_id is TEXT in existing schema
            LEFT JOIN exam_sessions es
                   ON es.exam_code  = e.exam_code
                  AND es.student_id = $2

            WHERE e.target_branch   = $3
              AND e.target_section  = $4
              AND e.is_published    = TRUE
            ORDER BY e.start_time DESC
            """,
            UUID(student_id),
            student_id,           # TEXT cast for exam_sessions join
            profile["branch"],
            profile["section"],
        )

    return {
        "exams": [
            {
                "exam_id":           str(r["exam_id"]),
                "exam_code":         r["exam_code"],
                "title":             r["title"],
                "description":       r["description"],
                "exam_type":         r["exam_type"],
                "duration_mins":     r["duration_mins"],
                "total_marks":       float(r["total_marks"]),
                "start_time":        r["start_time"].isoformat(),
                "end_time":          r["end_time"].isoformat(),
                "course_name":       r["course_name"],
                "course_code":       r["course_code"],
                "teacher_name":      r["teacher_name"],
                "submission_status": r["submission_status"],
                "obtained_marks":    float(r["obtained_marks"]) if r["obtained_marks"] else None,
                "percentage":        float(r["percentage"])     if r["percentage"]     else None,
                "session_state":     r["session_state"],
            }
            for r in rows
        ]
    }


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 6: POST /student/start-exam
# Creates erp_submissions row (in_progress).
# Does NOT touch exam_sessions — that is handled by existing join-exam endpoint
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/start-exam")
async def start_exam(
    body: StartExamRequest,
    request: Request,
    current_user: dict = Depends(get_current_student),
):
    pool = request.app.state.db_pool
    student_id = current_user["sub"]

    async with pool.acquire() as conn:
        await fetch_student_profile(conn, student_id)

        # Verify exam is published and targets this student
        exam = await conn.fetchrow(
            """
            SELECT e.id, e.exam_code, e.title, e.total_marks, e.start_time, e.end_time
            FROM erp_exams    e
            JOIN erp_students s ON s.id = $1
            WHERE e.id            = $2
              AND e.is_published  = TRUE
              AND e.target_branch  = s.branch
              AND e.target_section = s.section
            """,
            UUID(student_id),
            UUID(body.exam_id),
        )
        if not exam:
            raise HTTPException(
                status_code=404,
                detail="Exam not found or not available for your branch/section",
            )

        now = datetime.now(timezone.utc)
        if now < exam["start_time"]:
            raise HTTPException(status_code=400, detail="Exam has not started yet")
        if now > exam["end_time"]:
            raise HTTPException(status_code=400, detail="Exam window has closed")

        # Idempotent — safe if student hits start twice (e.g. page refresh)
        submission_id = await conn.fetchval(
            """
            INSERT INTO erp_submissions (exam_id, student_id, status, total_marks)
            VALUES ($1, $2, 'in_progress', $3)
            ON CONFLICT (exam_id, student_id) DO UPDATE
                SET updated_at = now()
            RETURNING id
            """,
            UUID(body.exam_id),
            UUID(student_id),
            exam["total_marks"],
        )

    return {
        "submission_id": str(submission_id),
        "exam_code":     exam["exam_code"],
        "title":         exam["title"],
        "total_marks":   float(exam["total_marks"]),
        "end_time":      exam["end_time"].isoformat(),
        "message":       "Exam started. Now call POST /api/v1/join-exam for proctoring.",
    }


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 7: GET /student/questions/{exam_id}
# Returns questions — correct answers / test cases intentionally hidden
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/questions/{exam_id}")
async def get_exam_questions(
    exam_id: str,
    request: Request,
    current_user: dict = Depends(get_current_student),
):
    pool = request.app.state.db_pool
    student_id = current_user["sub"]

    async with pool.acquire() as conn:
        submission = await conn.fetchrow(
            """
            SELECT id, status FROM erp_submissions
            WHERE exam_id = $1 AND student_id = $2
            """,
            UUID(exam_id),
            UUID(student_id),
        )
        if not submission:
            raise HTTPException(status_code=403, detail="Start the exam first")
        if submission["status"] != "in_progress":
            raise HTTPException(
                status_code=400,
                detail=f"Exam already {submission['status']}",
            )

        rows = await conn.fetch(
            """
            SELECT
                id, question_type, title, marks, order_index, is_required,
                options,
                description, input_format, output_format,
                constraints, time_limit_ms, memory_limit_mb,
                left_items, right_items
                -- correct_options, correct_pairs, test_cases intentionally excluded
            FROM erp_questions
            WHERE exam_id = $1
            ORDER BY order_index ASC
            """,
            UUID(exam_id),
        )

    questions = []
    for r in rows:
        q = {
            "id":            str(r["id"]),
            "question_type": r["question_type"],
            "title":         r["title"],
            "marks":         float(r["marks"]),
            "order_index":   r["order_index"],
            "is_required":   r["is_required"],
        }
        if r["options"]:         q["options"]          = r["options"]
        if r["description"]:     q["description"]      = r["description"]
        if r["input_format"]:    q["input_format"]     = r["input_format"]
        if r["output_format"]:   q["output_format"]    = r["output_format"]
        if r["constraints"]:     q["constraints"]      = r["constraints"]
        if r["time_limit_ms"]:   q["time_limit_ms"]    = r["time_limit_ms"]
        if r["memory_limit_mb"]: q["memory_limit_mb"]  = r["memory_limit_mb"]
        if r["left_items"]:      q["left_items"]       = r["left_items"]
        if r["right_items"]:     q["right_items"]      = r["right_items"]
        questions.append(q)

    return {
        "exam_id":       exam_id,
        "submission_id": str(submission["id"]),
        "questions":     questions,
    }


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 8: POST /student/submit
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/submit")
async def submit_exam(
    body: SubmitExamRequest,
    request: Request,
    current_user: dict = Depends(get_current_student),
):
    """
    answers format:
        {
          "<question_uuid>": { "selected": ["a"] },         # MCQ
          "<question_uuid>": { "text": "Newton" },          # ONE_WORD
          "<question_uuid>": { "source_code": "...", ... }, # CODING
          "<question_uuid>": { "pairs": [...] }             # MATCH
        }
    """
    pool = request.app.state.db_pool
    student_id = current_user["sub"]

    async with pool.acquire() as conn:
        async with conn.transaction():

            submission = await conn.fetchrow(
                """
                SELECT id, status, total_marks
                FROM erp_submissions
                WHERE exam_id = $1 AND student_id = $2
                FOR UPDATE
                """,
                UUID(body.exam_id),
                UUID(student_id),
            )
            if not submission:
                raise HTTPException(status_code=404, detail="No active submission found")
            if submission["status"] != "in_progress":
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot submit — current status is '{submission['status']}'",
                )

            for question_id, answer_data in body.answers.items():
                await conn.execute(
                    """
                    INSERT INTO erp_submission_answers
                        (submission_id, question_id, answer_data, answered_at)
                    VALUES ($1, $2, $3, now())
                    ON CONFLICT (submission_id, question_id) DO UPDATE
                        SET answer_data = EXCLUDED.answer_data,
                            answered_at = now()
                    """,
                    submission["id"],
                    UUID(question_id),
                    json.dumps(answer_data),
                )

            await conn.execute(
                """
                UPDATE erp_submissions
                SET status = 'submitted', submitted_at = now(), updated_at = now()
                WHERE id = $1
                """,
                submission["id"],
            )

    return {
        "message":       "Exam submitted successfully",
        "submission_id": str(submission["id"]),
    }


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 9: GET /student/results
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/results")
async def get_student_results(
    request: Request,
    current_user: dict = Depends(get_current_student),
):
    pool = request.app.state.db_pool
    student_id = current_user["sub"]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                sub.id             AS submission_id,
                sub.status,
                sub.obtained_marks,
                sub.total_marks,
                sub.percentage,
                sub.remarks,
                sub.submitted_at,
                sub.evaluated_at,
                e.title            AS exam_title,
                e.exam_type,
                c.course_name
            FROM erp_submissions sub
            JOIN erp_exams   e ON e.id = sub.exam_id
            JOIN erp_courses c ON c.id = e.course_id
            WHERE sub.student_id = $1
              AND sub.status IN ('submitted', 'evaluated')
            ORDER BY sub.submitted_at DESC
            """,
            UUID(student_id),
        )

    return {
        "results": [
            {
                "submission_id": str(r["submission_id"]),
                "status":        r["status"],
                "exam_title":    r["exam_title"],
                "exam_type":     r["exam_type"],
                "course_name":   r["course_name"],
                "obtained_marks":float(r["obtained_marks"]) if r["obtained_marks"] else None,
                "total_marks":   float(r["total_marks"])    if r["total_marks"]    else None,
                "percentage":    float(r["percentage"])     if r["percentage"]     else None,
                "remarks":       r["remarks"],
                "submitted_at":  r["submitted_at"].isoformat() if r["submitted_at"] else None,
                "evaluated_at":  r["evaluated_at"].isoformat() if r["evaluated_at"] else None,
            }
            for r in rows
        ]
    }