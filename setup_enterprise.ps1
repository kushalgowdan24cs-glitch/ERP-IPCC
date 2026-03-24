# Save this as: setup_enterprise.ps1
# Run with: powershell -ExecutionPolicy Bypass -File setup_enterprise.ps1

Write-Host "=== PROCTORSHIELD ENTERPRISE SETUP ===" -ForegroundColor Cyan

# ─── CREATE ALL FOLDERS ───
Write-Host "Creating folders..." -ForegroundColor Yellow
$folders = @(
    "monitoring/grafana/provisioning/datasources",
    "monitoring/grafana/dashboards",
    "model_repository/yolov8_detector/1",
    "model_repository/face_recognition/1",
    "model_repository/silero_vad/1",
    "backend/sql",
    "minio_data"
)
foreach ($f in $folders) {
    New-Item -ItemType Directory -Force -Path $f | Out-Null
}
Write-Host "Folders created!" -ForegroundColor Green

# ─── FILE 1: docker-compose.yml ───
Write-Host "Writing docker-compose.yml..." -ForegroundColor Yellow
@'
version: '3.8'

services:

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: always

  postgres:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: supersecretpassword
      POSTGRES_DB: proctorshield
    ports:
      - "5435:5432"
    volumes:
      - ./local_db_data:/var/lib/postgresql/data
      - ./backend/sql/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin -d proctorshield"]
      interval: 5s
      timeout: 3s
      retries: 5

  minio:
    image: minio/minio
    restart: always
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: supersecretpassword
    command: server /data --console-address ":9001"
    volumes:
      - ./minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 3

  minio-setup:
    image: minio/mc
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set local http://minio:9000 admin supersecretpassword;
      mc mb --ignore-existing local/exam-recordings;
      mc mb --ignore-existing local/exam-evidence;
      mc mb --ignore-existing local/student-photos;
      mc mb --ignore-existing local/forensic-reports;
      echo 'MinIO buckets created';
      exit 0;
      "

  livekit:
    image: livekit/livekit-server:latest
    container_name: livekit
    command: --config /etc/livekit.yaml
    ports:
      - "7880:7880"
      - "7881:7881"
      - "7882:7882/udp"
      - "3478:3478/udp"
      - "5349:5349"
    volumes:
      - ./livekit.yaml:/etc/livekit.yaml
    depends_on:
      redis:
        condition: service_healthy
    restart: always

  livekit-egress:
    image: livekit/egress:latest
    environment:
      EGRESS_CONFIG_FILE: /etc/egress.yaml
    volumes:
      - ./egress.yaml:/etc/egress.yaml
    depends_on:
      - livekit
      - redis
      - minio
    restart: always

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    restart: always

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: proctorshield2024
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
    depends_on:
      - prometheus
    restart: always

volumes:
  grafana_data:
'@ | Out-File -FilePath "docker-compose.yml" -Encoding UTF8

# ─── FILE 2: livekit.yaml ───
Write-Host "Writing livekit.yaml..." -ForegroundColor Yellow
@'
port: 7880
bind_addresses:
  - ""

keys:
  devkey: f47ac10b58cc4372a5670e02b2c3d479f47ac10b58cc4372

logging:
  level: info
  json: false

rtc:
  tcp_port: 7881
  udp_port: 7882
  use_external_ip: false
  enable_loopback_candidate: true

turn:
  enabled: true
  domain: localhost
  tls_port: 5349
  udp_port: 3478

redis:
  address: redis:6379

room:
  empty_timeout: 300
  max_participants: 5
  auto_create: true

webhook:
  urls:
    - "http://host.docker.internal:8000/api/v1/livekit/webhook"
  api_key: devkey
'@ | Out-File -FilePath "livekit.yaml" -Encoding UTF8

# ─── FILE 3: egress.yaml ───
Write-Host "Writing egress.yaml..." -ForegroundColor Yellow
@'
log_level: info
api_key: devkey
api_secret: f47ac10b58cc4372a5670e02b2c3d479f47ac10b58cc4372
ws_url: ws://livekit:7880

health_port: 0
template_port: 0

s3:
  access_key: admin
  secret: supersecretpassword
  endpoint: http://minio:9000
  region: us-east-1
  bucket: exam-recordings
  force_path_style: true
'@ | Out-File -FilePath "egress.yaml" -Encoding UTF8

# ─── FILE 4: prometheus.yml ───
Write-Host "Writing monitoring/prometheus.yml..." -ForegroundColor Yellow
@'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'fastapi'
    metrics_path: /metrics
    static_configs:
      - targets: ['host.docker.internal:8000']

  - job_name: 'livekit'
    metrics_path: /metrics
    static_configs:
      - targets: ['livekit:7880']
'@ | Out-File -FilePath "monitoring/prometheus.yml" -Encoding UTF8

# ─── FILE 5: grafana datasource ───
Write-Host "Writing grafana datasource..." -ForegroundColor Yellow
@'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
'@ | Out-File -FilePath "monitoring/grafana/provisioning/datasources/datasource.yml" -Encoding UTF8

# ─── FILE 6: init.sql ───
Write-Host "Writing backend/sql/init.sql..." -ForegroundColor Yellow
@'
CREATE TYPE exam_state AS ENUM (
    'SCHEDULED',
    'IDENTITY_CHECK',
    'IN_PROGRESS',
    'PAUSED',
    'SUSPENDED',
    'FLAGGED',
    'SUBMITTED',
    'REPORT_GENERATED',
    'ARCHIVED'
);

CREATE TYPE violation_severity AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

CREATE TABLE IF NOT EXISTS exam_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_code       VARCHAR(50) NOT NULL,
    student_id      VARCHAR(100) NOT NULL,
    state           exam_state NOT NULL DEFAULT 'SCHEDULED',
    livekit_room    VARCHAR(200),
    scheduled_at    TIMESTAMP DEFAULT NOW(),
    identity_at     TIMESTAMP,
    started_at      TIMESTAMP,
    paused_at       TIMESTAMP,
    resumed_at      TIMESTAMP,
    submitted_at    TIMESTAMP,
    report_at       TIMESTAMP,
    archived_at     TIMESTAMP,
    face_match_score    FLOAT,
    voice_match_score   FLOAT,
    identity_verified   BOOLEAN DEFAULT FALSE,
    risk_score      FLOAT DEFAULT 0.0,
    risk_level      VARCHAR(20) DEFAULT 'GREEN',
    total_violations INTEGER DEFAULT 0,
    recording_url   TEXT,
    report_url      TEXT,
    erp_webhook_sent    BOOLEAN DEFAULT FALSE,
    erp_webhook_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(exam_code, student_id)
);

CREATE TABLE IF NOT EXISTS state_transitions (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID REFERENCES exam_sessions(id),
    from_state      exam_state,
    to_state        exam_state NOT NULL,
    reason          TEXT,
    metadata        JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS violations (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID REFERENCES exam_sessions(id),
    violation_type  VARCHAR(50) NOT NULL,
    severity        violation_severity NOT NULL,
    confidence      FLOAT,
    description     TEXT,
    evidence_url    TEXT,
    frame_timestamp FLOAT,
    consecutive_count   INTEGER DEFAULT 1,
    duration_seconds    FLOAT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS heartbeats (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID REFERENCES exam_sessions(id),
    app_hash        VARCHAR(64),
    display_count   INTEGER,
    vm_detected     BOOLEAN DEFAULT FALSE,
    active_processes TEXT[],
    usb_devices     TEXT[],
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS behavioral_telemetry (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID REFERENCES exam_sessions(id),
    event_type      VARCHAR(30),
    key_flight_time FLOAT[],
    key_hold_time   FLOAT[],
    mouse_x         INTEGER,
    mouse_y         INTEGER,
    mouse_speed     FLOAT,
    tab_switches    INTEGER DEFAULT 0,
    copy_paste_count INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evidence_hashes (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID REFERENCES exam_sessions(id),
    file_type       VARCHAR(30),
    file_url        TEXT NOT NULL,
    sha256_hash     VARCHAR(64) NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE RULE protect_evidence_hashes_update AS
    ON UPDATE TO evidence_hashes DO INSTEAD NOTHING;
CREATE RULE protect_evidence_hashes_delete AS
    ON DELETE TO evidence_hashes DO INSTEAD NOTHING;

CREATE TABLE IF NOT EXISTS webhook_dlq (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID REFERENCES exam_sessions(id),
    endpoint_url    TEXT NOT NULL,
    payload         JSONB NOT NULL,
    http_status     INTEGER,
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 5,
    next_retry_at   TIMESTAMP,
    resolved        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sessions_exam_code ON exam_sessions(exam_code);
CREATE INDEX idx_sessions_student ON exam_sessions(student_id);
CREATE INDEX idx_sessions_state ON exam_sessions(state);
CREATE INDEX idx_violations_session ON violations(session_id);
CREATE INDEX idx_violations_type ON violations(violation_type);
CREATE INDEX idx_heartbeats_session ON heartbeats(session_id);
CREATE INDEX idx_telemetry_session ON behavioral_telemetry(session_id);
CREATE INDEX idx_dlq_unresolved ON webhook_dlq(resolved, next_retry_at)
    WHERE resolved = FALSE;
'@ | Out-File -FilePath "backend/sql/init.sql" -Encoding UTF8

# ─── FILE 7: backend/.env ───
Write-Host "Writing backend/.env..." -ForegroundColor Yellow
@'
DATABASE_URL=postgresql://admin:supersecretpassword@localhost:5435/proctorshield
REDIS_URL=redis://localhost:6379
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=f47ac10b58cc4372a5670e02b2c3d479f47ac10b58cc4372
LIVEKIT_URL=ws://localhost:7880
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=supersecretpassword
MINIO_BUCKET_RECORDINGS=exam-recordings
MINIO_BUCKET_EVIDENCE=exam-evidence
MINIO_BUCKET_REPORTS=forensic-reports
ERP_WEBHOOK_URL=http://localhost:8080/api/v1/exam-results
ERP_JWT_SECRET=shared-secret-with-java-erp
YOLO_CONFIDENCE_THRESHOLD=0.5
FACE_MATCH_THRESHOLD=0.6
VIOLATION_CONSECUTIVE_FRAMES=3
'@ | Out-File -FilePath "backend/.env" -Encoding UTF8

# ─── FILE 9: export_models.py ───
Write-Host "Writing backend/export_models.py..." -ForegroundColor Yellow
@'
"""
Export AI models to ONNX format for Triton Inference Server.
Run once: python export_models.py
"""
import os
from pathlib import Path

def export_yolo():
    from ultralytics import YOLO
    model = YOLO("yolov8n.pt")
    output = Path("../model_repository/yolov8_detector/1")
    output.mkdir(parents=True, exist_ok=True)
    model.export(format="onnx", imgsz=640, dynamic=True, simplify=True)
    os.rename("yolov8n.onnx", str(output / "model.onnx"))
    print("YOLOv8 exported to ONNX")

def export_silero_vad():
    import urllib.request
    output = Path("../model_repository/silero_vad/1")
    output.mkdir(parents=True, exist_ok=True)
    url = "https://models.silero.ai/models/en/en_v5.onnx"
    dest = output / "model.onnx"
    if not dest.exists():
        print("Downloading Silero VAD...")
        urllib.request.urlretrieve(url, str(dest))
        print("Silero VAD downloaded")
    else:
        print("Silero VAD already exists")

def create_triton_configs():
    yolo_config = Path("../model_repository/yolov8_detector/config.pbtxt")
    yolo_config.parent.mkdir(parents=True, exist_ok=True)
    yolo_config.write_text("""name: "yolov8_detector"
platform: "onnxruntime_onnx"
max_batch_size: 32
input [
  {
    name: "images"
    data_type: TYPE_FP32
    dims: [3, 640, 640]
  }
]
output [
  {
    name: "output0"
    data_type: TYPE_FP32
    dims: [-1, -1]
  }
]
dynamic_batching {
  preferred_batch_size: [8, 16, 32]
  max_queue_delay_microseconds: 100000
}""")
    vad_dir = Path("../model_repository/silero_vad")
    vad_dir.mkdir(parents=True, exist_ok=True)
    (vad_dir / "config.pbtxt").write_text("""name: "silero_vad"
platform: "onnxruntime_onnx"
max_batch_size: 1""")
    print("Triton configs created")

if __name__ == "__main__":
    print("=== Exporting Models for Triton ===")
    export_yolo()
    export_silero_vad()
    create_triton_configs()
    print("=== Done ===")
'@ | Out-File -FilePath "backend/export_models.py" -Encoding UTF8

# ─── LAUNCH ───
Write-Host ""
Write-Host "=== ALL FILES CREATED ===" -ForegroundColor Green
Write-Host ""
Write-Host "Now run these commands:" -ForegroundColor Cyan
Write-Host "  docker compose down" -ForegroundColor White
Write-Host "  Remove-Item -Recurse -Force local_db_data" -ForegroundColor White
Write-Host "  docker compose up -d" -ForegroundColor White
Write-Host "  docker compose ps" -ForegroundColor White
Write-Host ""
Write-Host "Then export models:" -ForegroundColor Cyan
Write-Host "  cd backend" -ForegroundColor White
Write-Host "  python export_models.py" -ForegroundColor White