-- ══════════════════════════════════════════
-- PROCTORSHIELD: ENTERPRISE DATABASE SCHEMA
-- ══════════════════════════════════════════

-- ─── 1. EXAM STATE MACHINE ENUMS ───
CREATE TYPE exam_state AS ENUM (
    'SCHEDULED',         -- Student is allowed to take it, hasn't started
    'IDENTITY_CHECK',    -- Currently scanning face against ERP photo
    'IN_PROGRESS',       -- Exam is live and actively recording
    'PAUSED',            -- Network dropped, grace period active (e.g., 2 mins)
    'SUSPENDED',         -- Grace period expired, proctor intervention required
    'FLAGGED',           -- Severe tamper detected, exam continues but flagged
    'SUBMITTED',         -- Student clicked submit
    'REPORT_GENERATED',  -- AI finished processing the final trust score
    'ARCHIVED'           -- Video and report hashed and locked in MinIO
);

CREATE TYPE violation_severity AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

-- ─── 2. CORE EXAM SESSIONS ───
CREATE TABLE IF NOT EXISTS exam_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_code           VARCHAR(50) NOT NULL,
    student_id          VARCHAR(100) NOT NULL,
    state               exam_state NOT NULL DEFAULT 'SCHEDULED',
    livekit_room        VARCHAR(200),
    
    -- Timestamps for every major event
    scheduled_at        TIMESTAMP DEFAULT NOW(),
    identity_at         TIMESTAMP,
    started_at          TIMESTAMP,
    paused_at           TIMESTAMP,
    resumed_at          TIMESTAMP,
    submitted_at        TIMESTAMP,
    
    -- Identity & Risk metrics
    face_match_score    FLOAT,
    identity_verified   BOOLEAN DEFAULT FALSE,
    risk_score          FLOAT DEFAULT 0.0,
    risk_level          VARCHAR(20) DEFAULT 'GREEN',
    
    -- Evidence links
    recording_url       TEXT,
    report_url          TEXT,
    
    -- Java ERP Integration
    erp_webhook_sent    BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(exam_code, student_id)
);

-- ─── 3. STATE TRANSITION AUDIT LOG (Legal Proof) ───
CREATE TABLE IF NOT EXISTS state_transitions (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID REFERENCES exam_sessions(id),
    from_state          exam_state,
    to_state            exam_state NOT NULL,
    reason              TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ─── 4. TEMPORAL VIOLATION EVENTS ───
CREATE TABLE IF NOT EXISTS violations (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID REFERENCES exam_sessions(id),
    violation_type      VARCHAR(50) NOT NULL,
    severity            violation_severity NOT NULL,
    confidence          FLOAT,
    description         TEXT,
    frame_timestamp     FLOAT,
    duration_seconds    FLOAT DEFAULT 0,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ─── 5. BEHAVIORAL TELEMETRY ───
CREATE TABLE IF NOT EXISTS behavioral_telemetry (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID REFERENCES exam_sessions(id),
    event_type          VARCHAR(30),
    tab_switches        INTEGER DEFAULT 0,
    copy_paste_count    INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ─── 6. EVIDENCE HASH AUDIT (Chain of Custody) ───
CREATE TABLE IF NOT EXISTS evidence_hashes (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID REFERENCES exam_sessions(id),
    file_type           VARCHAR(30),
    sha256_hash         VARCHAR(64) NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- Prevent ANY updates or deletes on evidence_hashes (WORM compliance at DB level)
CREATE RULE protect_evidence_hashes_update AS ON UPDATE TO evidence_hashes DO INSTEAD NOTHING;
CREATE RULE protect_evidence_hashes_delete AS ON DELETE TO evidence_hashes DO INSTEAD NOTHING;

-- ─── 7. ERP WEBHOOK DEAD LETTER QUEUE (Resilience) ───
CREATE TABLE IF NOT EXISTS webhook_dlq (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID REFERENCES exam_sessions(id),
    payload             JSONB NOT NULL,
    http_status         INTEGER,
    retry_count         INTEGER DEFAULT 0,
    next_retry_at       TIMESTAMP,
    resolved            BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ─── 8. PERFORMANCE INDEXES (Crucial for 1000+ students) ───
CREATE INDEX idx_sessions_student ON exam_sessions(student_id);
CREATE INDEX idx_sessions_state ON exam_sessions(state);
CREATE INDEX idx_violations_session ON violations(session_id);
CREATE INDEX idx_dlq_unresolved ON webhook_dlq(resolved, next_retry_at) WHERE resolved = FALSE;