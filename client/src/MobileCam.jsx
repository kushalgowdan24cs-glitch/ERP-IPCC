import React, { useState } from 'react';
import { LiveKitRoom, VideoTrack, useTracks } from '@livekit/components-react';
import { Track } from 'livekit-client';

export default function MobileCam() {
  const [hasStarted, setHasStarted] = useState(false);
  const [livekitError, setLivekitError] = useState('');

  const queryParams = new URLSearchParams(window.location.search);
  const token = queryParams.get('token');
  const serverUrl = queryParams.get('server');

  if (!token || !serverUrl) {
    return (
      <div style={styles.error}>
        <div style={styles.errorCard}>Invalid security link. Scan the QR code again.</div>
      </div>
    );
  }

  if (!hasStarted) {
    return (
      <div style={styles.startScreen}>
        <div style={styles.startCard}>
          <h2 style={styles.startTitle}>Desk Camera Setup</h2>
          <p style={styles.startText}>
            Mobile browsers require a tap before camera permission can be granted.
          </p>
          <button style={styles.startBtn} onClick={() => setHasStarted(true)}>
            Tap to Start Camera
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <style>
        {`@keyframes pulsePhoneDot {
          0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6); }
          70% { box-shadow: 0 0 0 12px rgba(239, 68, 68, 0); }
          100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }`}
      </style>

      <div style={styles.header}>
        <div style={styles.pulsingDot} />
        <h3 style={styles.headerTitle}>Desk Camera Active</h3>
      </div>

      <p style={styles.instructions}>
        Position the phone so keyboard and hands stay visible. Keep this screen open during the
        entire exam.
      </p>

      <LiveKitRoom
        video={true}
        audio={false}
        token={token}
        serverUrl={serverUrl}
        connect
        onError={(err) => {
          const message = err?.message || 'Unknown LiveKit error.';
          setLivekitError(message);
          alert(`LiveKit Error: ${message}`);
        }}
        style={styles.room}
      >
        <PhoneCameraPreview />
      </LiveKitRoom>

      {livekitError && <div style={styles.errorInline}>LiveKit connection issue: {livekitError}</div>}
    </div>
  );
}

function PhoneCameraPreview() {
  const tracks = useTracks([Track.Source.Camera]);
  if (tracks.length === 0) return <div style={styles.connecting}>Requesting camera permissions...</div>;

  return <VideoTrack trackRef={tracks[0]} style={styles.videoPreview} />;
}

const styles = {
  startScreen: {
    height: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '20px',
    backgroundColor: '#fdfbfb',
    backgroundImage:
      'radial-gradient(at 0% 0%, hsla(213, 100%, 93%, 1) 0px, transparent 50%), radial-gradient(at 100% 0%, hsla(259, 100%, 95%, 1) 0px, transparent 50%), radial-gradient(at 100% 100%, hsla(339, 100%, 96%, 1) 0px, transparent 50%), radial-gradient(at 0% 100%, hsla(196, 100%, 92%, 1) 0px, transparent 50%)',
    fontFamily: 'Avenir Next, Segoe UI, system-ui, sans-serif',
  },
  startCard: {
    background: 'rgba(255, 255, 255, 0.78)',
    backdropFilter: 'blur(18px)',
    border: '1px solid rgba(255, 255, 255, 0.95)',
    borderRadius: '20px',
    padding: '28px',
    maxWidth: '380px',
    width: '100%',
    textAlign: 'center',
    boxShadow: '0 10px 30px rgba(15, 23, 42, 0.08)',
  },
  startTitle: {
    margin: '0 0 10px 0',
    color: '#0f172a',
    fontSize: '1.4rem',
  },
  startText: {
    margin: '0 0 18px 0',
    color: '#475569',
    lineHeight: 1.45,
  },
  startBtn: {
    width: '100%',
    border: 'none',
    borderRadius: '12px',
    padding: '14px 16px',
    cursor: 'pointer',
    backgroundColor: '#2563eb',
    color: '#ffffff',
    fontWeight: 700,
    fontSize: '1rem',
    boxShadow: '0 8px 20px rgba(37, 99, 235, 0.32)',
  },
  container: {
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    padding: '20px',
    fontFamily: 'Avenir Next, Segoe UI, system-ui, sans-serif',
    backgroundColor: '#0b1220',
    color: '#e2e8f0',
    gap: '14px',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '10px',
    backgroundColor: '#162236',
    padding: '14px',
    borderRadius: '12px',
  },
  headerTitle: {
    margin: 0,
    color: '#ffffff',
  },
  pulsingDot: {
    width: '12px',
    height: '12px',
    backgroundColor: '#ef4444',
    borderRadius: '50%',
    animation: 'pulsePhoneDot 1.5s infinite',
  },
  instructions: {
    color: '#cbd5e1',
    textAlign: 'center',
    fontSize: '15px',
    lineHeight: 1.5,
    margin: 0,
  },
  room: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '16px',
    overflow: 'hidden',
    backgroundColor: '#060b16',
    border: '1px solid #334155',
  },
  connecting: {
    color: '#94a3b8',
    fontSize: '15px',
  },
  videoPreview: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },
  error: {
    height: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1f2937',
    padding: '18px',
  },
  errorCard: {
    color: '#ffffff',
    backgroundColor: '#7f1d1d',
    border: '1px solid #b91c1c',
    borderRadius: '12px',
    padding: '18px',
    textAlign: 'center',
    maxWidth: '440px',
  },
  errorInline: {
    backgroundColor: '#7f1d1d',
    border: '1px solid #ef4444',
    color: '#fecaca',
    borderRadius: '10px',
    padding: '10px 12px',
    fontSize: '12px',
  },
};
