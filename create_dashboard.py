import os

os.makedirs('dashboard', exist_ok=True)

# index.html
html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ProctorShield Dashboard</title>
  <link rel="stylesheet" href="dashboard.css" />
</head>
<body>
  <header>
    <h1>🛡️ ProctorShield Dashboard</h1>
    <div id="connection-status">⏳ Connecting...</div>
  </header>

  <main>
    <section id="stats-bar">
      <div class="stat-card">
        <div class="stat-value" id="total-sessions">0</div>
        <div class="stat-label">Active Sessions</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" id="flagged-count">0</div>
        <div class="stat-label">Flagged</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" id="clean-count">0</div>
        <div class="stat-label">Clean</div>
      </div>
    </section>

    <section id="sessions-grid"></section>

    <section id="event-log">
      <h2>📋 Live Event Log</h2>
      <div id="log-entries"></div>
    </section>
  </main>

  <script src="dashboard.js"></script>
</body>
</html>"""

# dashboard.css
css = """* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0f172a;
  color: #f1f5f9;
  min-height: 100vh;
}

header {
  background: #1e293b;
  padding: 16px 30px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #334155;
}

header h1 { font-size: 1.3rem; }

#connection-status {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}

.connected { background: rgba(34,197,94,0.2); color: #22c55e; }
.disconnected { background: rgba(239,68,68,0.2); color: #ef4444; }

main { padding: 20px 30px; }

#stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: #1e293b;
  border-radius: 12px;
  padding: 20px 30px;
  flex: 1;
  text-align: center;
}

.stat-value { font-size: 2rem; font-weight: 700; }
.stat-label { font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }

#sessions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
  min-height: 100px;
  color: #94a3b8;
}

.session-card {
  background: #1e293b;
  border-radius: 12px;
  padding: 20px;
  border-left: 4px solid #22c55e;
}

.session-card.risk-YELLOW { border-left-color: #f59e0b; }
.session-card.risk-ORANGE { border-left-color: #f97316; }
.session-card.risk-RED { border-left-color: #ef4444; }

.session-card .header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.session-card .student-name { font-weight: 700; font-size: 1.1rem; }

.risk-badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 700;
}

.risk-badge.GREEN { background: rgba(34,197,94,0.2); color: #22c55e; }
.risk-badge.YELLOW { background: rgba(245,158,11,0.2); color: #f59e0b; }
.risk-badge.ORANGE { background: rgba(249,115,22,0.2); color: #f97316; }
.risk-badge.RED { background: rgba(239,68,68,0.2); color: #ef4444; }

.session-card .info {
  font-size: 0.85rem;
  color: #94a3b8;
  margin-bottom: 8px;
}

#event-log {
  background: #1e293b;
  border-radius: 12px;
  padding: 20px;
}

#event-log h2 { font-size: 1.1rem; margin-bottom: 12px; }

#log-entries {
  max-height: 300px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 0.8rem;
}

.log-entry {
  padding: 6px 0;
  border-bottom: 1px solid #334155;
}"""

# dashboard.js
js = """const BACKEND_WS = 'ws://localhost:8000/ws/dashboard';
const BACKEND_HTTP = 'http://localhost:8000';

let ws;
let sessions = {};

function connect() {
  ws = new WebSocket(BACKEND_WS);

  ws.onopen = () => {
    document.getElementById('connection-status').textContent = '🟢 Connected';
    document.getElementById('connection-status').className = 'connected';
    console.log('[Dashboard] Connected');
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleMessage(data);
  };

  ws.onclose = () => {
    document.getElementById('connection-status').textContent = '🔴 Disconnected';
    document.getElementById('connection-status').className = 'disconnected';
    setTimeout(connect, 3000);
  };
}

function handleMessage(data) {
  if (data.type === 'initial_state') {
    data.sessions.forEach(s => { sessions[s.session_id] = s; });
    renderSessions();
  } else if (data.type === 'session_update') {
    const session = sessions[data.session_id] || {};
    session.session_id = data.session_id;
    session.student_name = data.student_name;
    session.risk_score = data.risk_score;
    session.risk_level = data.risk_level;
    session.total_flags = data.total_flags;
    sessions[data.session_id] = session;
    renderSessions();
  }
}

function renderSessions() {
  const grid = document.getElementById('sessions-grid');
  const list = Object.values(sessions);

  document.getElementById('total-sessions').textContent = list.length;
  document.getElementById('flagged-count').textContent = list.filter(s => s.risk_level === 'RED' || s.risk_level === 'ORANGE').length;
  document.getElementById('clean-count').textContent = list.filter(s => s.risk_level === 'GREEN').length;

  if (list.length === 0) {
    grid.innerHTML = '<p>No active sessions. Waiting for students...</p>';
    return;
  }

  grid.innerHTML = list.map(s => `
    <div class="session-card risk-${s.risk_level}">
      <div class="header">
        <span class="student-name">${s.student_name || 'Unknown'}</span>
        <span class="risk-badge ${s.risk_level}">
          ${Math.round(s.risk_score)} — ${s.risk_level}
        </span>
      </div>
      <div class="info">
        ${s.exam_title || 'Exam'} • ${s.total_flags || 0} flags
      </div>
    </div>
  `).join('');
}

async function fetchActive() {
  try {
    const res = await fetch(BACKEND_HTTP + '/api/v1/sessions/active/all');
    const data = await res.json();
    data.forEach(s => { sessions[s.session_id] = s; });
    renderSessions();
  } catch (e) {
    console.log('Fetch error:', e);
  }
}

fetchActive();
connect();
setInterval(fetchActive, 30000);"""

with open('dashboard/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('✓ index.html created')

with open('dashboard/dashboard.css', 'w', encoding='utf-8') as f:
    f.write(css)
print('✓ dashboard.css created')

with open('dashboard/dashboard.js', 'w', encoding='utf-8') as f:
    f.write(js)
print('✓ dashboard.js created')

print('\nDashboard files created successfully!')
print('Refresh http://localhost:8000/dashboard/ in your browser')