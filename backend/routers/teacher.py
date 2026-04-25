# routers/teacher.py

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
router = APIRouter(prefix="/teacher", tags=["teacher"])
bearer = HTTPBearer()

ERP_JWT_SECRET = os.getenv("ERP_JWT_SECRET", "shared-secret-with-java-erp")



def parse_dt(s: str) -> datetime:
    """Handles ISO strings with or without milliseconds and Z suffix."""
    s = s.replace('Z', '+00:00')
    if '.' in s:
        # Remove milliseconds — Python 3.10 fromisoformat doesn't support them
        s = s.split('.')[0] + '+00:00'
    return datetime.fromisoformat(s)

# ═══════════════════════════════════════════════
# JWT VALIDATION
# ═══════════════════════════════════════════════

def get_current_teacher(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
):
    try:
        payload = jwt.decode(
            credentials.credentials, ERP_JWT_SECRET, algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access only")

    return payload


# ═══════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════

class CreateExamRequest(BaseModel):
    course_id: str
    title: str
    description: str | None = None
    target_branch: str
    target_section: str
    exam_type: str
    duration_mins: int
    total_marks: float
    start_time: str
    end_time: str


class AddQuestionRequest(BaseModel):
    exam_id: str
    question_type: str
    title: str
    marks: float
    order_index: int = 0

    # Optional fields
    options: dict | None = None
    correct_options: list | None = None
    expected_answer: str | None = None
    description: str | None = None
    test_cases: list | None = None


# ═══════════════════════════════════════════════
# CREATE EXAM
# ═══════════════════════════════════════════════

@router.post("/create-exam")
async def create_exam(
    body: CreateExamRequest,
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool
    teacher_id = current_user["sub"]

    async with pool.acquire() as conn:
        exam_code = f"EXAM-{int(datetime.now().timestamp())}"

        exam_id = await conn.fetchval(
            """
            INSERT INTO erp_exams (
                exam_code, course_id, created_by,
                title, description,
                target_branch, target_section,
                exam_type, duration_mins, total_marks,
                start_time, end_time
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            exam_code,
            UUID(body.course_id),
            UUID(teacher_id),
            body.title,
            body.description,
            body.target_branch,
            body.target_section,
            body.exam_type,
            body.duration_mins,
            body.total_marks,
            parse_dt(body.start_time),
            parse_dt(body.end_time),
        )

    return {
        "exam_id": str(exam_id),
        "exam_code": exam_code,
        "message": "Exam created successfully",
    }




# ═══════════════════════════════════════════════
# ADD QUESTION
# ═══════════════════════════════════════════════

@router.post("/add-question")
async def add_question(
    body: AddQuestionRequest,
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO erp_questions (
                exam_id, question_type, title, marks, order_index,
                options, correct_options, expected_answer,
                description, test_cases
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
            UUID(body.exam_id),
            body.question_type,
            body.title,
            body.marks,
            body.order_index,
            json.dumps(body.options) if body.options else None,
            json.dumps(body.correct_options) if body.correct_options else None,
            body.expected_answer,
            body.description,
            json.dumps(body.test_cases) if body.test_cases else None,
        )

    return {"message": "Question added successfully"}

# ── GET /teacher/my-exams ─────────────────────────────────────────────────
@router.get("/my-exams")
async def get_my_exams(
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool
    teacher_id = current_user["sub"]

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
                e.total_marks,
                c.course_name,
                c.course_code,
                COUNT(sub.id)   AS submission_count,
                COUNT(sub.id) FILTER (WHERE sub.status = 'submitted') AS pending_eval
            FROM erp_exams e
            JOIN erp_courses c ON c.id = e.course_id
            LEFT JOIN erp_submissions sub ON sub.exam_id = e.id
            WHERE e.created_by = $1
            GROUP BY e.id, c.course_name, c.course_code
            ORDER BY e.created_at DESC
            """,
            UUID(teacher_id),
        )

    return {
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
                "total_marks":      float(r["total_marks"]),
                "course_name":      r["course_name"],
                "course_code":      r["course_code"],
                "submission_count": r["submission_count"],
                "pending_eval":     r["pending_eval"],
            }
            for r in rows
        ]
    }


# ── GET /teacher/my-courses ───────────────────────────────────────────────
@router.get("/my-courses")
async def get_my_courses(
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool
    teacher_id = current_user["sub"]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id AS course_id, course_code, course_name, branch, semester, credits
            FROM erp_courses
            WHERE teacher_id = $1 AND is_active = TRUE
            ORDER BY branch, semester, course_name
            """,
            UUID(teacher_id),
        )

    return {
        "courses": [
            {
                "course_id":   str(r["course_id"]),
                "course_code": r["course_code"],
                "course_name": r["course_name"],
                "branch":      r["branch"],
                "semester":    r["semester"],
                "credits":     r["credits"],
            }
            for r in rows
        ]
    }


# ── GET /teacher/questions/{exam_id} ──────────────────────────────────────
@router.get("/questions/{exam_id}")
async def get_exam_questions(
    exam_id: str,
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, question_type, title, marks, order_index,
                   options, correct_options, expected_answer,
                   description, test_cases, left_items, right_items, correct_pairs
            FROM erp_questions
            WHERE exam_id = $1
            ORDER BY order_index
            """,
            UUID(exam_id),
        )

    return {
        "questions": [
            {
                "id":            str(r["id"]),
                "question_type": r["question_type"],
                "title":         r["title"],
                "marks":         float(r["marks"]),
                "order_index":   r["order_index"],
                "options":       r["options"],
                "correct_options":r["correct_options"],
                "expected_answer":r["expected_answer"],
                "description":   r["description"],
                "test_cases":    r["test_cases"],
                "left_items":    r["left_items"],
                "right_items":   r["right_items"],
                "correct_pairs": r["correct_pairs"],
            }
            for r in rows
        ]
    }


# ── GET /teacher/submission-detail/{submission_id} ────────────────────────
@router.get("/submission-detail/{submission_id}")
async def get_submission_detail(
    submission_id: str,
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        answers = await conn.fetch(
            """
            SELECT
                sa.id           AS answer_id,
                sa.question_id,
                sa.answer_data,
                sa.marks_awarded,
                q.title         AS question_title,
                q.marks         AS max_marks,
                q.question_type
            FROM erp_submission_answers sa
            JOIN erp_questions q ON q.id = sa.question_id
            WHERE sa.submission_id = $1
            ORDER BY q.order_index
            """,
            UUID(submission_id),
        )

    return {
        "answers": [
            {
                "answer_id":      str(r["answer_id"]),
                "question_id":    str(r["question_id"]),
                "question_title": r["question_title"],
                "question_type":  r["question_type"],
                "answer_data":    r["answer_data"],
                "marks_awarded":  float(r["marks_awarded"]) if r["marks_awarded"] else None,
                "max_marks":      float(r["max_marks"]),
            }
            for r in answers
        ]
    }

# ═══════════════════════════════════════════════
# PUBLISH EXAM
# ═══════════════════════════════════════════════

@router.post("/publish-exam/{exam_id}")
async def publish_exam(
    exam_id: str,
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE erp_exams
            SET is_published = TRUE
            WHERE id = $1
            """,
            UUID(exam_id),
        )

    return {"message": "Exam published successfully"}


# ═══════════════════════════════════════════════
# VIEW SUBMISSIONS
# ═══════════════════════════════════════════════

@router.get("/submissions/{exam_id}")
async def get_submissions(
    exam_id: str,
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                sub.id,
                u.name,
                sub.status,
                sub.obtained_marks,
                sub.submitted_at
            FROM erp_submissions sub
            JOIN erp_users u ON u.id = sub.student_id
            WHERE sub.exam_id = $1
            """,
            UUID(exam_id),
        )

    return [
        {
            "submission_id": str(r["id"]),
            "student_name": r["name"],
            "status": r["status"],
            "marks": float(r["obtained_marks"]) if r["obtained_marks"] else None,
            "submitted_at": r["submitted_at"],
        }
        for r in rows
    ]


# ═══════════════════════════════════════════════
# EVALUATE ANSWER
# ═══════════════════════════════════════════════

@router.post("/evaluate")
async def evaluate_submission(
    submission_id: str,
    marks: float,
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE erp_submissions
            SET obtained_marks = $1,
                status = 'evaluated',
                evaluated_at = now()
            WHERE id = $2
            """,
            marks,
            UUID(submission_id),
        )

    return {"message": "Evaluation completed"}

# ── GET /teacher/branches — public branch list for dropdown ───────────────
@router.get("/branches")
async def get_branches_for_teacher(
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, code FROM erp_branches WHERE is_active = TRUE ORDER BY name"
        )
    return {
        "branches": [
            {"id": str(r["id"]), "name": r["name"], "code": r["code"]}
            for r in rows
        ]
    }
from pydantic import BaseModel as PydanticBase

class UpdateExamTimeRequest(PydanticBase):
    start_time: str
    end_time:   str

@router.patch("/update-exam-time/{exam_id}")
async def update_exam_time(
    exam_id: str,
    body: UpdateExamTimeRequest,
    request: Request,
    current_user: dict = Depends(get_current_teacher),
):
    pool = request.app.state.db_pool
    teacher_id = current_user["sub"]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE erp_exams
            SET start_time = $1, end_time = $2, updated_at = now()
            WHERE id = $3 AND created_by = $4
            """,
            parse_dt(body.start_time),
            parse_dt(body.end_time),
            UUID(exam_id),
            UUID(teacher_id),
        )
    return {"message": "Timing updated"}