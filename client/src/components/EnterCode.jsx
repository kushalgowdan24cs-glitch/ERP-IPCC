import React, { useState } from 'react';

export default function EnterCode({ onSubmit, connected, backendUrl }) {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (code.trim().length >= 4) {
      setLoading(true);
      onSubmit(code.trim().toUpperCase());
    }
  };

  return (
    <div className="card">
      <h1>🛡️ ProctorShield</h1>
      <h2>Secure Examination System</h2>

      <form onSubmit={handleSubmit}>
        <div className="input-group">
          <label>Enter Session Code</label>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABC123"
            maxLength={8}
            autoFocus
            disabled={loading}
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={code.trim().length < 4 || loading}
        >
          {loading ? '⏳ Connecting...' : '🚀 Start Exam'}
        </button>
      </form>

      <p style={{
        textAlign: 'center',
        marginTop: '1.5rem',
        fontSize: '0.8rem',
        color: 'var(--text-secondary)',
      }}>
        Your session will be monitored via webcam and microphone.
        <br />Please ensure you are in a well-lit, quiet environment.
      </p>
    </div>
  );
}