import React, { useState, useEffect } from 'react';
import { LiveKitRoom, useRoomContext } from '@livekit/components-react';
import { RoomEvent } from 'livekit-client';

// Add CSS keyframes for pulse animation
const pulseKeyframes = `
  @keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.5; }
    100% { opacity: 1; }
  }
`;

// Inject the keyframes into the document
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = pulseKeyframes;
  document.head.appendChild(style);
}

export default function ProctorDashboard() {
  const [examCode, setExamCode] = useState('CS101');
  const [proctorToken, setProctorToken] = useState(null);
  const [roomName, setRoomName] = useState('');

  const connectAsProctor = async () => {
    try {
      const normalizedCode = examCode.trim();
      const response = await fetch(`/api/v1/proctor-token/${normalizedCode}`);
      const data = await response.json();
      setProctorToken(data.token);
      setRoomName(data.room_name || normalizedCode);
    } catch (err) {
      alert("Error joining as proctor");
    }
  };

  if (!proctorToken) {
    return (
      <div style={styles.loginContainer}>
        <div style={styles.glassCard}>
          <h2>🛡️ Proctor Admin Terminal</h2>
          <p style={{color: '#64748b'}}>Enter Exam Code to view live telemetry.</p>
          <input style={styles.input} value={examCode} onChange={e => setExamCode(e.target.value)} />
          <button style={styles.button} onClick={connectAsProctor}>Open Live Timeline</button>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.dashboardContainer}>
      <div style={styles.header}>
        <h2 style={{margin: 0, color: '#0f172a'}}>📡 Telemetry Dashboard: {roomName || examCode}</h2>
        <div style={styles.badge}>Live Connection Active</div>
      </div>

      <LiveKitRoom
        token={proctorToken}
          serverUrl={`wss://${window.location.host}/livekit-ws`}
        connect={true}
      >
        <TelemetryTimeline />
      </LiveKitRoom>
    </div>
  );
}


// Subscribes and groups logs by Student ID
function TelemetryTimeline() {
  // We now store an object where keys are Student IDs, and values are arrays of logs
  // Example: { "STU_123": [{event: "Ctrl+C", time: "10:00"}], "STU_999": [...] }
  const [studentLogs, setStudentLogs] = useState({});
  const room = useRoomContext();

  useEffect(() => {
    if (!room) return;

    const handleDataReceived = (payload, participant) => {
      // Grab the CLEAN student ID directly from LiveKit!
      const studentId = participant?.identity || "Unknown Student";
      
      try {
        const data = JSON.parse(new TextDecoder().decode(payload));
        
        if (data && data.event) {
          setStudentLogs(prevLogs => {
            const existingLogs = prevLogs[studentId] || [];
            
            // Add the new log to the top of this specific student's list
            return {
              ...prevLogs,
              [studentId]: [data, ...existingLogs]
            };
          });
        }
      } catch (e) { }
    };

    room.on(RoomEvent.DataReceived, handleDataReceived);
    return () => room.off(RoomEvent.DataReceived, handleDataReceived);
  }, [room]);

  const getSeverityColor = (severity) => {
    switch(severity) {
      case 'critical': return '#fee2e2'; // Light red
      case 'warning': return '#fef3c7';  // Light yellow
      case 'info': return '#eff6ff';     // Light blue
      default: return '#f1f5f9';
    }
  };

  const studentIds = Object.keys(studentLogs);

  return (
    <div style={{ padding: '40px', overflowY: 'auto', height: '100%' }}>
      {studentIds.length === 0 && (
        <div style={{textAlign: 'center', color: '#94a3b8', marginTop: '50px', fontSize: '18px'}}>
          Waiting for student telemetry...
        </div>
      )}

      {/* GRID OF STUDENT CARDS */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '20px' }}>
        
        {studentIds.map(usn => (
          <div key={usn} style={{ background: 'white', borderRadius: '12px', border: '1px solid #cbd5e1', display: 'flex', flexDirection: 'column', height: '400px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
            
            {/* CARD HEADER (USN) */}
            <div style={{ background: '#0f172a', color: 'white', padding: '15px', borderTopLeftRadius: '12px', borderTopRightRadius: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '16px' }}>👤 {usn}</h3>
              <div style={{ width: '10px', height: '10px', background: '#10b981', borderRadius: '50%', animation: 'pulse 1.5s infinite' }}></div>
            </div>

            {/* CARD TIMELINE (SCROLLABLE) */}
            <div style={{ padding: '15px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {studentLogs[usn].map((log, index) => (
                <div key={index} style={{ background: getSeverityColor(log.severity), padding: '12px', borderRadius: '8px', borderLeft: `4px solid ${log.severity === 'critical' ? '#ef4444' : log.severity === 'warning' ? '#f59e0b' : '#3b82f6'}` }}>
                  <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>{log.time}</div>
                  <div style={{ fontSize: '14px', color: '#0f172a', fontWeight: '500' }}>{log.event}</div>
                </div>
              ))}
            </div>

          </div>
        ))}

      </div>
    </div>
  );
}

const styles = {
  loginContainer: { height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#fdfbfb', fontFamily: 'system-ui, sans-serif' },
  glassCard: { background: 'white', padding: '40px', borderRadius: '16px', display: 'flex', flexDirection: 'column', gap: '15px', border: '1px solid #e2e8f0', boxShadow: '0 10px 30px rgba(0,0,0,0.05)' },
  input: { padding: '15px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '16px' },
  button: { background: '#3b82f6', color: 'white', padding: '15px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontWeight: 'bold' },
  dashboardContainer: { height: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#fdfbfb', backgroundImage: 'radial-gradient(at 0% 0%, hsla(213, 100%, 93%, 1) 0px, transparent 50%)', fontFamily: 'system-ui, sans-serif' },
  header: { padding: '20px 40px', backgroundColor: 'rgba(255, 255, 255, 0.8)', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  badge: { backgroundColor: '#10b981', color: 'white', padding: '6px 15px', borderRadius: '20px', fontSize: '13px', fontWeight: 'bold', textTransform: 'uppercase' },
  timelineWrapper: { flex: 1, padding: '40px', overflowY: 'auto', display: 'flex', justifyContent: 'center' },
  logList: { width: '100%', maxWidth: '900px', display: 'flex', flexDirection: 'column', gap: '15px' },
  logItem: { padding: '20px', borderRadius: '12px', display: 'grid', gridTemplateColumns: '100px 150px 1fr', alignItems: 'center', boxShadow: '0 2px 5px rgba(0,0,0,0.02)' },
  logTime: { color: '#64748b', fontSize: '14px', fontWeight: 'bold' },
  logUsn: { color: '#0f172a', fontSize: '15px', fontWeight: 'bold' }
};
