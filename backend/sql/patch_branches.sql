-- =============================================================================
-- PATCH: Add missing erp_branches table and update erp_courses
-- File: sql/patch_branches.sql
-- Run AFTER erp_schema.sql
-- Additive only — fixes missing schema elements for admin dashboard
-- =============================================================================

-- Add erp_branches table
CREATE TABLE IF NOT EXISTS erp_branches (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT            NOT NULL UNIQUE,
    code        TEXT            NOT NULL UNIQUE,
    created_by  UUID            NOT NULL REFERENCES erp_users(id) ON DELETE SET NULL,
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_erp_branches_code ON erp_branches(code);
CREATE INDEX IF NOT EXISTS idx_erp_branches_active ON erp_branches(is_active);

COMMENT ON TABLE erp_branches IS 'Academic branches/departments managed by admins';

-- Update erp_courses to add missing columns
ALTER TABLE erp_courses
ADD COLUMN IF NOT EXISTS branch TEXT,
ADD COLUMN IF NOT EXISTS semester SMALLINT;

-- Add constraint for semester
ALTER TABLE erp_courses
ADD CONSTRAINT IF NOT EXISTS chk_courses_semester CHECK (semester IS NULL OR (semester >= 1 AND semester <= 10));

-- Create index on new columns
CREATE INDEX IF NOT EXISTS idx_erp_courses_branch_semester ON erp_courses(branch, semester);

COMMENT ON COLUMN erp_courses.branch IS 'Academic branch this course belongs to';
COMMENT ON COLUMN erp_courses.semester IS 'Semester level (1-8)';
