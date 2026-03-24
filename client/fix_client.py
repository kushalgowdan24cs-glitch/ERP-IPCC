import os

os.makedirs("src", exist_ok=True)

index_html = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ProctorShield Client</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""

main_jsx = """import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./App.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""

app_css = """:root{
  --bg:#0f172a; --panel:#1e293b; --card:#24324a;
  --text:#f1f5f9; --muted:#94a3b8; --accent:#3b82f6;
  --good:#22c55e; --warn:#f59e0b; --bad:#ef4444;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:Segoe UI,system-ui,Arial}
.container{max-width:900px;margin:0 auto;padding:24px}
.card{background:var(--panel);border-radius:14px;padding:22px;box-shadow:0 10px 40px rgba(0,0,0,.35)}
h1{margin:0 0 6px 0;font-size:22px}
p{margin:8px 0;color:var(--muted)}
input{width:100%;padding:14px 16px;border-radius:10px;border:1px solid #334155;background:#0b1220;color:var(--text);font-size:18px;letter-spacing:6px;text-transform:uppercase}
button{padding:12px 16px;border:0;border-radius:10px;background:var(--accent);color:white;font-weight:700;cursor:pointer}
.row{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-top:14px;flex-wrap:wrap}
.badge{padding:6px 12px;border-radius:999px;font-weight:800;font-size:12px}
.badge.good{background:rgba(34,197,94,.2);color:var(--good)}
.badge.warn{background:rgba(245,158,11,.2);color:var(--warn)}
.badge.bad{background:rgba(239,68,68,.2);color:var(--bad)}
.videoBox{margin-top:14px;overflow:hidden;border-radius:14px;border:2px solid #334155;background:#000;max-width:420px}
video{width:100%;display:block;transform:scaleX(-1)}
.q{margin-top:14px;padding:16px;border-radius:12px;background:var(--card)}
.opt{padding:12px 14px;border-radius:10px;background:#0b1220;border:1px solid #334155;margin:10px 0;cursor:pointer}
.opt.sel{border-color:var(--accent);background:rgba(59,130,246,.12)}
textarea{width:100%;min-height:140px;border-radius:10px;border:1px solid #334155;background:#0b1220;color:var(--text);padding:12px;font-size:15px}
.small{font-size:12px;color:var(--muted)}
"""

app_jsx = """import React, { useEffect, useMemo, useRef, useState } from "react";

const BACKEND_WS_BASE = "ws://localhost:8000";

function toBase64Jpeg(videoEl) {
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, 640, 480);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
  return dataUrl.split(",")[1];
}

export default function App() {
  const [stage, setStage] = useState("ENTER"); // ENTER -> ID -> EXAM -> DONE
  const [code, setCode] = useState("");
  const [wsState, setWsState] = useState("DISCONNECTED");
  const [session, setSession] = useState(null);
  const [riskScore, setRiskScore] = useState(0);
  const [riskLevel, setRiskLevel] = useState("GREEN");
  const [flags, setFlags] = useState([]);

  const [qIndex, setQIndex] = useState(0);
  const [answers, setAnswers] = useState({});

  const wsRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  const questions = session?.exam?.questions || [];

  async function startCameraMic() {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
      audio: true
    });
    streamRef.current = stream;
    if (videoRef.current) videoRef.current.srcObject = stream;
  }

  function stopMedia() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
  }

  function connect() {
    const c = code.trim().toUpperCase();
    if (!c) return;

    const ws = new WebSocket(`${BACKEND_WS_BASE}/ws/proctor/${c}`);
    wsRef.current = ws;

    ws.onopen = () => setWsState("CONNECTED");
    ws.onclose = () => setWsState("DISCONNECTED");
    ws.onerror = () => setWsState("ERROR");

    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);

      if (msg.type === "session_ready") {
        setSession(msg);
        setStage("ID");
        // request camera now
        startCameraMic().catch(err => alert("Camera/Mic permission needed: " + err));
      }

      if (msg.type === "enrollment_result") {
        if (msg.success) {
          setStage("EXAM");
          ws.send(JSON.stringify({ type: "exam_start", timestamp: Date.now() / 1000 }));
        } else {
          alert(msg.message || "Enrollment failed");
        }
      }

      if (msg.type === "flags") {
        setFlags(prev => [...prev, ...(msg.flags || [])]);
        setRiskScore(msg.risk_score ?? 0);
        setRiskLevel(msg.risk_level ?? "GREEN");
      }

      if (msg.type === "exam_completed") {
        setStage("DONE");
        stopMedia();
      }

      if (msg.type === "terminate") {
        alert("Terminated: " + (msg.reason || "unknown"));
        setStage("DONE");
        stopMedia();
      }
    };
  }

  // Send proctoring frames during EXAM
  useEffect(() => {
    if (stage !== "EXAM") return;

    const t = setInterval(() => {
      const ws = wsRef.current;
      const v = videoRef.current;
      if (!ws || ws.readyState !== 1 || !v) return;
      if (v.readyState < 2) return;

      const frame = toBase64Jpeg(v);
      ws.send(JSON.stringify({ type: "frame", frame, timestamp: Date.now() / 1000 }));
    }, 3000);

    return () => clearInterval(t);
  }, [stage]);

  function enrollFace() {
    const ws = wsRef.current;
    const v = videoRef.current;
    if (!ws || ws.readyState !== 1) return alert("WebSocket not connected");
    if (!v || v.readyState < 2) return alert("Camera not ready yet");

    const frame = toBase64Jpeg(v);
    ws.send(JSON.stringify({ type: "enroll_face", frame, timestamp: Date.now() / 1000 }));
  }

  function submitAnswer(value) {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) {
      ws.send(JSON.stringify({
        type: "answer_submit",
        question_index: qIndex,
        answer: String(value),
        timestamp: Date.now() / 1000
      }));
    }
    setAnswers(prev => ({ ...prev, [qIndex]: value }));
  }

  function next() {
    if (qIndex < questions.length - 1) setQIndex(qIndex + 1);
    else finish();
  }

  function finish() {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) {
      ws.send(JSON.stringify({ type: "exam_complete", timestamp: Date.now() / 1000 }));
    }
  }

  const riskBadgeClass =
    riskLevel === "GREEN" ? "good" :
    riskLevel === "YELLOW" || riskLevel === "ORANGE" ? "warn" : "bad";

  return (
    <div className="container">
      <div className="card">
        <div className="row">
          <div>
            <h1>ProctorShield Client</h1>
            <p className="small">Backend: {BACKEND_WS_BASE} | WS: {wsState}</p>
          </div>
          <span className={`badge ${riskBadgeClass}`}>Risk {Math.round(riskScore)} — {riskLevel}</span>
        </div>

        {stage === "ENTER" && (
          <>
            <p>Enter your session code (from the dashboard / API).</p>
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="2XBPKV" />
            <div className="row">
              <button onClick={connect}>Start</button>
              <span className="small">Use code: 2XBPKV</span>
            </div>
          </>
        )}

        {stage === "ID" && (
          <>
            <p>Identity Verification: look at the camera and click “Enroll Face”.</p>
            <div className="videoBox">
              <video ref={videoRef} autoPlay muted playsInline />
            </div>
            <div className="row">
              <button onClick={enrollFace}>Enroll Face</button>
              <span className="small">After enrollment you will enter the exam.</span>
            </div>
          </>
        )}

        {stage === "EXAM" && (
          <>
            <p><b>{session?.exam_title}</b> — Question {qIndex + 1} / {questions.length}</p>
            <div className="videoBox">
              <video ref={videoRef} autoPlay muted playsInline />
            </div>

            {questions[qIndex] && (
              <div className="q">
                <div><b>{questions[qIndex].text}</b></div>

                {questions[qIndex].type === "mcq" ? (
                  <div>
                    {questions[qIndex].options.map((opt, i) => (
                      <div
                        key={i}
                        className={"opt " + ((answers[qIndex] === i) ? "sel" : "")}
                        onClick={() => submitAnswer(i)}
                      >
                        {String.fromCharCode(65 + i)}. {opt}
                      </div>
                    ))}
                  </div>
                ) : (
                  <textarea
                    value={answers[qIndex] || ""}
                    onChange={(e) => submitAnswer(e.target.value)}
                    placeholder="Type your answer..."
                  />
                )}

                <div className="row">
                  <button onClick={next}>{qIndex < questions.length - 1 ? "Next" : "Submit Exam"}</button>
                  <span className="small">Flags received: {flags.length}</span>
                </div>
              </div>
            )}
          </>
        )}

        {stage === "DONE" && (
          <>
            <h1>Done</h1>
            <p>Session ended. Check dashboard for risk score and flags.</p>
          </>
        )}
      </div>
    </div>
  );
}
"""

def write(path, content):
  with open(path, "w", encoding="utf-8") as f:
    f.write(content)
  print(f"Wrote {path} ({len(content)} chars)")

write("index.html", index_html)
write("src/main.jsx", main_jsx)
write("src/App.jsx", app_jsx)
write("src/App.css", app_css)

print("Client files written. Now run: npm run dev:react")