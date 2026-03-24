const { app, BrowserWindow, globalShortcut, ipcMain } = require('electron');
const path = require('path');
const { exec } = require('child_process');

let mainWindow;

// ── Blocked keyboard shortcuts ──
const BLOCKED_SHORTCUTS = [
  'CommandOrControl+C', 'CommandOrControl+V', 'CommandOrControl+X',
  'CommandOrControl+A', 'CommandOrControl+Z',
  'CommandOrControl+Tab', 'Alt+Tab', 'Alt+F4',
  'CommandOrControl+Shift+I',  // DevTools
  'CommandOrControl+R',        // Reload
  'F5', 'F11', 'F12',
  'PrintScreen',
  'CommandOrControl+P',        // Print
  'CommandOrControl+S',        // Save
];

// ── Blacklisted processes ──
const BLACKLISTED_PROCESSES = [
  'obs', 'obs64', 'obs-studio', 'streamlabs',
  'anydesk', 'teamviewer', 'rustdesk',
  'discord', 'zoom', 'skype', 'teams',
  'bandicam', 'camtasia', 'screenrec',
  'manycam', 'snap camera', 'xsplit',
  'vnc', 'tightvnc', 'ultravnc',
  'autohotkey', 'autoit',
  'sharex', 'greenshot', 'lightshot',
];

function createWindow() {
  mainWindow = new BrowserWindow({
    fullscreen: true,
    frame: false,               // No title bar
    resizable: false,
    closable: false,            // Prevent closing
    minimizable: false,
    maximizable: false,
    alwaysOnTop: true,          // Stay on top
    kiosk: true,                // Kiosk mode
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      devTools: false,          // Disable DevTools in production
    },
  });

  // Load React dev server or built files
  const isDev = process.argv.includes('--dev') || !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    // Enable DevTools only in dev
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  // Prevent window close during exam
  mainWindow.on('close', (e) => {
    e.preventDefault();
  });

  // Detect focus loss
  mainWindow.on('blur', () => {
    mainWindow.webContents.send('lockdown-event', {
      event: 'app_lost_focus',
      timestamp: Date.now(),
    });
    // Force focus back
    setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.focus();
        mainWindow.moveTop();
      }
    }, 100);
  });
}

app.whenReady().then(() => {
  createWindow();

  // Block keyboard shortcuts
  BLOCKED_SHORTCUTS.forEach(shortcut => {
    try {
      globalShortcut.register(shortcut, () => {
        mainWindow.webContents.send('lockdown-event', {
          event: shortcut.includes('C') || shortcut.includes('V')
            ? 'copy_paste_attempt'
            : 'tab_switch',
          shortcut: shortcut,
          timestamp: Date.now(),
        });
      });
    } catch (e) {
      // Some shortcuts may fail to register on certain OS
    }
  });
});

// ── IPC: Process scanning ──
ipcMain.handle('scan-processes', async () => {
  return new Promise((resolve) => {
    const platform = process.platform;
    let command;

    if (platform === 'win32') {
      command = 'tasklist /FO CSV /NH';
    } else if (platform === 'darwin') {
      command = 'ps -eo comm';
    } else {
      command = 'ps -eo comm --no-headers';
    }

    exec(command, (error, stdout) => {
      if (error) {
        resolve({ processes: [], blocked: [] });
        return;
      }

      const lines = stdout.toLowerCase().split('\n');
      const blocked = [];

      for (const line of lines) {
        for (const banned of BLACKLISTED_PROCESSES) {
          if (line.includes(banned)) {
            blocked.push(banned);
          }
        }
      }

      resolve({
        processes: lines.length,
        blocked: [...new Set(blocked)],
      });
    });
  });
});

// ── IPC: Allow exam completion (unlocks the window) ──
ipcMain.on('exam-finished', () => {
  globalShortcut.unregisterAll();
  if (mainWindow) {
    mainWindow.closable = true;
    mainWindow.setKiosk(false);
    mainWindow.setAlwaysOnTop(false);
  }
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  app.quit();
});