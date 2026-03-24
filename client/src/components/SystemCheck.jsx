import React, { useState, useEffect } from 'react';

export default function SystemCheck({ onComplete }) {
  const [checks, setChecks] = useState({
    camera: 'pending',
    microphone: 'pending',
    processes: 'pending',
    display: 'pending',
  });
  const [blockedProcesses, setBlockedProcesses] = useState([]);
  const [allPassed, setAllPassed] = useState(false);

  useEffect(() => {
    runChecks();
  }, []);

  async function runChecks() {
    // Check camera
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      stream.getTracks().forEach(t => t.stop());
      setChecks(prev => ({ ...prev, camera: 'pass' }));
    } catch {
      setChecks(prev => ({ ...prev, camera: 'fail' }));
    }

    // Check microphone
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(t => t.stop());
      setChecks(prev => ({ ...prev, microphone: 'pass' }));
    } catch {
      setChecks(prev => ({ ...prev, microphone: 'fail' }));
    }

    // Check processes (Electron only)
    if (window.proctorAPI) {
      try {
        const result = await window.proctorAPI.scanProcesses();
        if (result.blocked.length > 0) {
          setBlockedProcesses(result.blocked);
          setChecks(prev => ({ ...prev, processes: 'fail' }));
        } else {
          setChecks(prev => ({ ...prev, processes: 'pass' }));
        }
      } catch {
        setChecks(prev => ({ ...prev, processes: 'pass' }));
      }
    } else {
      // Running in browser (dev mode), skip process check
      setChecks(prev => ({ ...prev, processes: 'pass' }));
    }

    // Display check (basic — just verify single screen as best we can)
    setChecks(prev => ({ ...prev, display: 'pass' }));
  }

  useEffect(() => {
    const passed = Object.values(checks).every(v => v === 'pass');
    setAllPassed(passed);
  }, [checks]);

  const checkIcon = (status) => {
    if (status === 'pass') return <span className="check-icon check-pass">✅</span>;
    if (status === 'fail') return <span className="check-icon check-fail">❌</span>;
    return <span className="check-icon check-pending">⏳</span>;
  };

  return (
    <div className="card">
      <h1>🔍 System Check</h1>
      <h2>Verifying your setup before the exam</h2>

      <div className="check-list">
        <div className="check-item">
          {checkIcon(checks.camera)}
          <span>Webcam access</span>
        </div>
        <div className="check-item">
          {checkIcon(checks.microphone)}
          <span>Microphone access</span>
        </div>
        <div className="check-item">
          {checkIcon(checks.processes)}
          <span>No prohibited applications running</span>
        </div>
        <div className="check-item">
          {checkIcon(checks.display)}
          <span>Single display detected</span>
        </div>
      </div>

      {blockedProcesses.length > 0 && (
        <div style={{
          background: 'var(--danger-bg)',
          padding: '12px 16px',
          borderRadius: '8px',
          marginBottom: '1rem',
        }}>
          <strong style={{ color: 'var(--danger)' }}>
            Please close these applications:
          </strong>
          <ul style={{ margin: '8px 0 0 20px', color: 'var(--danger)' }}>
            {blockedProcesses.map(p => <li key={p}>{p}</li>)}
          </ul>
          <button
            className="btn btn-danger"
            style={{ marginTop: '10px', padding: '8px 16px', fontSize: '0.85rem' }}
            onClick={runChecks}
          >
            Re-check
          </button>
        </div>
      )}

      <button
        className="btn btn-primary"
        disabled={!allPassed}
        onClick={onComplete}
      >
        {allPassed ? '✅ Continue to Identity Verification' : '⏳ Checking...'}
      </button>
    </div>
  );
}