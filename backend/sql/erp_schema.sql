-- =============================================================================
-- ERP SCHEMA — AI PROCTORING PLATFORM
-- Day 1: PostgreSQL Database Design
-- Author: Senior Backend Architect
-- Rules: ADDITIVE ONLY — does NOT modify any existing tables
-- =============================================================================

-- ---------------------------------------------------------------------------
-- EXTENSION
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "citext";     -- case-insensitive email lookups


-- =============================================================================
-- SECTION 1: USER MANAGEMENT
-- =============================================================================

CREATE TYPE erp_role AS ENUM ('student', 'teacher', 'admin');

CREATE TABLE erp_users (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    email           CITEXT      NOT NULL UNIQUE,
    password_hash   TEXT        NOT NULL,
    role            erp_role    NOT NULL,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_erp_users_email  ON erp_users(email);
CREATE INDEX idx_erp_users_role   ON erp_users(role);

COMMENT ON TABLE  erp_users          IS 'Central identity table for all platform users';
COMMENT ON COLUMN erp_users.email    IS 'CITEXT ensures case-insensitive uniqueness';
COMMENT ON COLUMN erp_users.role     IS 'Drives RBAC throughout the system';


-- =============================================================================
-- SECTION 2: STUDENTS
-- =============================================================================

CREATE TABLE erp_students (
    id          UUID    PRIMARY KEY REFERENCES erp_users(id) ON DELETE CASCADE,
    roll_number TEXT    UNIQUE,                 -- institute roll number
    branch      TEXT    NOT NULL,               -- e.g. CSE, ECE, ME
    section     TEXT    NOT NULL,               -- e.g. A, B, C
    semester    SMALLINT,                       -- current semester 1-8
    batch_year  SMALLINT,                       -- admission year e.g. 2022
    CONSTRAINT chk_semester CHECK (semester BETWEEN 1 AND 10)
);

CREATE INDEX idx_erp_students_branch_section ON erp_students(branch, section);

COMMENT ON TABLE erp_students IS 'Student profile linked 1:1 to erp_users';


-- =============================================================================
-- SECTION 3: TEACHERS
-- =============================================================================

CREATE TABLE erp_teachers (
    id          UUID    PRIMARY KEY REFERENCES erp_users(id) ON DELETE CASCADE,
    department  TEXT,
    employee_id TEXT    UNIQUE
);

COMMENT ON TABLE erp_teachers IS 'Teacher profile linked 1:1 to erp_users';

-- =============================================================================
-- PATCH: erp_admins profile table
-- File: sql/patch_001_erp_admins.sql
-- Run AFTER erp_schema.sql
-- Additive only — zero changes to existing tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS erp_admins (
    id              UUID        PRIMARY KEY
                                REFERENCES erp_users(id) ON DELETE CASCADE,
    can_manage_users    BOOLEAN NOT NULL DEFAULT TRUE,
    can_manage_exams    BOOLEAN NOT NULL DEFAULT TRUE,
    can_view_proctoring BOOLEAN NOT NULL DEFAULT TRUE,
    can_manage_courses  BOOLEAN NOT NULL DEFAULT TRUE,
    is_super_admin      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE erp_admins IS
    'Admin profile linked 1:1 to erp_users. '
    'Granular permission flags allow partial admin roles. '
    'is_super_admin = TRUE grants unrestricted access.';

-- ── Upgrade the existing seed admin user to have an admin profile ──────────
INSERT INTO erp_admins (id, is_super_admin)
SELECT id, TRUE
FROM   erp_users
WHERE  role  = 'admin'
  AND  email = 'admin@proctoring.local'
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- SECTION 4: COURSES
-- =============================================================================

CREATE TABLE erp_courses (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    course_code TEXT        NOT NULL UNIQUE,    -- e.g. CS301
    course_name TEXT        NOT NULL,
    teacher_id  UUID        NOT NULL REFERENCES erp_teachers(id) ON DELETE RESTRICT,
    credits     SMALLINT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_erp_courses_teacher ON erp_courses(teacher_id);

COMMENT ON TABLE erp_courses IS 'Academic courses managed by teachers';


-- =============================================================================
-- SECTION 5: EXAMS
-- NOTE: exam_code is the foreign key to EXISTING exam_sessions.exam_code
--       We do NOT declare FK because exam_sessions is in a different schema
--       boundary; referential integrity is enforced at application layer.
-- =============================================================================

CREATE TYPE exam_type AS ENUM ('practice', 'real');

CREATE TABLE erp_exams (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_code       TEXT        NOT NULL UNIQUE,   -- ← matches exam_sessions.exam_code
    course_id       UUID        NOT NULL REFERENCES erp_courses(id) ON DELETE RESTRICT,
    created_by      UUID        NOT NULL REFERENCES erp_teachers(id) ON DELETE RESTRICT,
    title           TEXT        NOT NULL,
    description     TEXT,
    target_branch   TEXT        NOT NULL,
    target_section  TEXT        NOT NULL,
    exam_type       exam_type   NOT NULL DEFAULT 'real',
    duration_mins   SMALLINT    NOT NULL DEFAULT 60,
    total_marks     NUMERIC(6,2) NOT NULL DEFAULT 100,
    passing_marks   NUMERIC(6,2),
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    is_published    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_exam_time   CHECK (end_time > start_time),
    CONSTRAINT chk_pass_marks  CHECK (passing_marks IS NULL OR passing_marks <= total_marks)
);

CREATE INDEX idx_erp_exams_exam_code        ON erp_exams(exam_code);
CREATE INDEX idx_erp_exams_course           ON erp_exams(course_id);
CREATE INDEX idx_erp_exams_teacher          ON erp_exams(created_by);
CREATE INDEX idx_erp_exams_target           ON erp_exams(target_branch, target_section);
CREATE INDEX idx_erp_exams_time             ON erp_exams(start_time, end_time);

COMMENT ON TABLE  erp_exams           IS 'Exam definitions. exam_code links to existing exam_sessions.exam_code';
COMMENT ON COLUMN erp_exams.exam_code IS 'Must match exam_sessions.exam_code in the proctoring schema';


-- =============================================================================
-- SECTION 6: QUESTIONS (polymorphic, flexible type system)
-- =============================================================================

CREATE TYPE question_type AS ENUM (
    'coding',
    'mcq',
    'one_word',
    'short_answer',
    'true_false',
    'match_following'
);

CREATE TABLE erp_questions (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id         UUID            NOT NULL REFERENCES erp_exams(id) ON DELETE CASCADE,
    question_type   question_type   NOT NULL,
    title           TEXT            NOT NULL,   -- the question text / problem statement
    marks           NUMERIC(5,2)    NOT NULL DEFAULT 1,
    order_index     SMALLINT        NOT NULL DEFAULT 0,
    is_required     BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- -----------------------------------------------------------------------
    -- MCQ / TRUE_FALSE
    -- options: [{"id":"a","text":"..."},{"id":"b","text":"..."}]
    -- correct_options: ["a"] or ["a","b"] for multi-correct
    -- -----------------------------------------------------------------------
    options         JSONB,
    correct_options JSONB,          -- array of option ids

    -- -----------------------------------------------------------------------
    -- ONE_WORD / SHORT_ANSWER / TRUE_FALSE
    -- -----------------------------------------------------------------------
    expected_answer TEXT,
    answer_keywords JSONB,          -- array of keywords for auto-grade

    -- -----------------------------------------------------------------------
    -- CODING (LeetCode style)
    -- -----------------------------------------------------------------------
    description     TEXT,
    input_format    TEXT,
    output_format   TEXT,
    constraints     TEXT,
    time_limit_ms   INTEGER DEFAULT 2000,
    memory_limit_mb INTEGER DEFAULT 256,
    -- test_cases: [{"input":"...","expected_output":"...","is_hidden":true}]
    test_cases      JSONB,

    -- -----------------------------------------------------------------------
    -- MATCH THE FOLLOWING
    -- left_items:  [{"id":"1","text":"..."}]
    -- right_items: [{"id":"A","text":"..."}]
    -- correct_pairs: [{"left":"1","right":"A"}]
    -- -----------------------------------------------------------------------
    left_items      JSONB,
    right_items     JSONB,
    correct_pairs   JSONB
);

CREATE INDEX idx_erp_questions_exam       ON erp_questions(exam_id);
CREATE INDEX idx_erp_questions_type       ON erp_questions(question_type);
CREATE INDEX idx_erp_questions_order      ON erp_questions(exam_id, order_index);

COMMENT ON TABLE erp_questions IS 'Polymorphic question table supporting 6 question types via type-specific nullable columns';


-- =============================================================================
-- SECTION 7: SUBMISSIONS
-- NOTE: student_id is a UUID that references erp_students.id
--       which is the same as erp_users.id, which MUST match
--       exam_sessions.student_id in the proctoring schema.
-- =============================================================================

CREATE TYPE submission_status AS ENUM (
    'in_progress',
    'submitted',
    'evaluated',
    'flagged'
);

CREATE TABLE erp_submissions (
    id              UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id         UUID                NOT NULL REFERENCES erp_exams(id) ON DELETE RESTRICT,
    student_id      UUID                NOT NULL REFERENCES erp_students(id) ON DELETE RESTRICT,
    status          submission_status   NOT NULL DEFAULT 'in_progress',
    started_at      TIMESTAMPTZ         NOT NULL DEFAULT now(),
    submitted_at    TIMESTAMPTZ,
    evaluated_at    TIMESTAMPTZ,
    evaluated_by    UUID                REFERENCES erp_teachers(id) ON DELETE SET NULL,

    -- Aggregate scores
    total_marks     NUMERIC(6,2),
    obtained_marks  NUMERIC(6,2),
    percentage      NUMERIC(5,2)
        GENERATED ALWAYS AS (
            CASE WHEN total_marks > 0
                THEN ROUND((obtained_marks / total_marks) * 100, 2)
                ELSE NULL
            END
        ) STORED,

    -- remarks / feedback from teacher
    remarks         TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (exam_id, student_id)   -- one submission per student per exam
);

CREATE INDEX idx_erp_submissions_exam     ON erp_submissions(exam_id);
CREATE INDEX idx_erp_submissions_student  ON erp_submissions(student_id);
CREATE INDEX idx_erp_submissions_status   ON erp_submissions(status);

COMMENT ON TABLE erp_submissions IS 'Top-level submission record per student per exam';


-- =============================================================================
-- SECTION 8: SUBMISSION ANSWERS (per-question granularity)
-- =============================================================================

CREATE TABLE erp_submission_answers (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id   UUID        NOT NULL REFERENCES erp_submissions(id) ON DELETE CASCADE,
    question_id     UUID        NOT NULL REFERENCES erp_questions(id) ON DELETE CASCADE,

    -- Student's answer stored as flexible JSON
    -- MCQ:           {"selected": ["a"]}
    -- ONE_WORD:      {"text": "photosynthesis"}
    -- SHORT_ANSWER:  {"text": "...long answer..."}
    -- TRUE_FALSE:    {"selected": "true"}
    -- MATCH:         {"pairs": [{"left":"1","right":"A"}]}
    -- CODING:        {"language_id": 71, "source_code": "...", "judge0_token": "..."}
    answer_data     JSONB       NOT NULL DEFAULT '{}',

    -- Auto or manual marks
    marks_awarded   NUMERIC(5,2),
    is_correct      BOOLEAN,                    -- for auto-gradeable types
    judge0_result   JSONB,                      -- stores Judge0 API response for coding
    grader_notes    TEXT,

    answered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (submission_id, question_id)
);

CREATE INDEX idx_erp_answers_submission ON erp_submission_answers(submission_id);
CREATE INDEX idx_erp_answers_question   ON erp_submission_answers(question_id);

COMMENT ON TABLE erp_submission_answers IS 'Per-question answers with flexible JSONB storage for all question types';


-- =============================================================================
-- SECTION 9: AUDIT / REFRESH TRIGGERS
-- =============================================================================

-- Generic updated_at trigger function
CREATE OR REPLACE FUNCTION erp_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_erp_users_updated_at
    BEFORE UPDATE ON erp_users
    FOR EACH ROW EXECUTE FUNCTION erp_set_updated_at();

CREATE TRIGGER trg_erp_exams_updated_at
    BEFORE UPDATE ON erp_exams
    FOR EACH ROW EXECUTE FUNCTION erp_set_updated_at();

CREATE TRIGGER trg_erp_submissions_updated_at
    BEFORE UPDATE ON erp_submissions
    FOR EACH ROW EXECUTE FUNCTION erp_set_updated_at();


-- =============================================================================
-- SECTION 10: ROLE-LEVEL GRANTS (adjust DB user names to your environment)
-- Uncomment and set your actual DB roles before running in production.
-- =============================================================================

-- GRANT SELECT, INSERT, UPDATE ON erp_users, erp_students TO app_student_role;
-- GRANT SELECT ON erp_courses, erp_exams, erp_questions TO app_student_role;
-- GRANT SELECT, INSERT, UPDATE ON erp_submissions, erp_submission_answers TO app_student_role;

-- GRANT SELECT, INSERT, UPDATE, DELETE ON erp_courses, erp_exams, erp_questions TO app_teacher_role;
-- GRANT SELECT ON erp_submissions, erp_submission_answers TO app_teacher_role;
-- GRANT UPDATE (marks_awarded, grader_notes) ON erp_submission_answers TO app_teacher_role;

-- GRANT ALL ON ALL TABLES IN SCHEMA public TO app_admin_role;


-- =============================================================================
-- SECTION 11: SEED DATA (admin bootstrap — change password immediately)
-- =============================================================================

-- Creates a single admin user with a PLACEHOLDER hash.
-- In production: generate a proper bcrypt hash and replace it.
-- Placeholder: bcrypt('AdminPass@1', 12) — DO NOT USE IN PROD AS-IS
INSERT INTO erp_users (id, name, email, password_hash, role)
VALUES (
    gen_random_uuid(),
    'System Admin',
    'admin@proctoring.local',
    '$2b$12$REPLACE_THIS_HASH_WITH_REAL_BCRYPT',
    'admin'
)
ON CONFLICT (email) DO NOTHING;


-- =============================================================================
-- END OF SCHEMA
-- =============================================================================