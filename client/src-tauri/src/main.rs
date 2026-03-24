#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use sysinfo::{System, ProcessesToUpdate};
use tauri::{Emitter, Window}; 
use std::thread;
use std::process::Command;
use std::time::Duration;

// ─── THE BLACKLIST ───
// These are the binary names for screen recorders, remote desktops, and VMs.
const FORBIDDEN_PROCESSES: &[&str] = &[
    "obs64.exe", "obs32.exe", "discord.exe", "skype.exe", 
    "teamviewer.exe", "anydesk.exe", "vboxclient.exe", 
    "vmtoolsd.exe", "zoom.exe", "webex.exe"
];

// ─── COMMAND: ENFORCE OS LOCKDOWN ───
#[tauri::command]
fn enforce_lockdown(window: Window) -> Result<(), String> {
    // 1. Force absolute fullscreen (hides Windows taskbar and Mac dock)
    window.set_fullscreen(true).map_err(|e| e.to_string())?;
    
    // 2. Pin to top (prevents opening cheat sheets over the exam)
    window.set_always_on_top(true).map_err(|e| e.to_string())?;
    
    // 3. Remove minimize/close buttons
    window.set_decorations(false).map_err(|e| e.to_string())?;
    
    // 4. Check for multiple monitors
    if let Ok(monitors) = window.available_monitors() {
        if monitors.len() > 1 {
            return Err("MULTIPLE_DISPLAYS_DETECTED".to_string());
        }
    }
    
    Ok(())
}

// ─── COMMAND: MANUAL INTEGRITY CHECK ───
#[tauri::command]
fn perform_integrity_check() -> String {
    let mut sys = System::new_all();
    sys.refresh_all();

    let mut detected_threats = Vec::new();

    for (_pid, process) in sys.processes() {
        // Safely convert OS string to standard Rust string before checking
        let proc_name = process.name().to_string_lossy().to_lowercase();
        for &forbidden in FORBIDDEN_PROCESSES {
            if proc_name.contains(forbidden) {
                detected_threats.push(proc_name.clone());
            }
        }
    }

    if detected_threats.is_empty() {
        "SECURE".to_string()
    } else {
        format!("TAMPER_DETECTED: {}", detected_threats.join(", "))
    }
}

// ─── COMMAND: KILL PROHIBITED APPS ───
#[tauri::command]
fn kill_prohibited_apps() {
    let apps_to_kill = ["Discord.exe", "WhatsApp.exe", "Telegram.exe", "comet.exe"];

    for app in apps_to_kill.iter() {
        // /F = Force, /T = process tree, /IM = image name
        let _ = Command::new("taskkill")
            .args(["/F", "/T", "/IM", app])
            .output();
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let app_handle = app.handle().clone();
            
            // ─── THE WATCHDOG THREAD ───
            thread::spawn(move || {
                let mut sys = System::new_all();
                loop {
                    // sysinfo v0.30+ requires explicit update parameters
                    sys.refresh_processes(ProcessesToUpdate::All, true);
                    for (_pid, process) in sys.processes() {
                        let proc_name = process.name().to_string_lossy().to_lowercase();
                        for &forbidden in FORBIDDEN_PROCESSES {
                            if proc_name.contains(forbidden) {
                                // Tauri v2 uses .emit() instead of .emit_all()
                                let _ = app_handle.emit(
                                    "security_violation", 
                                    format!("Banned process launched: {}", proc_name)
                                );
                            }
                        }
                    }
                    thread::sleep(Duration::from_secs(5));
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            enforce_lockdown, 
            perform_integrity_check,
            kill_prohibited_apps
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}