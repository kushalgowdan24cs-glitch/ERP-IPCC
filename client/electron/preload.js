const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('proctorAPI', {
  // Process scanning
  scanProcesses: () => ipcRenderer.invoke('scan-processes'),

  // Listen for lockdown events from main process
  onLockdownEvent: (callback) => {
    ipcRenderer.on('lockdown-event', (event, data) => callback(data));
  },

  // Signal exam completion
  examFinished: () => ipcRenderer.send('exam-finished'),

  // Platform info
  platform: process.platform,
});