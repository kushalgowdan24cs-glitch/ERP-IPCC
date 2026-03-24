use sysinfo::System;
use tauri::{AppHandle, Emitter, Manager};
use arboard::Clipboard;
use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

// ── BLACKLISTED PROCESSES ──
// These apps will be force-killed if detected during an exam.
const BLACKLISTED_PROCESSES: &[&str] = &[
    // Screen sharing & remote access
    "anydesk.exe",
    "anydesk",
    "teamviewer.exe",
    "teamviewer",
    "rustdesk.exe",
    "chrome_remote_desktop",
    // Communication apps (answer feeding)
    "discord.exe",
    "discord",
    "telegram.exe",
    "telegram",
    "slack.exe",
    "slack",
    "whatsapp.exe",
    "whatsapp",
    "zoom.exe",
    "zoom",
    "skype.exe",
    "skype",
    "teams.exe",
    "ms-teams.exe",
    // Screen recording / streaming
    "obs64.exe",
    "obs32.exe",
    "obs.exe",
    "obs",
    "streamlabs.exe",
    "streamlabs",
    "bandicam.exe",
    "camtasia.exe",
    "xsplit.exe",
    "sharex.exe",
    // Virtual machines (hiding cheating)
    "vmware.exe",
    "virtualbox.exe",
    "virtualboxvm.exe",
    "vmplayer.exe",
    // Specific banned app
    "comet.exe",
    "comet",
];

#[derive(Clone, Serialize)]
struct KilledProcess {
    name: String,
    pid: u32,
    reason: String,
}

#[derive(Clone, Serialize)]
struct ProcessScanResult {
    killed: Vec<KilledProcess>,
    scan_time_ms: u128,
    total_processes: usize,
}

/// Tauri command: manually trigger a single process scan
#[tauri::command]
fn scan_and_kill_processes() -> ProcessScanResult {
    let mut sys = System::new();
    sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);

    let mut killed = Vec::new();
    let start = std::time::Instant::now();
    let total = sys.processes().len();

    for (pid, process) in sys.processes() {
        let proc_name = process.name().to_string_lossy().to_lowercase();

        for &blacklisted in BLACKLISTED_PROCESSES {
            if proc_name == blacklisted || proc_name.contains(blacklisted) {
                // KILL IT
                let success = process.kill();
                if success {
                    killed.push(KilledProcess {
                        name: process.name().to_string_lossy().to_string(),
                        pid: pid.as_u32(),
                        reason: format!("Blacklisted application: {}", blacklisted),
                    });
                    log::warn!(
                        "🔴 KILLED process: {} (PID: {}) — reason: blacklisted",
                        process.name().to_string_lossy(),
                        pid.as_u32()
                    );
                }
                break;
            }
        }
    }

    ProcessScanResult {
        killed,
        scan_time_ms: start.elapsed().as_millis(),
        total_processes: total,
    }
}

/// Tauri command: get list of blacklisted process names
#[tauri::command]
fn get_blacklist() -> Vec<String> {
    BLACKLISTED_PROCESSES.iter().map(|s| s.to_string()).collect()
}

/// Background monitor: runs every 2 seconds, emits events to frontend
fn start_background_monitor(app: AppHandle, active: Arc<AtomicBool>) {
    thread::spawn(move || {
        let mut sys = System::new();

        loop {
            if !active.load(Ordering::Relaxed) {
                thread::sleep(Duration::from_millis(500));
                continue;
            }

            sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);

            let mut killed = Vec::new();

            for (pid, process) in sys.processes() {
                let proc_name = process.name().to_string_lossy().to_lowercase();

                for &blacklisted in BLACKLISTED_PROCESSES {
                    if proc_name == blacklisted || proc_name.contains(blacklisted) {
                        let success = process.kill();
                        if success {
                            killed.push(KilledProcess {
                                name: process.name().to_string_lossy().to_string(),
                                pid: pid.as_u32(),
                                reason: format!("Blacklisted: {}", blacklisted),
                            });
                            log::warn!(
                                "🔴 [BG] KILLED: {} (PID: {})",
                                process.name().to_string_lossy(),
                                pid.as_u32()
                            );
                        }
                        break;
                    }
                }
            }

            // Emit event to frontend if any processes were killed
            if !killed.is_empty() {
                let _ = app.emit("process-killed", &killed);
            }

            thread::sleep(Duration::from_secs(2));
        }
    });
}

/// Clipboard monitor: runs every 500ms, clears clipboard if it contains text
fn start_clipboard_monitor(app: AppHandle, active: Arc<AtomicBool>) {
    thread::spawn(move || {
        let mut clipboard = match Clipboard::new() {
            Ok(c) => c,
            Err(e) => {
                log::error!("Failed to initialize clipboard: {}", e);
                return;
            }
        };

        // When activating, do an initial clear so pre-copied content is wiped
        let mut was_active = false;

        loop {
            let is_active = active.load(Ordering::Relaxed);
            
            if !is_active {
                was_active = false;
                thread::sleep(Duration::from_millis(500));
                continue;
            }

            if !was_active {
                // Exam just started! Clear everything immediately.
                let _ = clipboard.set_text("");
                was_active = true;
            }

            // Check if there is text in the clipboard
            if let Ok(text) = clipboard.get_text() {
                if !text.trim().is_empty() {
                    // Nuke the clipboard
                    let _ = clipboard.set_text("");
                    
                    log::warn!("📋 Clipboard blocked and cleared!");
                    
                    // Emit event to frontend
                    let _ = app.emit("clipboard-violation", "Clipboard content was cleared.");
                }
            }

            thread::sleep(Duration::from_millis(500));
        }
    });
}

/// Tauri command: start the background monitors
#[tauri::command]
fn start_process_monitor(app: AppHandle, state: tauri::State<'_, MonitorState>) {
    state.active.store(true, Ordering::Relaxed);
    log::info!("🛡️ Anti-cheat monitors ACTIVATED — scanning processes and clipboard");

    // Do an immediate scan
    let result = scan_and_kill_processes();
    if !result.killed.is_empty() {
        let _ = app.emit("process-killed", &result.killed);
    }
}

/// Tauri command: stop the background process monitor
#[tauri::command]
fn stop_process_monitor(state: tauri::State<'_, MonitorState>) {
    state.active.store(false, Ordering::Relaxed);
    log::info!("🛡️ Process monitor DEACTIVATED");
}

struct MonitorState {
    active: Arc<AtomicBool>,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let monitor_active = Arc::new(AtomicBool::new(false));

    tauri::Builder::default()
        .manage(MonitorState {
            active: monitor_active.clone(),
        })
        .setup(move |app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Start the background monitor threads (waits until activated)
            start_background_monitor(app.handle().clone(), monitor_active.clone());
            start_clipboard_monitor(app.handle().clone(), monitor_active.clone());
            log::info!("🛡️ ProctorShield System Monitors initialized (idle until exam starts)");

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            scan_and_kill_processes,
            get_blacklist,
            start_process_monitor,
            stop_process_monitor,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
