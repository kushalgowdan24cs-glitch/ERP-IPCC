import React, { useEffect, useRef, useState } from "react";

// Build the WebSocket URL using the SAME origin as the page.
// Vite proxies /ws/* to the FastAPI backend, so this works on:
//   - localhost (ws://localhost:5173/ws/... → proxy → ws://localhost:8000/ws/...)
//   - ngrok HTTPS (wss://xxx.ngrok-free.dev/ws/... → proxy → ws://localhost:8000/ws/...)
function getWsBase() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

function toBase64Jpeg(videoEl) {
  const canvas = document.createElement("canvas");
  canvas.width = 480;
  canvas.height = 360;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, 480, 360);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.5);
  return dataUrl.split(",")[1];
}

export default function MobileStream() {
  const videoRef = useRef(null);
  const wsRef = useRef(null);

  const [status, setStatus] = useState("Requesting camera permissions...");
  const [wsStatus, setWsStatus] = useState("Connecting...");
  const [errorMsg, setErrorMsg] = useState("");
  const [frameCount, setFrameCount] = useState(0);

  const query = new URLSearchParams(window.location.search);
  const code = query.get("code");

  // ── Start camera ──
  useEffect(() => {
    if (!code) {
      setStatus("Error: No session code found in URL.");
      return;
    }

    let currentStream = null;

    const startVideo = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment", width: { ideal: 480 } },
        });

        currentStream = stream;
        setStatus("Camera Active 🟢");
        setErrorMsg("");

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      } catch (err) {
        setStatus("❌ Camera Blocked");
        setErrorMsg(err.message);
      }
    };

    startVideo();

    return () => {
      if (currentStream) {
        currentStream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [code]);

    const triggerSnippetCapture = null; // Removed continuous hooks

  // ── WebSocket connection ──
  useEffect(() => {
    if (!code) return;

    // Connect through the same origin — Vite proxies /ws/* to FastAPI
    const wsUrl = `${getWsBase()}/ws/mobile/${code}`;
    let ws;
    let reconnectTimer;

    function connectWs() {
      const triggerSnippetCapture = (flagType, timestamp) => {
        if (!videoRef.current || !videoRef.current.srcObject) return;
        try {
          const recorder = new MediaRecorder(videoRef.current.srcObject, { mimeType: 'video/webm' });
          const chunks = [];
          
          recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
          
          recorder.onstop = () => {
            const blob = new Blob(chunks, { type: 'video/webm' });
            const formData = new FormData();
            formData.append("file", blob);
            formData.append("camera_type", "secondary");
            formData.append("flag_type", flagType);
            formData.append("timestamp", timestamp || (Date.now() / 1000));

            fetch(`${getWsBase().replace("ws", "http")}/api/v1/sessions/${code}/recording/snippet`, {
              method: "POST",
              body: formData
            }).then(res => res.json())
              .then(data => console.log(`[Mobile DVR] Snippet uploaded: ${flagType}`))
              .catch(err => console.error("[Mobile DVR] Upload failed:", err));
          };

          // Record 10 seconds of evidence from the mobile camera
          recorder.start();
          setTimeout(() => {
            if (recorder.state !== 'inactive') recorder.stop();
          }, 10000);
        } catch (err) {
          console.error("Secondary snippet recorder failed:", err);
        }
      };

      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus("🟢 Connected to backend");
        console.log("[Mobile] WS connected:", wsUrl);
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          
          if (msg.type === "flags") {
            const newFlags = msg.flags || [];
            if (newFlags.length > 0) {
              const latest = newFlags[newFlags.length - 1];
              // Trigger DVR Snippet Recording for the latest violation!
              triggerSnippetCapture(latest.flag_type, latest.timestamp);
            }
          }
        } catch (e) {
          // ignore
        }
      };

      ws.onclose = () => {
        setWsStatus("🔴 Disconnected — retrying…");
        reconnectTimer = setTimeout(connectWs, 3000);
      };

      ws.onerror = () => ws.close();
    }

    connectWs();

    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [code]);

  // ── Send frames every 3 seconds ──
  useEffect(() => {
    if (!code) return;

    const interval = setInterval(() => {
      const ws = wsRef.current;
      const v = videoRef.current;

      if (!ws || ws.readyState !== 1 || !v || v.readyState < 2) return;

      try {
        const base64 = toBase64Jpeg(v);
        ws.send(
          JSON.stringify({
            type: "secondary_frame",
            frame: base64,
            timestamp: Date.now() / 1000,
          })
        );
        setFrameCount((prev) => prev + 1);
      } catch (e) {
        console.error("[Mobile] Frame send error:", e);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [code]);

  return (
    <div
      style={{
        background: "#111",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontFamily: "sans-serif",
        padding: "20px",
      }}
    >
      <h2 style={{ color: "#4ade80", margin: "0 0 6px" }}>📱 Side Camera Active</h2>
      <p style={{ marginBottom: "10px", color: "#aaa", fontSize: "14px" }}>
        Session: <strong>{code || "—"}</strong>
      </p>

      <div
        style={{
          background: "#222",
          padding: "10px 16px",
          borderRadius: "8px",
          marginBottom: "16px",
          textAlign: "center",
          width: "90%",
          maxWidth: "400px",
        }}
      >
        <p style={{ margin: 0, fontWeight: "bold", color: errorMsg ? "#ff4d4d" : "#4ade80", fontSize: "13px" }}>
          {status}
        </p>
        <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94a3b8" }}>
          {wsStatus} • Frames sent: {frameCount}
        </p>
        {errorMsg && (
          <p style={{ margin: "5px 0 0 0", fontSize: "12px", color: "#ff4d4d" }}>
            {errorMsg}
          </p>
        )}
      </div>

      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{
          width: "90%",
          maxWidth: "400px",
          height: "300px",
          borderRadius: "12px",
          border: "2px solid #333",
          backgroundColor: "#000",
          objectFit: "cover",
        }}
      />

      <p style={{ marginTop: "16px", fontSize: "11px", color: "#555", textAlign: "center" }}>
        Keep this screen open during the exam.<br />
        Frames are streamed to the proctor automatically.
      </p>
    </div>
  );
}