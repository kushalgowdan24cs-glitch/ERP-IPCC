import React, { useState, useEffect, useRef, useCallback } from "react";

/**
 * IdentityVerification — Active Liveness + Face Match
 *
 * Props:
 *   wsRef          — ref to the existing WebSocket connection
 *   videoRef       — ref to the existing <video> element
 *   session        — session object { student_id, student_name, ... }
 *   onVerified     — callback when identity is fully verified
 *   onFailed       — callback when verification fails (optional)
 *   backendRest    — REST base URL for fetching ERP photo
 *
 * This component does NOT create its own WebSocket or camera.
 * It reuses the ones already created by App.jsx.
 */

const CHALLENGE_ICONS = {
  BLINK: "👁️",
  TURN_LEFT: "⬅️",
  TURN_RIGHT: "➡️",
  NOD_UP: "⬆️",
  OPEN_MOUTH: "😮",
};

function toBase64Jpeg(videoEl) {
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, 640, 480);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
  return dataUrl.split(",")[1];
}

export default function IdentityVerification({
  wsRef,
  videoRef,
  session,
  onVerified,
  onFailed,
  backendRest = "http://localhost:8000",
}) {
  // ── Liveness State ──
  const [livenessState, setLivenessState] = useState("IDLE");
  // IDLE → PASSIVE_CHECK → CHALLENGING → MATCHING → DONE → FAILED
  const [challenges, setChallenges] = useState([]);
  const [currentChallenge, setCurrentChallenge] = useState(null);
  const [instruction, setInstruction] = useState("");
  const [timeLeft, setTimeLeft] = useState(0);
  const [progress, setProgress] = useState({ completed: 0, total: 0, percent: 0 });
  const [feedback, setFeedback] = useState(null);

  // ── Result State ──
  const [resultMsg, setResultMsg] = useState("");
  const [resultSuccess, setResultSuccess] = useState(false);
  const [similarity, setSimilarity] = useState(null);

  // ── Frame sending interval ──
  const frameIntervalRef = useRef(null);
  const messageHandlerRef = useRef(null);

  const isActive = ["STARTING", "PASSIVE_CHECK", "CHALLENGING", "MATCHING"].includes(livenessState);

  // ═══════════════════════════════════════════════════════════
  //  WebSocket message handler — listens for liveness messages
  // ═══════════════════════════════════════════════════════════

  const handleMessage = useCallback((evt) => {
    let msg;
    try {
      msg = JSON.parse(evt.data);
    } catch {
      return;
    }

    // ── Liveness session created ──
    if (msg.type === "liveness_session_created") {
      setChallenges(msg.challenges || []);
      setLivenessState("PASSIVE_CHECK");
      setInstruction("Look straight at the camera...");
      startFrames();
      return;
    }

    // ── Liveness progress update ──
    if (msg.type === "liveness_update") {
      if (msg.state === "PASSIVE_CHECK") {
        setLivenessState("PASSIVE_CHECK");
        setInstruction("Analyzing... hold still and look at the camera");
      }
      if (msg.state === "CHALLENGING") {
        setLivenessState("CHALLENGING");
        setCurrentChallenge(msg.current_challenge || null);
        setInstruction(msg.instruction || "");
        setTimeLeft(msg.time_remaining || 0);
        if (msg.progress) setProgress(msg.progress);
        setFeedback(msg.feedback || null);
      }
      return;
    }

    // ── Liveness final result ──
    if (msg.type === "liveness_result") {
      if (msg.state === "PASSED") {
        setLivenessState("MATCHING");
        setInstruction("Liveness verified ✓  Matching your face...");
      }
      if (msg.state === "FAILED") {
        setLivenessState("FAILED");
        setInstruction(msg.message || "Liveness check failed");
        setResultMsg(msg.message || "Verification failed. Try again.");
        setResultSuccess(false);
        stopFrames();
      }
      return;
    }

    // ── Face match result (sent after liveness passes) ──
    if (msg.type === "enrollment_result") {
      stopFrames();
      if (msg.success) {
        setLivenessState("DONE");
        setResultMsg(msg.message || "Identity verified!");
        setResultSuccess(true);
        setSimilarity(msg.similarity || null);
        // Delay callback so user sees the success state
        setTimeout(() => onVerified?.(msg), 1500);
      } else {
        setLivenessState("FAILED");
        setResultMsg(msg.message || "Face does not match. Try again.");
        setResultSuccess(false);
        setSimilarity(msg.similarity || null);
        onFailed?.(msg);
      }
      return;
    }
  }, [onVerified, onFailed]);

  // ── Attach / detach the message listener ──
  useEffect(() => {
    const ws = wsRef?.current;
    if (!ws) return;

    // Store ref so we can remove the exact same function
    messageHandlerRef.current = handleMessage;
    ws.addEventListener("message", handleMessage);

    return () => {
      ws.removeEventListener("message", handleMessage);
    };
  }, [wsRef, handleMessage]);

  // ── Cleanup on unmount ──
  useEffect(() => {
    return () => {
      stopFrames();
    };
  }, []);

  // ═══════════════════════════════════════════════════════════
  //  Frame sending — 8 FPS during liveness check
  // ═══════════════════════════════════════════════════════════

  function startFrames() {
    stopFrames();
    frameIntervalRef.current = setInterval(() => {
      const ws = wsRef?.current;
      const v = videoRef?.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || !v || v.readyState < 2) return;
      ws.send(JSON.stringify({
        type: "liveness_frame",
        frame: toBase64Jpeg(v),
        timestamp: Date.now() / 1000,
      }));
    }, 125); // 8 FPS
  }

  function stopFrames() {
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
  }

  // ═══════════════════════════════════════════════════════════
  //  Start / Retry liveness
  // ═══════════════════════════════════════════════════════════

  function startLiveness() {
    const ws = wsRef?.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    // Reset all state
    setLivenessState("STARTING");
    setChallenges([]);
    setCurrentChallenge(null);
    setInstruction("Starting liveness check...");
    setTimeLeft(0);
    setProgress({ completed: 0, total: 0, percent: 0 });
    setFeedback(null);
    setResultMsg("");
    setResultSuccess(false);
    setSimilarity(null);

    ws.send(JSON.stringify({
      type: "start_liveness",
      student_id: session?.student_id,
    }));
  }

  // ═══════════════════════════════════════════════════════════
  //  Styling helpers
  // ═══════════════════════════════════════════════════════════

  const stateColor = {
    IDLE: "#64748b",
    STARTING: "#64748b",
    PASSIVE_CHECK: "#3b82f6",
    CHALLENGING: "#f59e0b",
    MATCHING: "#3b82f6",
    DONE: "#22c55e",
    FAILED: "#ef4444",
  };

  const stateLabel = {
    IDLE: "Ready",
    STARTING: "Starting...",
    PASSIVE_CHECK: "Scanning...",
    CHALLENGING: "Challenge",
    MATCHING: "Matching...",
    DONE: "✓ Verified",
    FAILED: "✗ Failed",
  };

  const color = stateColor[livenessState] || "#64748b";
  const label = stateLabel[livenessState] || livenessState;
  const studentId = session?.student_id || "STU001";

  // ═══════════════════════════════════════════════════════════
  //  RENDER
  // ═══════════════════════════════════════════════════════════

  return (
    <div style={styles.container}>
      <h3 style={styles.title}>🔐 Biometric Identity Verification</h3>
      <p style={styles.subtitle}>
        Complete the liveness challenge to prove you are a real person, then your face will be matched against your college ID.
      </p>

      {/* ── Photo + Camera side by side ── */}
      <div style={styles.dualView}>
        {/* ERP Photo */}
        <div style={styles.photoColumn}>
          <p style={styles.label}>📷 College ID (ERP)</p>
          <img
            src={`${backendRest}/api/v1/sessions/student-photo/${studentId}`}
            alt="College ID"
            style={styles.erpPhoto}
            onError={(e) => { e.target.style.display = "none"; }}
          />
        </div>

        <div style={{ fontSize: 28, color: "#4ade80", alignSelf: "center" }}>⟷</div>

        {/* Live Camera with overlays */}
        <div style={styles.photoColumn}>
          <p style={styles.label}>🎥 Live Webcam</p>
          <div style={{
            ...styles.cameraContainer,
            borderColor: color,
            boxShadow: livenessState === "DONE"
              ? "0 0 25px rgba(34,197,94,0.4)"
              : livenessState === "FAILED"
                ? "0 0 25px rgba(239,68,68,0.4)"
                : "0 4px 15px rgba(0,0,0,0.05)",
          }}>
            <video
              ref={videoRef}
              autoPlay muted playsInline
              style={styles.video}
            />

            {/* Face outline guide */}
            {isActive && (
              <div style={{
                ...styles.faceOutline,
                borderColor: color,
              }} />
            )}

            {/* Status badge */}
            <div style={{ ...styles.badge, backgroundColor: color }}>
              {label}
            </div>

            {/* Timer */}
            {livenessState === "CHALLENGING" && timeLeft > 0 && (
              <div style={styles.timer}>
                {Math.ceil(timeLeft)}s
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Challenge instruction ── */}
      {isActive && (
        <div style={{ ...styles.instructionBox, borderLeftColor: color }}>
          {currentChallenge && CHALLENGE_ICONS[currentChallenge] && (
            <span style={{ fontSize: 26 }}>{CHALLENGE_ICONS[currentChallenge]}</span>
          )}
          <p style={styles.instructionText}>{instruction}</p>
        </div>
      )}

      {/* ── Progress bar + step dots ── */}
      {challenges.length > 0 && livenessState !== "IDLE" && (
        <div style={styles.progressWrapper}>
          {/* Bar */}
          <div style={styles.progressTrack}>
            <div style={{
              ...styles.progressFill,
              width: `${progress.percent}%`,
              backgroundColor: color,
            }} />
          </div>

          {/* Step dots */}
          <div style={styles.stepsRow}>
            {challenges.map((ch, i) => {
              const done = i < progress.completed;
              const active = i === progress.completed && livenessState === "CHALLENGING";
              return (
                <div key={i} style={{
                  ...styles.stepDot,
                  background: done ? "#22c55e" : active ? "#f59e0b" : "#e2e8f0",
                  color: done || active ? "#fff" : "#64748b",
                }}>
                  {done ? "✓" : (CHALLENGE_ICONS[ch.type] || (i + 1))}
                </div>
              );
            })}
          </div>
          <p style={styles.progressLabel}>
            {progress.completed}/{progress.total} challenges
          </p>
        </div>
      )}

      {/* ── Blink counter ── */}
      {feedback && currentChallenge === "BLINK" && (
        <div style={styles.blinkCounter}>
          Blinks: {feedback.blinks_detected || 0} / {feedback.blinks_needed || 2}
        </div>
      )}

      {/* ── Result message ── */}
      {resultMsg && (
        <div style={{
          ...styles.resultBox,
          background: resultSuccess ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
          borderColor: resultSuccess ? "#22c55e" : "#ef4444",
        }}>
          <p style={{
            ...styles.resultText,
            color: resultSuccess ? "#22c55e" : "#ef4444",
          }}>
            {resultSuccess ? "✅ " : "❌ "}{resultMsg}
          </p>
          {similarity !== null && similarity > 0 && (
            <p style={styles.similarityText}>
              Confidence: {(similarity * 100).toFixed(1)}%
            </p>
          )}
        </div>
      )}

      {/* ── Action button ── */}
      <div style={styles.buttonRow}>
        <button
          onClick={startLiveness}
          disabled={isActive}
          style={{
            ...styles.primaryBtn,
            background: isActive ? "#94a3b8" : "#3b82f6",
            cursor: isActive ? "not-allowed" : "pointer",
          }}
        >
          {livenessState === "FAILED"
            ? "🔄 Retry Verification"
            : livenessState === "IDLE"
              ? "🔐 Start Verification"
              : isActive
                ? "Verifying..."
                : livenessState === "DONE"
                  ? "✅ Verified"
                  : "🔐 Start Verification"
          }
        </button>
      </div>

      {/* ── Help text ── */}
      <p style={styles.helpText}>
        Ensure your face is clearly visible, well-lit, and centered.
        <br />Remove hats, sunglasses, or masks. You will be asked to blink, turn your head, or open your mouth.
      </p>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
//  STYLES
// ═══════════════════════════════════════════════════════════

const styles = {
  container: {
    maxWidth: 580,
    margin: "0 auto",
    padding: "8px 16px",
    textAlign: "center",
  },
  title: {
    marginBottom: 6,
    fontSize: 20,
    fontWeight: 700,
    color: "#0f172a",
  },
  subtitle: {
    color: "#888",
    fontSize: 13,
    marginBottom: 16,
  },

  // ── Dual view ──
  dualView: {
    display: "flex",
    gap: 16,
    justifyContent: "center",
    alignItems: "flex-start",
    marginBottom: 16,
    flexWrap: "wrap",
  },
  photoColumn: {
    textAlign: "center",
  },
  label: {
    fontSize: 12,
    color: "#64748b",
    marginBottom: 4,
    fontWeight: 600,
  },
  erpPhoto: {
    width: 200,
    height: 200,
    borderRadius: 16,
    border: "3px solid #4ade80",
    objectFit: "cover",
    background: "#f8fafc",
    boxShadow: "0 4px 15px rgba(0,0,0,0.05)",
  },

  // ── Camera container ──
  cameraContainer: {
    position: "relative",
    width: 240,
    height: 240,
    borderRadius: 16,
    border: "3px solid #3b82f6",
    overflow: "hidden",
    background: "#000",
    transition: "border-color 0.3s, box-shadow 0.3s",
  },
  video: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  faceOutline: {
    position: "absolute",
    top: "12%",
    left: "22%",
    width: "56%",
    height: "70%",
    border: "2px dashed",
    borderRadius: "50%",
    pointerEvents: "none",
    opacity: 0.6,
    transition: "border-color 0.3s",
  },
  badge: {
    position: "absolute",
    top: 8,
    right: 8,
    color: "#fff",
    padding: "3px 10px",
    borderRadius: 16,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.3,
  },
  timer: {
    position: "absolute",
    bottom: 8,
    right: 8,
    background: "rgba(0,0,0,0.7)",
    color: "#fff",
    padding: "4px 10px",
    borderRadius: 8,
    fontSize: 16,
    fontWeight: 700,
    fontVariantNumeric: "tabular-nums",
  },

  // ── Instruction ──
  instructionBox: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    padding: "12px 20px",
    margin: "0 auto 12px",
    maxWidth: 460,
    background: "rgba(255,255,255,0.85)",
    borderLeft: "4px solid #64748b",
    borderRadius: 10,
    transition: "border-color 0.3s",
  },
  instructionText: {
    margin: 0,
    fontSize: 15,
    fontWeight: 600,
    color: "#1e293b",
  },

  // ── Progress ──
  progressWrapper: {
    maxWidth: 400,
    margin: "0 auto 14px",
  },
  progressTrack: {
    height: 5,
    background: "#e2e8f0",
    borderRadius: 3,
    overflow: "hidden",
    marginBottom: 8,
  },
  progressFill: {
    height: "100%",
    borderRadius: 3,
    transition: "width 0.4s ease, background-color 0.3s",
  },
  stepsRow: {
    display: "flex",
    justifyContent: "center",
    gap: 8,
    marginBottom: 4,
  },
  stepDot: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    fontWeight: 700,
    transition: "background-color 0.3s",
  },
  progressLabel: {
    margin: 0,
    fontSize: 12,
    color: "#94a3b8",
    textAlign: "center",
  },

  // ── Feedback ──
  blinkCounter: {
    display: "inline-block",
    padding: "5px 14px",
    background: "#fffbeb",
    border: "1px solid #fbbf24",
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 600,
    marginBottom: 10,
  },

  // ── Result ──
  resultBox: {
    padding: "10px 18px",
    margin: "8px auto 12px",
    maxWidth: 420,
    border: "2px solid",
    borderRadius: 10,
    display: "inline-block",
  },
  resultText: {
    margin: 0,
    fontSize: 14,
    fontWeight: 600,
  },
  similarityText: {
    margin: "4px 0 0",
    fontSize: 12,
    color: "#64748b",
  },

  // ── Buttons ──
  buttonRow: {
    display: "flex",
    justifyContent: "center",
    gap: 12,
    marginTop: 8,
  },
  primaryBtn: {
    fontSize: 16,
    padding: "10px 30px",
    border: "none",
    borderRadius: 10,
    color: "#fff",
    fontWeight: 600,
    transition: "background 0.2s",
  },

  // ── Help ──
  helpText: {
    textAlign: "center",
    marginTop: 14,
    fontSize: 12,
    color: "#94a3b8",
    lineHeight: 1.5,
  },
};