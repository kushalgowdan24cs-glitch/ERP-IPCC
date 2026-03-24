import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';

// ─── ENTERPRISE MOUNTING POINT ───
// No routers. No landing pages. No choices.
// The moment the student opens the app, it locks them into App.jsx
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);