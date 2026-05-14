// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

#[cfg(debug_assertions)]
use std::path::Path;
use std::path::PathBuf;
use std::sync::Mutex;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct SidecarPort(Mutex<Option<u16>>);
struct ApiTokenState(Mutex<Option<String>>);
struct SidecarChild(Mutex<Option<CommandChild>>);
struct SidecarError(Mutex<Option<String>>);
struct SidecarStopping(Mutex<bool>);

#[tauri::command]
fn get_sidecar_port(state: State<SidecarPort>) -> Result<u16, String> {
    state
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "Sidecar port not yet discovered".into())
}

#[tauri::command]
fn get_api_token(state: State<ApiTokenState>) -> Result<String, String> {
    state
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .ok_or_else(|| "API token not yet discovered".into())
}

#[tauri::command]
fn get_sidecar_error(state: State<SidecarError>) -> Result<String, String> {
    state
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .ok_or_else(|| "No sidecar error recorded".into())
}

#[tauri::command]
fn notify_high_score_lead(app: tauri::AppHandle, title: String, body: String) {
    use tauri_plugin_notification::NotificationExt;

    let _ = app
        .notification()
        .builder()
        .title(&title)
        .body(&body)
        .show();
}

#[cfg(debug_assertions)]
fn bundled_python_path(app: &AppHandle) -> Option<PathBuf> {
    let runtime_dir = app
        .path()
        .resource_dir()
        .ok()?
        .join("resources")
        .join("python-runtime");

    let candidates = if cfg!(windows) {
        vec!["python.exe", "python"]
    } else {
        vec!["bin/python3", "bin/python", "python"]
    };

    candidates
        .into_iter()
        .map(|candidate| runtime_dir.join(candidate))
        .find(|path| path.exists())
}

#[cfg(debug_assertions)]
fn local_venv_python_path(backend_dir: &Path) -> Option<PathBuf> {
    let candidates = if cfg!(windows) {
        vec![".venv/Scripts/python.exe", ".venv/Scripts/python"]
    } else {
        vec![
            ".venv/bin/python3",
            ".venv/bin/python",
            ".venv/bin/python.exe",
        ]
    };

    candidates
        .into_iter()
        .map(|candidate| backend_dir.join(candidate))
        .find(|path| path.exists())
}

#[cfg(debug_assertions)]
fn debug_backend_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(|p| p.join("backend"))
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default().join("backend"))
}

#[cfg(all(debug_assertions, windows))]
fn ps_single_quoted_path(path: &Path) -> String {
    path.to_string_lossy().replace('\'', "''")
}

#[cfg(all(debug_assertions, windows))]
fn cleanup_debug_python_sidecars(backend_dir: &Path) {
    let Some(python_path) = local_venv_python_path(backend_dir) else {
        return;
    };

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let exe = ps_single_quoted_path(&python_path);
    let backend = ps_single_quoted_path(backend_dir);
    let script = format!(
        "$exe='{exe}'; $backend='{backend}'; \
         Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | \
         Where-Object {{ $_.ExecutablePath -eq $exe -and $_.CommandLine -like ('*' + $backend + '*') }} | \
         ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
    );

    let _ = std::process::Command::new("powershell")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", &script])
        .creation_flags(CREATE_NO_WINDOW)
        .output();
}

#[cfg(all(debug_assertions, not(windows)))]
fn cleanup_debug_python_sidecars(_backend_dir: &Path) {}

fn kill_process_tree(pid: u32) {
    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;

        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }

    #[cfg(not(windows))]
    {
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .output();
    }
}

fn sidecar_pid_path(app: &AppHandle) -> Option<PathBuf> {
    app.path().app_data_dir().ok().map(|dir| dir.join("sidecar.pid"))
}

fn cleanup_stale_sidecar(app: &AppHandle) {
    let Some(pid_path) = sidecar_pid_path(app) else {
        return;
    };
    let Ok(raw_pid) = std::fs::read_to_string(&pid_path) else {
        return;
    };
    let Ok(pid) = raw_pid.trim().parse::<u32>() else {
        let _ = std::fs::remove_file(pid_path);
        return;
    };
    if pid == 0 {
        let _ = std::fs::remove_file(pid_path);
        return;
    }
    eprintln!("[tauri] Cleaning stale sidecar process tree from pid file: {pid}");
    kill_process_tree(pid);
    let _ = std::fs::remove_file(pid_path);
}

fn remember_sidecar_pid(app: &AppHandle, pid: u32) {
    let Some(pid_path) = sidecar_pid_path(app) else {
        return;
    };
    if let Some(parent) = pid_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = std::fs::write(pid_path, pid.to_string());
}

fn shutdown_sidecar(app: &AppHandle) {
    if let Ok(mut stopping) = app.state::<SidecarStopping>().0.lock() {
        *stopping = true;
    }

    let child = app
        .state::<SidecarChild>()
        .0
        .lock()
        .ok()
        .and_then(|mut guard| guard.take());

    if let Some(child) = child {
        let pid = child.pid();
        eprintln!("[tauri] Stopping sidecar process tree: {pid}");
        kill_process_tree(pid);
        let _ = child.kill();
    }

    if let Ok(mut port) = app.state::<SidecarPort>().0.lock() {
        *port = None;
    }

    if let Ok(mut token) = app.state::<ApiTokenState>().0.lock() {
        *token = None;
    }

    if let Some(pid_path) = sidecar_pid_path(app) {
        let _ = std::fs::remove_file(pid_path);
    }

    #[cfg(debug_assertions)]
    cleanup_debug_python_sidecars(&debug_backend_dir());
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .manage(SidecarPort(Mutex::new(None)))
        .manage(ApiTokenState(Mutex::new(None)))
        .manage(SidecarChild(Mutex::new(None)))
        .manage(SidecarError(Mutex::new(None)))
        .manage(SidecarStopping(Mutex::new(false)))
        .invoke_handler(tauri::generate_handler![
            get_sidecar_port,
            get_api_token,
            get_sidecar_error,
            notify_high_score_lead
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            cleanup_stale_sidecar(&handle);

            #[cfg(debug_assertions)]
            let backend_dir = debug_backend_dir();

            #[cfg(debug_assertions)]
            cleanup_debug_python_sidecars(&backend_dir);

            #[cfg(debug_assertions)]
            let sidecar_cmd = {
                let bundled = bundled_python_path(&handle);
                let local_venv = local_venv_python_path(&backend_dir);

                if let Some(ref py) = bundled {
                    eprintln!("[tauri] Using bundled runtime: {}", py.display());
                } else if let Some(ref py) = local_venv {
                    eprintln!("[tauri] Using backend virtualenv: {}", py.display());
                } else {
                    eprintln!(
                        "[tauri] No bundled or virtualenv runtime found - falling back to `uv`"
                    );
                }

                if let Some(py) = bundled {
                    handle
                        .shell()
                        .command(py.to_string_lossy().to_string())
                        .args(["main.py"])
                        .current_dir(&backend_dir)
                } else if let Some(py) = local_venv {
                    handle
                        .shell()
                        .command(py.to_string_lossy().to_string())
                        .args(["main.py"])
                        .current_dir(&backend_dir)
                } else {
                    handle
                        .shell()
                        .command("uv")
                        .args(["run", "python", "main.py"])
                        .current_dir(&backend_dir)
                }
            };

            #[cfg(not(debug_assertions))]
            let sidecar_cmd = {
                eprintln!("[tauri] Using bundled backend sidecar");
                // Tauri installs externalBin sidecars beside the app executable under
                // the binary basename, so this resolves to jhm-sidecar-next.exe on Windows.
                handle
                    .shell()
                    .sidecar("jhm-sidecar-next")
                    .expect("failed to create sidecar command")
            };

            let mut sidecar_cmd = sidecar_cmd;
            sidecar_cmd = sidecar_cmd.env("PYTHONUNBUFFERED", "1");
            if let Ok(app_data_dir) = handle.path().app_data_dir() {
                let _ = std::fs::create_dir_all(&app_data_dir);
                let app_data = app_data_dir.to_string_lossy().to_string();
                sidecar_cmd = sidecar_cmd
                    .env("LOCALAPPDATA", app_data.clone())
                    .env("JHM_APP_DATA_DIR", app_data);
            }
            if let Ok(resource_dir) = handle.path().resource_dir() {
                let bundled_browsers_path = resource_dir
                    .join("resources")
                    .join("bin")
                    .join("ms-playwright");
                if bundled_browsers_path.exists() {
                    sidecar_cmd = sidecar_cmd.env(
                        "PLAYWRIGHT_BROWSERS_PATH",
                        bundled_browsers_path.to_string_lossy().to_string(),
                    );
                }
            }
            if let Ok(app_data_dir) = handle.path().app_data_dir() {
                let browser_cache = app_data_dir.join("browser-runtime").join("ms-playwright");
                sidecar_cmd = sidecar_cmd.env(
                    "JHM_BROWSER_RUNTIME_DIR",
                    browser_cache.to_string_lossy().to_string(),
                );
                if !browser_cache.exists() {
                    let _ = std::fs::create_dir_all(&browser_cache);
                }
                sidecar_cmd = sidecar_cmd.env(
                    "PLAYWRIGHT_BROWSERS_PATH",
                    browser_cache.to_string_lossy().to_string(),
                );
            }

            let (mut rx, child) = match sidecar_cmd.spawn() {
                Ok(result) => result,
                Err(err) => {
                    let msg = format!("Failed to spawn Python sidecar: {err}");
                    eprintln!("[tauri] {msg}");
                    if let Ok(mut guard) = handle.state::<SidecarError>().0.lock() {
                        *guard = Some(msg.clone());
                    }
                    let _ = handle.emit("sidecar-error", msg);
                    return Ok(());
                }
            };

            let sidecar_pid = child.pid();
            eprintln!("[tauri] Sidecar PID: {sidecar_pid}");
            remember_sidecar_pid(&handle, sidecar_pid);
            if let Ok(mut stopping) = handle.state::<SidecarStopping>().0.lock() {
                *stopping = false;
            }

            if let Ok(mut guard) = handle.state::<SidecarChild>().0.lock() {
                *guard = Some(child);
            }

            let app_handle = handle.clone();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(b) => {
                            let text = String::from_utf8_lossy(&b).to_string();
                            for raw_line in text.lines() {
                                let line = raw_line.trim();
                                if let Some(port_str) = line.strip_prefix("PORT:") {
                                    if let Ok(port) = port_str.parse::<u16>() {
                                        if let Ok(mut g) = app_handle.state::<SidecarPort>().0.lock() {
                                            *g = Some(port);
                                        }
                                        let _ = app_handle.emit("sidecar-port", port);
                                        eprintln!("[tauri] Sidecar port: {port}");
                                    }
                                } else if let Some(token) = line.strip_prefix("JHM_TOKEN=") {
                                    if let Ok(mut g) = app_handle.state::<ApiTokenState>().0.lock() {
                                        *g = Some(token.to_string());
                                    }
                                    let _ = app_handle.emit("sidecar-token", token.to_string());
                                }
                            }
                        }
                        CommandEvent::Stderr(b) => {
                            let line = String::from_utf8_lossy(&b).trim().to_string();
                            if !line.is_empty() {
                                eprintln!("[sidecar] {line}");
                                let lower = line.to_lowercase();
                                let is_error = lower.contains("error")
                                    || lower.contains("traceback")
                                    || lower.contains("exception")
                                    || lower.contains("failed");
                                if is_error {
                                    if let Ok(mut guard) = app_handle.state::<SidecarError>().0.lock() {
                                        *guard = Some(line.clone());
                                    }
                                    let _ = app_handle.emit("sidecar-error", line);
                                }
                            }
                        }
                        CommandEvent::Terminated(s) => {
                            eprintln!("[tauri] Sidecar terminated: {:?}", s.code);
                            let intentional_shutdown = app_handle
                                .state::<SidecarStopping>()
                                .0
                                .lock()
                                .map(|guard| *guard)
                                .unwrap_or(false);
                            if intentional_shutdown {
                                continue;
                            }
                            let msg = format!("Sidecar terminated before startup: {:?}", s.code);
                            if let Ok(mut guard) = app_handle.state::<SidecarError>().0.lock() {
                                *guard = Some(msg.clone());
                            }
                            let _ = app_handle.emit("sidecar-error", msg);
                            let _ = app_handle.emit("sidecar-terminated", ());
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri application");

    app.run(|app_handle, event| match event {
        RunEvent::WindowEvent { label, event, .. } => {
            eprintln!("[tauri] Window event on {label}: {event:?}");
            if matches!(event, WindowEvent::CloseRequested { .. } | WindowEvent::Destroyed) {
                shutdown_sidecar(app_handle);
            }
        }
        RunEvent::ExitRequested { code, .. } => {
            eprintln!("[tauri] Exit requested: {code:?}");
            shutdown_sidecar(app_handle);
        }
        RunEvent::Exit => {
            eprintln!("[tauri] App exit");
            shutdown_sidecar(app_handle);
        }
        _ => {}
    });
}
