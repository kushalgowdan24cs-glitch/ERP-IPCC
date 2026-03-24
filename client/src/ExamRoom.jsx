import React, { useState, useEffect, useRef } from 'react';
import { LiveKitRoom, useTracks, VideoTrack, useRoomContext } from '@livekit/components-react';
import { Track } from 'livekit-client';
import * as faceapi from 'face-api.js';
import * as cocoSsd from '@tensorflow-models/coco-ssd';
import '@tensorflow/tfjs';
import QRCode from "react-qr-code";
import CodingTerminal from './CodingTerminal';
import '@livekit/components-styles';

const QUESTIONS = [
  {
    type: 'mcq',
    id: 1,
    text: 'What does CPU stand for?',
    options: ['Central Process Unit', 'Central Processing Unit', 'Computer Personal Unit', 'Central Processor Unit'],
  },
  {
    type: 'coding',
    id: 2,
    text: 'Write a Python function that takes a string input and prints it in ALL CAPS.',
    testCases: [
      { input: 'hello', expected: 'HELLO' },
      { input: 'proctorshield', expected: 'PROCTORSHIELD' },
      { input: 'bangalore123', expected: 'BANGALORE123' },
    ],
  },
  {
    type: 'mcq',
    id: 3,
    text: 'Which language is primarily used for React?',
    options: ['Python', 'Java', 'JavaScript', 'C++'],
  },
];


const EXAM_DURATION_SECONDS = 30 * 60;

function decodeJwtSafe(token) {
  if (!token) return {};
  try {
    const payload = token.split('.')[1];
    if (!payload) return {};
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const decoded = decodeURIComponent(
      atob(normalized)
        .split('')
        .map((char) => `%${`00${char.charCodeAt(0).toString(16)}`.slice(-2)}`)
        .join('')
    );
    return JSON.parse(decoded);
  } catch {
    return {};
  }
}

export default function ExamRoom({ erpToken, examCode, cameraId, micId }) {
  const [livekitToken, setLivekitToken] = useState(null);
  const [error, setError] = useState('');
  
  // Fetch Token
  useEffect(() => {
    const fetchToken = async () => {
      try {
        const response = await fetch(`/api/v1/join-exam`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: erpToken, exam_code: examCode })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Failed to join exam");
        setLivekitToken(data.token);
      } catch (err) {
        setError(`Connection blocked: ${err.message}`);
      }
    };
    fetchToken();
  }, [erpToken, examCode]);

  if (error) return <div style={styles.errorScreen}>{error}</div>;
  if (!livekitToken) return <div style={styles.loadingScreen}>Establishing Secure Connection...</div>;

  return (
    <LiveKitRoom
      video={{ deviceId: cameraId }}
      audio={{ deviceId: micId }}
      token={livekitToken}
        serverUrl={`wss://${window.location.host}/livekit-ws`}
      connect={true}
      style={styles.meshBackground}
    >
      <ExamInterface erpToken={erpToken} examCode={examCode} livekitToken={livekitToken} />
    </LiveKitRoom>
  );
}

// Separate component so we can use LiveKit hooks
function ExamInterface({ erpToken, examCode, livekitToken }) {
  // 🔧 UPDATE THIS with your laptop's IPv4 address (find it with: ipconfig)
  const LOCAL_IP = "192.168.0.249"; // Replace with your actual IPv4 address

  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [timeLeft, setTimeLeft] = useState(1800);
  const [isFinished, setIsFinished] = useState(false);
  const videoElementRef = useRef(null);
  const claims = decodeJwtSafe(erpToken);
  const displayUsn = claims.sub || claims.usn || claims.student_id || 'UNKNOWN';

  const room = useRoomContext(); 
  
  const sendAlert = async (eventMsg, severity = 'warning') => {
    if (!room || room.state !== 'connected') return; 
    
    // Notice we removed 'usn'. The teacher will grab the clean ID from LiveKit directly!
    const payload = JSON.stringify({
      event: eventMsg,
      severity: severity,
      time: new Date().toLocaleTimeString([], { hour12: false })
    });
    
    try {
      await room.localParticipant.publishData(new TextEncoder().encode(payload), { reliable: true });
    } catch (e) {}
  };

  // ==========================================
  // 🛡️ DIAGNOSTIC CORE SECURITY & FACE AI 🛡️
  // ==========================================
  useEffect(() => {
    let aiInterval;
    let lastAlertTime = 0;

    const startAI = async () => {
      try {
        console.log("⏳ [AI] Loading Face Models from /models...");
        await faceapi.nets.ssdMobilenetv1.loadFromUri('/models');
        await faceapi.nets.faceLandmark68Net.loadFromUri('/models');
        console.log("✅ [AI] Models Loaded Successfully!");
      } catch (err) {
        console.error("❌ [AI] CRITICAL ERROR: Could not load models. Are they in the public/models folder?", err);
        return;
      }

      console.log("🤖 [AI] Starting Scanner Loop...");

      aiInterval = setInterval(async () => {
        // 1. Find the video element safely
        let video = videoElementRef.current;
        if (!video) {
          video = document.querySelector('video');
          if (video) {
            console.log("🎥 [AI] Found video element on screen!");
            videoElementRef.current = video;
          } else {
            console.log("⚠️ [AI] Waiting for video element to appear...");
            return;
          }
        }

        // 2. Ensure video is actually playing and has dimensions
        // If readyState is not 4, the video is just a blank box. AI cannot read blank boxes.
        if (video.readyState !== 4 || video.videoWidth === 0) {
          console.log("⏳ [AI] Video found, but waiting for it to fully buffer...");
          return;
        }

        try {
          // 3. Run the Detection (0.1 = Maximum Sensitivity)
          const faces = await faceapi.detectAllFaces(
            video,
            new faceapi.SsdMobilenetv1Options({ minConfidence: 0.1 })
          ).withFaceLandmarks();

          // 🔥 THE GOLDEN LOG: This tells us exactly what the AI sees!
          console.log(`👁️ [AI] Scan complete: ${faces.length} faces detected.`);

          const now = Date.now();
          if (now - lastAlertTime < 3000) return; // Anti-spam

          if (faces.length === 0) {
            sendAlert("No face detected on screen", "critical");
            lastAlertTime = now;
            return;
          }

          if (faces.length > 1) {
            sendAlert(`MULTIPLE PEOPLE DETECTED (${faces.length})`, "critical");
            lastAlertTime = now;
            return;
          }

          // EYEBALL / HEAD POSE MATH
          const landmarks = faces[0].landmarks;
          const nose = landmarks.getNose()[3];
          const leftEye = landmarks.getLeftEye()[0];
          const rightEye = landmarks.getRightEye()[3];
          const jawBottom = landmarks.getJawOutline()[8];

          const faceWidth = rightEye.x - leftEye.x;
          const faceHeight = jawBottom.y - leftEye.y;

          const noseXPosition = (nose.x - leftEye.x) / faceWidth;
          if (noseXPosition < 0.15 || noseXPosition > 0.85) {
            sendAlert("Student looking away from screen", "warning");
            lastAlertTime = now;
          }

          const noseYPosition = (nose.y - leftEye.y) / faceHeight;
          if (noseYPosition > 0.75) {
            sendAlert("Student looking down at desk", "warning");
            lastAlertTime = now;
          }

        } catch (e) {
          console.error("❌ [AI] Crash during scan:", e);
        }
      }, 2000); // Scans every 2 seconds
    };

    startAI();

    return () => {
      if (aiInterval) clearInterval(aiInterval);
    };
  }, [room]);

  // Timer
  useEffect(() => {
    if (timeLeft <= 0 || isFinished) return;
    const timerId = setInterval(() => setTimeLeft(prev => prev - 1), 1000);
    return () => clearInterval(timerId);
  }, [timeLeft, isFinished]);

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const currentQ = QUESTIONS[currentQuestionIndex];
  const mobileUrl = LOCAL_IP
    ? `https://${LOCAL_IP}:5173/?mode=mobile&token=${livekitToken}&server=wss://${LOCAL_IP}:5173/livekit-ws`
    : '';

  return (
    <div style={styles.examContainer}>
      <div style={styles.dynamicHeader}>
        <div>
          <h2 style={{ margin: 0, color: '#0f172a', fontSize: '24px' }}>{examCode} Final Examination</h2>
          <p style={{ margin: '5px 0 0 0', color: '#64748b', fontWeight: 'bold' }}>
            USN: <span style={{color: '#3b82f6'}}>{displayUsn}</span> | Telemetry Active 🟢
          </p>
        </div>
        
        {/* 🔥 MOVED PING BUTTON HERE SO IT IS 100% CLICKABLE 🔥 */}
        <button 
          onClick={() => sendAlert("MANUAL PING FROM STUDENT", "info")}
          style={{ padding: '10px 20px', background: '#3b82f6', color: 'white', fontWeight: 'bold', border: 'none', borderRadius: '8px', cursor: 'pointer', zIndex: 9999, pointerEvents: 'auto' }}
        >
          TEST PING
        </button>

        <div style={styles.timerBadge}>
          <span style={{fontSize: '14px', marginRight: '8px', color: '#64748b'}}>TIME</span>
          <span style={{fontSize: '24px', fontWeight: '900', color: '#ef4444'}}>{formatTime(timeLeft)}</span>
        </div>
      </div>

      <div style={{display: 'flex', gap: '20px', flex: 1}}>
        {/* EXAM CONTENT */}
        <div style={styles.glassCardMain}>
          {isFinished ? (
             <h2 style={{color: '#10b981'}}>✅ Exam Submitted.</h2>
          ) : (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <p style={{ ...styles.questionText, marginBottom: 0 }}>Q{currentQuestionIndex + 1}: {currentQ.text}</p>
                {currentQ.type === 'coding' && (
                  <span style={{ background: '#3b82f6', color: 'white', padding: '4px 10px', borderRadius: '20px', fontSize: '12px', fontWeight: 'bold' }}>
                    CODING CHALLENGE
                  </span>
                )}
              </div>

              {currentQ.type === 'mcq' ? (
                <div style={styles.optionsList}>
                  {currentQ.options.map((opt, idx) => (
                    <button
                      key={idx}
                      onClick={() => setAnswers({ ...answers, [currentQuestionIndex]: opt })}
                      style={{ ...styles.optionButton, backgroundColor: answers[currentQuestionIndex] === opt ? '#eff6ff' : 'white', borderColor: answers[currentQuestionIndex] === opt ? '#3b82f6' : '#e2e8f0' }}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              ) : (
                <div style={{ height: '600px', marginBottom: '20px' }}>
                  <CodingTerminal
                    question={currentQ}
                    onPassAll={() => setAnswers({ ...answers, [currentQuestionIndex]: 'ALL_TESTS_PASSED' })}
                  />
                </div>
              )}
              <div style={styles.navigation}>
                <button style={styles.navBtnLight} onClick={() => setCurrentQuestionIndex(p => Math.max(0, p-1))}>Previous</button>
                <button style={styles.navBtnPrimary} onClick={() => currentQuestionIndex === QUESTIONS.length - 1 ? setIsFinished(true) : setCurrentQuestionIndex(p => p+1)}>
                  {currentQuestionIndex === QUESTIONS.length - 1 ? "Submit Exam" : "Next"}
                </button>
              </div>
            </>
          )}
        </div>

        {/* PROCTOR SIDEBAR */}
        <div style={styles.sidebarLight}>
          <div style={styles.glassSidebarCard}>
            <div style={{color: '#ef4444', fontWeight: 'bold', fontSize: '12px', textAlign: 'center', marginBottom: '10px'}}>🔴 AI MONITORING</div>
            <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
              <MyLocalCamera /> 
            </div>
          </div>
          <div style={styles.glassSidebarCard}>
            <h4 style={{margin: '0 0 10px 0', fontSize: '14px'}}>📱 Desk Cam</h4>
            <div style={{ color: '#334155', fontSize: '12px', marginBottom: '10px' }}>
              QR target: {LOCAL_IP}:5173
            </div>
            <div style={{ background: 'white', padding: '10px', borderRadius: '12px', display: 'flex', justifyContent: 'center' }}>
              <QRCode value={mobileUrl || 'https://localhost:5173'} size={120} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function MyLocalCamera() {
  const tracks = useTracks([Track.Source.Camera]);
  if (tracks.length === 0) return <div>Starting...</div>;
  return <VideoTrack trackRef={tracks[0]} style={{ width: '100%', transform: 'scaleX(-1)', display: 'block' }} />;
}

const styles = {
  loadingScreen: { height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc', color: '#334155', fontSize: '20px' },
  errorScreen: { height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#fee2e2', color: '#991b1b', fontSize: '20px' },
  meshBackground: { height: '100vh', display: 'flex', backgroundColor: '#fdfbfb', backgroundImage: `radial-gradient(at 0% 0%, hsla(213, 100%, 93%, 1) 0px, transparent 50%), radial-gradient(at 100% 0%, hsla(259, 100%, 95%, 1) 0px, transparent 50%)`, fontFamily: 'system-ui, sans-serif' },
  examContainer: { flex: 1, padding: '40px', display: 'flex', flexDirection: 'column', gap: '20px', overflowY: 'auto' },
  dynamicHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255, 255, 255, 0.6)', backdropFilter: 'blur(12px)', padding: '20px 30px', borderRadius: '16px', border: '1px solid white' },
  timerBadge: { display: 'flex', alignItems: 'center', background: '#fee2e2', padding: '10px 20px', borderRadius: '12px', border: '1px solid #fecaca' },
  glassCardMain: { flex: 1, background: 'rgba(255, 255, 255, 0.7)', backdropFilter: 'blur(16px)', padding: '40px', borderRadius: '20px', border: '1px solid white' },
  questionText: { fontSize: '22px', fontWeight: '600', color: '#0f172a', marginBottom: '30px' },
  optionsList: { display: 'flex', flexDirection: 'column', gap: '12px' },
  optionButton: { padding: '20px', fontSize: '17px', borderRadius: '12px', cursor: 'pointer', textAlign: 'left', fontWeight: '500', border: '2px solid', color: '#0f172a' },
  navigation: { display: 'flex', justifyContent: 'space-between', marginTop: '40px' },
  navBtnLight: { background: 'white', color: '#475569', padding: '15px 30px', borderRadius: '12px', border: '1px solid #cbd5e1', cursor: 'pointer', fontWeight: 'bold' },
  navBtnPrimary: { background: '#3b82f6', color: 'white', padding: '15px 30px', borderRadius: '12px', border: 'none', cursor: 'pointer', fontWeight: 'bold' },
  sidebarLight: { width: '280px', display: 'flex', flexDirection: 'column', gap: '15px' },
  glassSidebarCard: { background: 'rgba(255, 255, 255, 0.7)', borderRadius: '16px', padding: '20px', border: '1px solid white', boxShadow: '0 4px 15px rgba(0,0,0,0.02)' },
};
