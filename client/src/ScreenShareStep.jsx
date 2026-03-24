import React, { useEffect, useRef, useState } from 'react';
import QRCode from 'react-qr-code';

export default function ScreenShareStep({ studentData, onNext }) {
  // 🔧 UPDATE THIS with your laptop's IPv4 address (find it with: ipconfig)
  const LOCAL_IP = "192.168.0.249"; // Replace with your actual IPv4 address

  const [isSharing, setIsSharing] = useState(false);
  const [error, setError] = useState('');
  const [screenStream, setScreenStream] = useState(null);
  const [mobileUrl, setMobileUrl] = useState('');
  const [mobileStatus, setMobileStatus] = useState('Preparing mobile security link...');
  const videoRef = useRef(null);

  useEffect(() => {
    const fetchMobileToken = async () => {
      if (!studentData?.erpToken || !studentData?.examCode) {
        setMobileStatus('Waiting for student context...');
        return;
      }

      if (!LOCAL_IP) {
        setMobileStatus('Update LOCAL_IP in ScreenShareStep.jsx with your laptop IP address.');
        return;
      }

      try {
        setMobileStatus('Requesting desk-cam token...');
        const response = await fetch('/api/v1/join-exam', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: studentData.erpToken,
            exam_code: studentData.examCode,
            client_type: 'mobile',
          }),
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.token) {
          throw new Error(data.detail || 'Could not issue mobile desk-cam token.');
        }

        const serverUrl = `wss://${LOCAL_IP}:5173/livekit-ws`;
        const qrUrl = `https://${LOCAL_IP}:5173/?mode=mobile&token=${encodeURIComponent(data.token)}&server=${encodeURIComponent(serverUrl)}`;
        setMobileUrl(qrUrl);
        setMobileStatus('Phone link ready. Scan QR with phone camera.');
      } catch (err) {
        setMobileStatus(`Phone link failed: ${err.message}`);
      }
    };

    fetchMobileToken();
  }, [studentData]);

  useEffect(() => {
    return () => {
      if (screenStream) {
        screenStream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [screenStream]);

  const startScreenShare = async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { displaySurface: 'monitor' },
        audio: false,
      });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      setScreenStream(stream);
      setIsSharing(true);
      setError('');

      const videoTrack = stream.getVideoTracks()[0];
      if (videoTrack) {
        videoTrack.onended = () => {
          setIsSharing(false);
          setScreenStream(null);
        };
      }
    } catch (err) {
      setError('You must share your entire screen to continue.');
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.glassCard}>
        <h2 style={styles.title}>Security Setup</h2>

        {error && <div style={styles.errorBanner}>{error}</div>}

        <div style={styles.grid}>
          <div style={styles.box}>
            <h3 style={styles.boxTitle}>1. Screen Capture</h3>
            <p style={styles.boxText}>
              Share your <b>entire screen</b> so the proctoring engine can monitor unauthorized
              windows and tab switching.
            </p>

            <div style={styles.videoPlaceholder}>
              <video
                ref={videoRef}
                autoPlay
                muted
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  display: isSharing ? 'block' : 'none',
                }}
              />
              {!isSharing && <p style={styles.placeholderText}>No screen detected</p>}
            </div>

            {!isSharing ? (
              <button style={styles.buttonBlue} onClick={startScreenShare}>
                Share Screen
              </button>
            ) : (
              <div style={styles.successBadge}>Screen secured</div>
            )}
          </div>

          <div style={styles.box}>
            <h3 style={styles.boxTitle}>2. Desk Camera</h3>
            <p style={styles.boxText}>
              Scan this QR on your phone to activate a secondary keyboard view in the same
              proctoring room.
            </p>

            <div style={styles.qrContainer}>
              {mobileUrl ? (
                <QRCode value={mobileUrl} size={160} />
              ) : (
                <div className="desk-spinner" style={styles.spinner} />
              )}
            </div>

            <p style={styles.mobileStatus}>{mobileStatus}</p>
          </div>
        </div>

        <button
          style={isSharing ? styles.buttonGreen : styles.buttonDisabled}
          onClick={() => onNext(screenStream)}
          disabled={!isSharing}
        >
          {isSharing ? 'Continue to Face Verification' : 'Complete Step 1 to Continue'}
        </button>
      </div>

      <style>
        {` .desk-spinner { border: 4px solid #e2e8f0; border-top: 4px solid #3b82f6; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; }
           @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}
      </style>
    </div>
  );
}

const styles = {
  container: {
    height: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '24px',
    backgroundColor: '#fdfbfb',
    backgroundImage:
      'radial-gradient(at 0% 0%, hsla(213, 100%, 93%, 1) 0px, transparent 50%), radial-gradient(at 100% 0%, hsla(259, 100%, 95%, 1) 0px, transparent 50%), radial-gradient(at 100% 100%, hsla(339, 100%, 96%, 1) 0px, transparent 50%), radial-gradient(at 0% 100%, hsla(196, 100%, 92%, 1) 0px, transparent 50%)',
    fontFamily: 'Avenir Next, Segoe UI, system-ui, sans-serif',
  },
  glassCard: {
    background: 'rgba(255, 255, 255, 0.66)',
    backdropFilter: 'blur(20px)',
    padding: '32px',
    borderRadius: '24px',
    width: 'min(980px, 100%)',
    border: '1px solid rgba(255, 255, 255, 0.85)',
    display: 'flex',
    flexDirection: 'column',
    gap: '18px',
    boxShadow: '0 10px 40px rgba(0,0,0,0.05)',
  },
  title: {
    textAlign: 'center',
    color: '#0f172a',
    margin: '0 0 8px 0',
    fontSize: '28px',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
    gap: '24px',
  },
  box: {
    background: 'rgba(255, 255, 255, 0.5)',
    padding: '22px',
    borderRadius: '16px',
    border: '1px solid #ffffff',
    display: 'flex',
    flexDirection: 'column',
  },
  boxTitle: {
    margin: '0 0 8px 0',
    color: '#1e293b',
    fontSize: '20px',
  },
  boxText: {
    color: '#475569',
    fontSize: '14px',
    lineHeight: 1.5,
    margin: '0 0 16px 0',
  },
  videoPlaceholder: {
    width: '100%',
    height: '200px',
    backgroundColor: '#f1f5f9',
    borderRadius: '12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '16px',
    overflow: 'hidden',
    border: '2px dashed #cbd5e1',
  },
  placeholderText: {
    color: '#94a3b8',
    margin: 0,
  },
  qrContainer: {
    width: '100%',
    height: '200px',
    backgroundColor: '#ffffff',
    borderRadius: '12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '1px solid #e2e8f0',
    padding: '10px',
  },
  spinner: {
    margin: 'auto',
  },
  mobileStatus: {
    color: '#ef4444',
    fontSize: '12px',
    fontWeight: 700,
    margin: '12px 0 0 0',
    textAlign: 'center',
    minHeight: '18px',
  },
  buttonBlue: {
    background: '#3b82f6',
    color: 'white',
    padding: '14px',
    borderRadius: '10px',
    border: 'none',
    cursor: 'pointer',
    fontWeight: 'bold',
    width: '100%',
    fontSize: '16px',
    boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
  },
  successBadge: {
    background: '#d1fae5',
    color: '#065f46',
    padding: '14px',
    borderRadius: '10px',
    border: '1px solid #10b981',
    textAlign: 'center',
    fontWeight: 'bold',
    width: '100%',
    fontSize: '16px',
  },
  buttonGreen: {
    background: '#10b981',
    color: 'white',
    padding: '16px',
    borderRadius: '12px',
    border: 'none',
    cursor: 'pointer',
    fontWeight: 'bold',
    width: '100%',
    fontSize: '18px',
    marginTop: '4px',
    boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
  },
  buttonDisabled: {
    background: '#cbd5e1',
    color: '#64748b',
    padding: '16px',
    borderRadius: '12px',
    border: 'none',
    width: '100%',
    fontSize: '18px',
    marginTop: '4px',
  },
  errorBanner: {
    background: '#fee2e2',
    color: '#991b1b',
    padding: '12px',
    borderRadius: '8px',
    textAlign: 'center',
    border: '1px solid #fca5a5',
  },
};
