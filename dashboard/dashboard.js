document.addEventListener("DOMContentLoaded", () => {
    const studentGrid = document.getElementById('student-grid');
    const alertFeed = document.getElementById('alert-feed');
    const statusText = document.getElementById('connection-status');

    // In-memory state of active students
    const activeStudents = new Map();

    // ─── WEBSOCKET CONNECTION ───
    const ws = new WebSocket('ws://localhost:8000/api/v1/admin/ws');

    ws.onopen = () => {
        statusText.textContent = "Online & Secure";
        statusText.style.color = "#10b981";
    };

    ws.onclose = () => {
        statusText.textContent = "Disconnected - Retrying...";
        statusText.style.color = "#ef4444";
        // In production, implement a reconnection backoff loop here
    };

    ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        handleAlert(payload);
    };

    // ─── LOGIC ENGINE ───
    function handleAlert(data) {
        // data format: { student_id, exam_code, type, event, details, risk_level (optional) }
        
        // 1. Update or Create Student Card
        if (!activeStudents.has(data.student_id)) {
            createStudentCard(data.student_id);
        }
        updateStudentCard(data.student_id, data);

        // 2. Add to Alert Sidebar
        createSidebarAlert(data);
    }

    function createStudentCard(studentId) {
        const card = document.createElement('div');
        card.className = 'student-card';
        card.id = `card-${studentId}`;
        card.innerHTML = `
            <h3>${studentId}</h3>
            <div class="status">Status: <span>Monitoring</span></div>
            <div class="latest-event" style="margin-top: 0.5rem; font-size: 0.85rem; font-weight: bold;"></div>
        `;
        studentGrid.appendChild(card);
        activeStudents.set(studentId, { riskLevel: 'GREEN' });
    }

    function updateStudentCard(studentId, data) {
        const card = document.getElementById(`card-${studentId}`);
        if (!card) return;

        // Elevate risk UI if it's a critical violation
        if (data.risk_level === 'RED' || data.type === 'OS_TAMPERING' || data.event === 'UNAUTHORIZED_DEVICE_PHONE') {
            card.className = 'student-card red';
            card.querySelector('.status span').textContent = 'CRITICAL VIOLATION';
            card.querySelector('.status span').style.color = '#ef4444';
        } else if (card.className !== 'student-card red') {
            card.className = 'student-card yellow';
            card.querySelector('.status span').textContent = 'SUSPICIOUS';
            card.querySelector('.status span').style.color = '#f59e0b';
        }

        card.querySelector('.latest-event').textContent = `Latest: ${data.event.replace(/_/g, ' ')}`;
    }

    function createSidebarAlert(data) {
        // Remove the "Waiting for anomalies" placeholder
        if (alertFeed.children.length === 1 && alertFeed.children[0].tagName === 'P') {
            alertFeed.innerHTML = '';
        }

        const isCritical = data.risk_level === 'RED' || data.type === 'OS_TAMPERING';
        
        const alertEl = document.createElement('div');
        alertEl.className = `alert-item ${isCritical ? 'CRITICAL' : 'WARNING'}`;
        
        const timeStr = new Date().toLocaleTimeString();
        
        alertEl.innerHTML = `
            <div class="alert-time">${timeStr} | ${data.student_id}</div>
            <strong style="color: ${isCritical ? '#ef4444' : '#f59e0b'}">${data.event.replace(/_/g, ' ')}</strong>
            <div style="font-size: 0.85rem; margin-top: 0.5rem;">${data.details || 'Anomaly detected in feed.'}</div>
        `;

        // Prepend to top of list
        alertFeed.insertBefore(alertEl, alertFeed.firstChild);

        // Keep UI clean, remove alerts older than 50
        if (alertFeed.children.length > 50) {
            alertFeed.removeChild(alertFeed.lastChild);
        }
    }
});