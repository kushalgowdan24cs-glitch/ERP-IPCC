import React, { useEffect, useState, useRef, useCallback } from "react";
import "./AdminDashboard.css";

// Use same-origin via Vite proxy
const WS_PROTO = window.location.protocol === "https:" ? "wss:" : "ws:";
const BACKEND_WS = `${WS_PROTO}//${window.location.host}/ws/dashboard`;
const BACKEND_HTTP = `${window.location.protocol}//${window.location.host}`;

// ── Severity & Label Helpers ──
const SEV_ICON = { CRITICAL: "🔴", HIGH: "🟠", MEDIUM: "🟡", LOW: "🔵", INFO: "ℹ️" };

const FLAG_LABELS = {
  NO_FACE_DETECTED:           { label: "No one on screen",                icon: "👤" },
  FACE_ABSENT_EXTENDED:       { label: "Student absent from camera",      icon: "🚫" },
  MULTIPLE_FACES:             { label: "Multiple people detected",         icon: "👥" },
  MULTIPLE_PERSONS_IN_FRAME:  { label: "Multiple people in frame",         icon: "👥" },
  IDENTITY_MISMATCH:          { label: "Face doesn't match college ID",    icon: "🔓" },
  BANNED_OBJECT_CELL_PHONE:   { label: "Cell phone detected",              icon: "📵" },
  BANNED_OBJECT_BOOK:         { label: "Book detected in frame",           icon: "📖" },
  BANNED_OBJECT_LAPTOP:       { label: "Extra laptop detected",            icon: "💻" },
  BANNED_OBJECT_TV:           { label: "TV/Monitor detected",              icon: "🖥️" },
  BANNED_OBJECT_SMARTWATCH:   { label: "Smartwatch detected",              icon: "⌚" },
  BANNED_OBJECT_EARBUD:       { label: "Earbud detected",                  icon: "🎧" },
  GAZE_AWAY_SUSTAINED:        { label: "Looking away from screen",         icon: "👀" },
  SPEECH_DETECTED:            { label: "Speech activity detected",         icon: "🗣️" },
  UNKNOWN_SPEAKER_DETECTED:   { label: "Unknown voice in room",            icon: "🔊" },
  TAB_SWITCH_ATTEMPT:         { label: "Tried to switch tabs",             icon: "🔀" },
  TAB_SWITCH_OR_MINIMIZE:     { label: "Window lost focus / tab switch",   icon: "🔀" },
  APP_LOST_FOCUS:             { label: "App lost focus",                   icon: "🪟" },
  CLIPBOARD_VIOLATION:        { label: "Copy-paste attempt blocked",       icon: "📋" },
  BLOCKED_PROCESS_RUNNING:    { label: "Blacklisted app terminated",       icon: "🔒" },
  LIVENESS_FAILED:            { label: "Failed biometric liveness",        icon: "🤖" },
  IDENTITY_VERIFIED:          { label: "Identity verified",                icon: "✅" },
};

const getFlagLabel = (flagType) => {
  const entry = FLAG_LABELS[flagType];
  if (entry) return `${entry.icon} ${entry.label}`;
  return flagType.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
};

const formatFlagTime = (ts) => {
  if (!ts) return "--:--:--";
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
  return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true });
};

export default function AdminDashboard() {
  const [sessions, setSessions] = useState({});
  const [wsConnected, setWsConnected] = useState(false);
  const [clock, setClock] = useState(new Date());
  
  // Tracks which specific violation clip is currently playing
  const [activeClipId, setActiveClipId] = useState(null); 
  
  // Tracks video load errors so we can offer a "Retry" button
  const [videoErrors, setVideoErrors] = useState({});
  
  const wsRef = useRef(null);

  // ── Live clock ──
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // ── WebSocket ──
  const connectWs = useCallback(() => {
    const ws = new WebSocket(BACKEND_WS);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      console.log("[Admin] WebSocket connected");
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);

        // Initial Load of all sessions
        if (msg.type === "initial_state" && Array.isArray(msg.sessions)) {
          setSessions((prev) => {
            const map = { ...prev }; 
            msg.sessions.forEach((s) => {
              const flags = s.flags || [];
              let runningScore = 0;
              const log = flags.map((f) => {
                runningScore += (f.risk_points ?? 0);
                return {
                  id: `${f.timestamp}_${f.flag_type}`, 
                  flag_type: f.flag_type || "UNKNOWN",
                  severity: f.severity || "MEDIUM",
                  message: f.message || f.flag_type,
                  risk_points: f.risk_points ?? 0,
                  timestamp: f.timestamp || 0,
                  evidence_url: f.evidence_url || null,
                  running_score: runningScore,
                };
              });
              map[s.session_id || s.id] = {
                ...s,
                violation_log: log,
                lastUpdate: Date.now(),
              };
            });
            return map;
          });
        }

        // Live Updates
        if (msg.type === "session_update" && msg.session_id) {
          setSessions((prev) => {
            const existing = prev[msg.session_id] || {};
            const existingLog = existing.violation_log || [];

            let updatedLog = existingLog;
            if (msg.new_flags && msg.new_flags.length > 0) {
              const newEntries = msg.new_flags.map((f) => ({
                id: `${f.timestamp}_${f.flag_type}`,
                flag_type: f.flag_type || "UNKNOWN",
                severity: f.severity || "MEDIUM",
                message: f.message || f.flag_type,
                risk_points: f.risk_points ?? 0,
                timestamp: f.timestamp || Date.now() / 1000,
                evidence_url: f.evidence_url || null,
                running_score: msg.risk_score ?? existing.risk_score ?? 0,
              }));
              updatedLog = [...existingLog, ...newEntries];
            }

            return {
              ...prev,
              [msg.session_id]: {
                ...existing,
                student_name: msg.student_name ?? existing.student_name,
                risk_score: msg.risk_score ?? existing.risk_score ?? 0,
                risk_level: msg.risk_level ?? existing.risk_level ?? "GREEN",
                total_flags: msg.total_flags ?? existing.total_flags ?? 0,
                status: msg.status ?? existing.status ?? "in_progress",
                session_id: msg.session_id,
                violation_log: updatedLog,
                lastUpdate: Date.now(),
              }
            };
          });
        }
      } catch (e) {
        console.error("[Admin] WS parse error:", e);
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      setTimeout(connectWs, 3000);
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connectWs();
    return () => wsRef.current?.close();
  }, [connectWs]);

  // 🚨 DELETE SESSION FUNCTION 🚨
  const deleteSession = (sessionId) => {
    if (wsRef.current && wsRef.current.readyState === 1) {
      wsRef.current.send(JSON.stringify({ type: "delete_session", session_id: sessionId }));
    }
    setSessions((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
  };

  const list = Object.values(sessions).sort((a, b) => b.lastUpdate - a.lastUpdate);
  const totalSessions = list.length;
  const flaggedCount = list.filter((s) => s.risk_level === "RED" || s.risk_level === "ORANGE").length;
  const cleanCount = list.filter((s) => s.risk_level === "GREEN").length;
  const totalViolations = list.reduce((acc, s) => acc + (s.violation_log?.length || 0), 0);

  const getInitials = (name) => {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/);
    return parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : name.slice(0, 2).toUpperCase();
  };

  const getStatusBadge = (status) => {
    if (status === "completed") return <span className="status-badge completed">✅ Completed</span>;
    if (status === "disconnected") return <span className="status-badge offline">💤 Offline</span>;
    return <span className="status-badge live">🟢 Live</span>;
  };

  // Helper to safely mark a video as failed so we can show the Retry button
  const handleVideoError = (clipId) => {
    setVideoErrors(prev => ({ ...prev, [clipId]: true }));
  };

  const retryVideo = (clipId) => {
    setVideoErrors(prev => ({ ...prev, [clipId]: false }));
  };

  return (
    <div className="admin-root">
      {/* Mesh Background */}
      <div className="admin-mesh-bg">
        <div className="admin-blob blob-1"></div>
        <div className="admin-blob blob-2"></div>
        <div className="admin-blob blob-3"></div>
      </div>

      <header className="admin-header glass-panel">
        <div className="admin-header-left">
          <div className="admin-logo-box">🛡️</div>
          <div>
            <h1>Forensic Evidence Log</h1>
            <p className="subtitle">ProctorShield Auto-Generated Violation Reports</p>
          </div>
        </div>
        <div className="admin-header-right">
          <span className="admin-clock">{clock.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true })}</span>
          <span className={`ws-status ${wsConnected ? "connected" : "disconnected"}`}>
            <span className="ws-dot" />
            {wsConnected ? "System Online" : "Reconnecting…"}
          </span>
        </div>
      </header>

      {/* Stats Row */}
      <section className="admin-stats">
        <div className="stat-card glass-panel"><div className="stat-icon blue">📋</div><div className="stat-info"><span className="stat-value">{totalSessions}</span><span className="stat-label">Total Exams</span></div></div>
        <div className="stat-card glass-panel"><div className="stat-icon green">✅</div><div className="stat-info"><span className="stat-value">{cleanCount}</span><span className="stat-label">Clean Exams</span></div></div>
        <div className="stat-card glass-panel"><div className="stat-icon red">🚨</div><div className="stat-info"><span className="stat-value">{flaggedCount}</span><span className="stat-label">Flagged Exams</span></div></div>
        <div className="stat-card glass-panel"><div className="stat-icon violet">⚠️</div><div className="stat-info"><span className="stat-value">{totalViolations}</span><span className="stat-label">Total Violations</span></div></div>
      </section>

      {/* Main Grid */}
      <div className="admin-body">
        {totalSessions === 0 ? (
          <div className="empty-state glass-panel">
            <div className="empty-state-icon">📭</div>
            <h3>No Records Found</h3>
            <p>Waiting for students to connect. Sessions will automatically populate here.</p>
          </div>
        ) : (
          <div className="session-grid">
            {list.map((s) => {
              const sid = s.session_id || s.id;
              const name = s.student_name || "Unknown";
              const riskLevel = s.risk_level || "GREEN";
              const riskScore = Math.round(s.risk_score ?? 0);
              const violationLog = s.violation_log || [];

              return (
                <div className="session-card glass-panel" key={sid}>
                  
                  {/* Top Bar: Student Info & Score & Delete Button */}
                  <div className="session-card-header">
                    <div className="session-student">
                      <div className="student-avatar">{getInitials(name)}</div>
                      <div className="student-info">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                          <h3 style={{ margin: 0, color: '#0f172a' }}>{name}</h3>
                          {getStatusBadge(s.status)}
                        </div>
                        <p className="session-id">{sid?.slice(0, 12)}…</p>
                      </div>
                    </div>
                    
                    <div style={{display: 'flex', alignItems: 'center', gap: '15px'}}>
                      <div className="score-block">
                        <span className="score-label">Risk Score</span>
                        <span className={`score-number ${riskLevel}`}>{riskScore}</span>
                      </div>
                      
                      {/* 🗑️ THE DELETE BUTTON */}
                      <button 
                        className="delete-btn"
                        title="Delete Record"
                        onClick={(e) => {
                          e.stopPropagation();
                          if(window.confirm(`Are you sure you want to delete the record for ${name}?`)) {
                            deleteSession(sid);
                          }
                        }}
                      >
                        🗑️
                      </button>
                    </div>

                  </div>

                  {/* Violation Timeline (Always visible) */}
                  <div className="violation-timeline-section">
                    <div className="timeline-header-fixed">
                      <span className="timeline-title">Forensic Timeline</span>
                      <span className="timeline-count">{violationLog.length} Events</span>
                    </div>

                    <div className="violation-timeline">
                      {violationLog.length === 0 ? (
                        <div className="timeline-empty">
                          <span>✅</span> Clean record. No violations detected.
                        </div>
                      ) : (
                        <>
                          {[...violationLog].reverse().map((v) => {
                            const sev = v.severity || "MEDIUM";
                            const tsInt = Math.trunc(v.timestamp);
                            
                            const mainUrl = v.evidence_url || `${BACKEND_HTTP}/api/v1/sessions/${sid}/recording/snippet/${sid}_${v.flag_type}_${tsInt}_main.webm`;
                            const deskUrl = v.evidence_url || `${BACKEND_HTTP}/api/v1/sessions/${sid}/recording/snippet/${sid}_${v.flag_type}_${tsInt}_secondary.webm`;
                            
                            const isPlayingMain = activeClipId === `${v.id}_main`;
                            const isPlayingDesk = activeClipId === `${v.id}_desk`;

                            return (
                              <div className={`timeline-row sev-${sev}`} key={v.id}>
                                <div className="timeline-row-main">
                                  <span className="tl-time">{formatFlagTime(v.timestamp)}</span>
                                  <div className="tl-event">
                                    <span className="tl-sev-icon">{SEV_ICON[sev] || "⚪"}</span>
                                    <div className="tl-event-detail">
                                      <span className="tl-flag-type">{getFlagLabel(v.flag_type)}</span>
                                    </div>
                                  </div>
                                  <span className="tl-points">+{v.risk_points}</span>
                                </div>
                                
                                {/* Inline DVR Buttons */}
                                <div className="dvr-btn-row">
                                  <button 
                                    className={`dvr-btn ${isPlayingMain ? 'active' : ''}`} 
                                    onClick={() => setActiveClipId(isPlayingMain ? null : `${v.id}_main`)}
                                  >
                                    <span style={{color: '#3b82f6'}}>{isPlayingMain ? '▼' : '▶️'}</span> Main Cam Clip
                                  </button>
                                  <button 
                                    className={`dvr-btn ${isPlayingDesk ? 'active' : ''}`} 
                                    onClick={() => setActiveClipId(isPlayingDesk ? null : `${v.id}_desk`)}
                                  >
                                    <span style={{color: '#a855f7'}}>{isPlayingDesk ? '▼' : '▶️'}</span> Desk Cam Clip
                                  </button>
                                </div>

                                {/* Smart Inline Video Player */}
                                {isPlayingMain && (
                                  <div className="inline-video-player">
                                    {videoErrors[`${v.id}_main`] ? (
                                      <div className="vid-error" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                                        <span>⏳ Clip buffering (takes ~10s)...</span>
                                        <button onClick={() => retryVideo(`${v.id}_main`)}>Retry</button>
                                      </div>
                                    ) : (
                                      <video controls autoPlay src={mainUrl} onError={() => handleVideoError(`${v.id}_main`)} />
                                    )}
                                  </div>
                                )}

                                {isPlayingDesk && (
                                  <div className="inline-video-player">
                                    {videoErrors[`${v.id}_desk`] ? (
                                      <div className="vid-error" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                                        <span>⏳ Clip buffering (takes ~10s)...</span>
                                        <button onClick={() => retryVideo(`${v.id}_desk`)}>Retry</button>
                                      </div>
                                    ) : (
                                      <video controls autoPlay src={deskUrl} onError={() => handleVideoError(`${v.id}_desk`)} />
                                    )}
                                  </div>
                                )}

                              </div>
                            );
                          })}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}