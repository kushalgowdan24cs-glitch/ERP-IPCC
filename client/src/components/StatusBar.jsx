import React, { useState, useEffect } from 'react';

export default function StatusBar({
  studentName, examTitle, riskScore, riskLevel, connected, duration
}) {
  return (
    <div className="status-bar">
      <div className="left">
        <span>🛡️ <strong>ProctorShield</strong></span>
        <span style={{ color: 'var(--text-secondary)' }}>|</span>
        <span>{examTitle}</span>
        <span style={{ color: 'var(--text-secondary)' }}>|</span>
        <span>{studentName}</span>
      </div>
      <div className="right">
        <span className={`risk-badge risk-${riskLevel}`}>
          Risk: {Math.round(riskScore)} ({riskLevel})
        </span>
        <span style={{
          width: 10, height: 10, borderRadius: '50%',
          background: connected ? 'var(--success)' : 'var(--danger)',
          display: 'inline-block',
        }} />
      </div>
    </div>
  );
}