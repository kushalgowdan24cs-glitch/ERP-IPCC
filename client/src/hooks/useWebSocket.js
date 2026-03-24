import { useState, useEffect, useRef, useCallback } from 'react';

export function useWebSocket(baseUrl, onMessage, stage) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const codeRef = useRef(null);

  const connect = useCallback((code) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    // Force port 8000 regardless of what baseUrl says
    const forcedBaseUrl = baseUrl.replace('8081', '8000');
    const wsUrl = `${forcedBaseUrl}/ws/proctor/${code}`;
    console.log(`[WS] Connecting to ${wsUrl}`);

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[WS] Connected');
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[WS] Received:', data.type);
        onMessage(data);
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    ws.onclose = (event) => {
      console.log(`[WS] Disconnected (code: ${event.code})`);
      setConnected(false);

      // Auto-reconnect if exam is in progress
      if (stage === 'EXAM' && codeRef.current) {
        console.log('[WS] Reconnecting in 3 seconds...');
        setTimeout(() => connect(codeRef.current), 3000);
      }
    };

    ws.onerror = (error) => {
      console.error('[WS] Error:', error);
    };

    wsRef.current = ws;
    codeRef.current = code;
  }, [baseUrl, onMessage, stage]);

  const send = useCallback((data) => {
    if (data.type === 'connect') {
      connect(data.code);
      return;
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, [connect]);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return { send, connected };
}