# backend/routers/erp_auth.py
# ─────────────────────────────────────────────────────────────────────────────
# NEW FILE — does not touch existing auth.py
# Provides /erp/login and /erp/register for the ERP dashboards
# Uses same ERP_JWT_SECRET as existing auth.py
# ─────────────────────────────────────────────────────────────────────────────

import os
import jwt
import bcrypt
import logging
from uuid import UUID
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/erp", tags=["erp-auth"])

ERP_JWT_SECRET = os.getenv("ERP_JWT_SECRET", "shared-secret-with-java-erp")
TOKEN_TTL_H    = 24


# ═════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═════════════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
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


class LoginRequest(BaseModel):
    email:    str
    password: str


# ═════════════════════════════════════════════════════════════════════════════
# JWT HELPER
# ═════════════════════════════════════════════════════════════════════════════

def create_erp_token(user_id: str, role: str, name: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub":  user_id,
        "role": role,
        "name": name,
        "iat":  int(now.timestamp()),
        "exp":  int((now + timedelta(hours=TOKEN_TTL_H)).timestamp()),
    }
    return jwt.encode(payload, ERP_JWT_SECRET, algorithm="HS256")


# ═════════════════════════════════════════════════════════════════════════════
# POST /erp/register
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request):
    allowed = {"student", "teacher", "admin"}
    if body.role not in allowed:
        raise HTTPException(400, detail=f"role must be one of {allowed}")

    if body.role == "student" and (not body.branch or not body.section):
        raise HTTPException(400, detail="branch and section are required for students")

    pw_hash = bcrypt.hashpw(
        body.password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

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
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    user_id, body.roll_number, body.branch,
                    body.section, body.semester, body.batch_year,
                )
            elif body.role == "teacher":
                await conn.execute(
                    """
                    INSERT INTO erp_teachers (id, department, employee_id)
                    VALUES ($1, $2, $3)
                    """,
                    user_id, body.department, body.employee_id,
                )
            elif body.role == "admin":
                await conn.execute(
                    """
                    INSERT INTO erp_admins (id, is_super_admin)
                    VALUES ($1, TRUE)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    user_id,
                )

    return {"message": "User registered successfully", "user_id": str(user_id)}


# ═════════════════════════════════════════════════════════════════════════════
# POST /erp/login
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/login")
async def login(body: LoginRequest, request: Request):
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, email, password_hash, role, is_active
            FROM erp_users
            WHERE email = $1
            """,
            body.email,
        )

    if not row:
        raise HTTPException(401, detail="Invalid email or password")

    if not row["is_active"]:
        raise HTTPException(403, detail="Account is disabled. Contact admin.")

    match = bcrypt.checkpw(
        body.password.encode("utf-8"),
        row["password_hash"].encode("utf-8"),
    )
    if not match:
        raise HTTPException(401, detail="Invalid email or password")

    token = create_erp_token(str(row["id"]), row["role"], row["name"])

    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "id":    str(row["id"]),
            "name":  row["name"],
            "email": row["email"],
            "role":  row["role"],
        },
    }


# ═════════════════════════════════════════════════════════════════════════════
# GET /erp/me  — verify token and return profile
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/me")
async def me(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, detail="Missing token")

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, ERP_JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, detail="Invalid token")

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, email, role FROM erp_users WHERE id = $1",
            UUID(payload["sub"]),
        )

    if not row:
        raise HTTPException(404, detail="User not found")

    return {
        "id":    str(row["id"]),
        "name":  row["name"],
        "email": row["email"],
        "role":  row["role"],
    }