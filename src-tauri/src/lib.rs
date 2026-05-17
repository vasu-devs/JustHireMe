// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

#[cfg(debug_assertions)]
use std::path::Path;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::Serialize;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use tauri::{AppHandle, Emitter, Manager, RunEvent, State, WindowEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct SidecarPort(Mutex<Option<u16>>);
struct ApiTokenState(Mutex<Option<String>>);
struct SidecarChild(Mutex<Option<CommandChild>>);
struct SidecarError(Mutex<Option<String>>);
struct SidecarLastStderr(Mutex<Option<String>>);
struct SidecarStopping(Mutex<bool>);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct UpdateInstallStatus {
    platform: String,
    can_update: bool,
    needs_manual_install: bool,
    reason: String,
    install_dir: Option<String>,
    app_bundle: Option<String>,
}

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

#[cfg(target_os = "macos")]
fn display_path(path: &std::path::Path) -> String {
    path.to_string_lossy().to_string()
}

#[cfg(any(target_os = "macos", test))]
fn normalized_path(path: &std::path::Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

#[cfg(any(target_os = "macos", test))]
fn find_app_bundle_path(exe: &std::path::Path) -> Option<PathBuf> {
    exe.ancestors()
        .find(|path| {
            path.extension()
                .and_then(|extension| extension.to_str())
                .map(|extension| extension.eq_ignore_ascii_case("app"))
                .unwrap_or(false)
        })
        .map(std::path::Path::to_path_buf)
}

#[cfg(target_os = "macos")]
fn probe_install_dir_writable(install_dir: &std::path::Path) -> Result<(), String> {
    use std::fs::OpenOptions;
    use std::io::Write;
    use std::time::{SystemTime, UNIX_EPOCH};

    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    let probe_path = install_dir.join(format!(
        ".justhireme-update-write-test-{}-{stamp}",
        std::process::id()
    ));

    match OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&probe_path)
    {
        Ok(mut file) => {
            let _ = file.write_all(b"update preflight\n");
            let _ = std::fs::remove_file(&probe_path);
            Ok(())
        }
        Err(error) => Err(format!(
            "{}{}",
            error,
            error
                .raw_os_error()
                .map(|code| format!(" (os error {code})"))
                .unwrap_or_default()
        )),
    }
}

#[cfg(any(target_os = "macos", test))]
fn macos_update_block_reason(
    app_bundle: &std::path::Path,
    install_dir: &std::path::Path,
    writable_result: Result<(), String>,
) -> Option<String> {
    let app_path = normalized_path(app_bundle);
    let install_path = normalized_path(install_dir);

    if app_path.contains("/AppTranslocation/") {
        return Some(
            "JustHireMe is running from macOS Gatekeeper App Translocation. Move JustHireMe.app to /Applications or ~/Applications, open it from there, then run the update again.".into(),
        );
    }

    if app_path.starts_with("/Volumes/") || install_path.starts_with("/Volumes/") {
        return Some(
            "JustHireMe is running from a mounted disk image, which macOS exposes as read-only. Drag JustHireMe.app into /Applications or ~/Applications, open the installed copy, then run the update again.".into(),
        );
    }

    if let Err(error) = writable_result {
        return Some(format!(
            "JustHireMe cannot write to its install folder ({install_path}). Install the latest DMG manually into a writable Applications folder, then future in-app updates can continue. Details: {error}"
        ));
    }

    None
}

#[cfg(test)]
mod tests {
    use super::{find_app_bundle_path, macos_update_block_reason};
    use std::path::Path;

    #[test]
    fn finds_macos_app_bundle_from_executable_path() {
        let exe = Path::new("/Applications/JustHireMe.app/Contents/MacOS/JustHireMe");
        let bundle = find_app_bundle_path(exe).expect("bundle path");

        assert_eq!(bundle, Path::new("/Applications/JustHireMe.app"));
    }

    #[test]
    fn blocks_updates_from_mounted_disk_image() {
        let reason = macos_update_block_reason(
            Path::new("/Volumes/JustHireMe/JustHireMe.app"),
            Path::new("/Volumes/JustHireMe"),
            Ok(()),
        )
        .expect("blocked reason");

        assert!(reason.contains("mounted disk image"));
        assert!(reason.contains("read-only"));
    }

    #[test]
    fn blocks_updates_from_app_translocation() {
        let reason = macos_update_block_reason(
            Path::new("/private/var/folders/xx/AppTranslocation/123/d/JustHireMe.app"),
            Path::new("/private/var/folders/xx/AppTranslocation/123/d"),
            Ok(()),
        )
        .expect("blocked reason");

        assert!(reason.contains("App Translocation"));
    }

    #[test]
    fn blocks_updates_when_install_folder_is_not_writable() {
        let reason = macos_update_block_reason(
            Path::new("/Applications/JustHireMe.app"),
            Path::new("/Applications"),
            Err("Permission denied (os error 13)".into()),
        )
        .expect("blocked reason");

        assert!(reason.contains("cannot write"));
        assert!(reason.contains("Permission denied"));
    }

    #[test]
    fn allows_updates_from_writable_applications_folder() {
        let reason = macos_update_block_reason(
            Path::new("/Users/alice/Applications/JustHireMe.app"),
            Path::new("/Users/alice/Applications"),
            Ok(()),
        );

        assert!(reason.is_none());
    }
}

#[tauri::command]
fn get_update_install_status() -> UpdateInstallStatus {
    #[cfg(target_os = "macos")]
    {
        let exe = match std::env::current_exe() {
            Ok(path) => path,
            Err(error) => {
                return UpdateInstallStatus {
                    platform: "macos".into(),
                    can_update: false,
                    needs_manual_install: true,
                    reason: format!(
                        "JustHireMe could not determine its app location before updating: {error}"
                    ),
                    install_dir: None,
                    app_bundle: None,
                };
            }
        };

        let app_bundle = match find_app_bundle_path(&exe) {
            Some(path) => path,
            None => {
                return UpdateInstallStatus {
                    platform: "macos".into(),
                    can_update: true,
                    needs_manual_install: false,
                    reason: "JustHireMe is not running from a macOS app bundle.".into(),
                    install_dir: exe.parent().map(display_path),
                    app_bundle: None,
                };
            }
        };

        let install_dir = match app_bundle.parent() {
            Some(path) => path.to_path_buf(),
            None => {
                return UpdateInstallStatus {
                    platform: "macos".into(),
                    can_update: false,
                    needs_manual_install: true,
                    reason:
                        "JustHireMe could not determine the folder that contains the app bundle."
                            .into(),
                    install_dir: None,
                    app_bundle: Some(display_path(&app_bundle)),
                };
            }
        };

        let reason = macos_update_block_reason(
            &app_bundle,
            &install_dir,
            probe_install_dir_writable(&install_dir),
        );
        return UpdateInstallStatus {
            platform: "macos".into(),
            can_update: reason.is_none(),
            needs_manual_install: reason.is_some(),
            reason: reason.unwrap_or_else(|| {
                "JustHireMe is installed in a writable location and can use in-app updates.".into()
            }),
            install_dir: Some(display_path(&install_dir)),
            app_bundle: Some(display_path(&app_bundle)),
        };
    }

    #[cfg(not(target_os = "macos"))]
    {
        UpdateInstallStatus {
            platform: std::env::consts::OS.into(),
            can_update: true,
            needs_manual_install: false,
            reason: "In-app updates are available on this platform.".into(),
            install_dir: None,
            app_bundle: None,
        }
    }
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
fn cleanup_debug_python_sidecars(backend_dir: &Path) {
    let Some(python_path) = local_venv_python_path(backend_dir) else {
        return;
    };

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let exe = python_path.to_string_lossy().replace('\\', "\\\\");
    let output = std::process::Command::new("wmic")
        .args([
            "process",
            "where",
            &format!("ExecutablePath='{exe}'"),
            "get",
            "ProcessId,CommandLine",
            "/FORMAT:CSV",
        ])
        .creation_flags(CREATE_NO_WINDOW)
        .output();

    let Ok(output) = output else {
        return;
    };
    let backend = backend_dir.to_string_lossy().to_lowercase();
    let text = String::from_utf8_lossy(&output.stdout);
    for line in text.lines() {
        let lower = line.to_lowercase();
        if !lower.contains(&backend) {
            continue;
        }
        if let Some(pid) = line.rsplit(',').next().and_then(|value| value.trim().parse::<u32>().ok()) {
            kill_process_tree(pid);
        }
    }
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

#[cfg(windows)]
fn is_jhm_process(pid: u32) -> bool {
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let output = std::process::Command::new("tasklist")
        .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV", "/NH"])
        .creation_flags(CREATE_NO_WINDOW)
        .output();
    let Ok(output) = output else {
        return false;
    };
    let text = String::from_utf8_lossy(&output.stdout).to_lowercase();
    text.contains("jhm-sidecar") || text.contains("python")
}

#[cfg(not(windows))]
fn is_jhm_process(_pid: u32) -> bool {
    true
}

fn sidecar_pid_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_data_dir()
        .ok()
        .map(|dir| dir.join("sidecar.pid"))
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
    if is_jhm_process(pid) {
        eprintln!("[tauri] Cleaning stale sidecar process tree from pid file: {pid}");
        kill_process_tree(pid);
    } else {
        eprintln!("[tauri] Ignoring stale sidecar pid file for non-JustHireMe process: {pid}");
    }
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

fn spawn_sidecar(handle: AppHandle, restart_count: u8) -> Result<(), String> {
    if let Ok(mut port) = handle.state::<SidecarPort>().0.lock() {
        *port = None;
    }
    if let Ok(mut token) = handle.state::<ApiTokenState>().0.lock() {
        *token = None;
    }

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
            eprintln!("[tauri] No bundled or virtualenv runtime found - falling back to `uv`");
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
        handle
            .shell()
            .sidecar("jhm-sidecar-next")
            .expect("failed to create sidecar command")
    };

    let mut sidecar_cmd = sidecar_cmd;
    sidecar_cmd = sidecar_cmd.args(["--no-services"]);
    sidecar_cmd = sidecar_cmd.env("PYTHONUNBUFFERED", "1");
    if let Ok(app_data_dir) = handle.path().app_data_dir() {
        let _ = std::fs::create_dir_all(&app_data_dir);
        let app_data = app_data_dir.to_string_lossy().to_string();
        sidecar_cmd = sidecar_cmd
            .current_dir(&app_data_dir)
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
            let _ = handle.emit("sidecar-error", msg.clone());
            return Err(msg);
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
                    let text = String::from_utf8_lossy(&b).to_string();
                    for raw_line in text.lines() {
                        let line = raw_line.trim();
                        if !line.is_empty() {
                            eprintln!("[sidecar] {line}");
                            if let Ok(mut guard) = app_handle.state::<SidecarLastStderr>().0.lock() {
                                *guard = Some(line.to_string());
                            }
                            let lower = line.to_lowercase();
                            let is_error = lower.contains("error")
                                || lower.contains("traceback")
                                || lower.contains("exception")
                                || lower.contains("failed")
                                || lower.contains("library not loaded")
                                || lower.contains("not valid for use in process");
                            if is_error {
                                if let Ok(mut guard) = app_handle.state::<SidecarError>().0.lock() {
                                    *guard = Some(line.to_string());
                                }
                                let _ = app_handle.emit("sidecar-error", line.to_string());
                            }
                        }
                    }
                }
                CommandEvent::Terminated(s) => {
                    eprintln!("[tauri] Sidecar terminated: {:?}", s.code);
                    if let Ok(mut guard) = app_handle.state::<SidecarChild>().0.lock() {
                        let _ = guard.take();
                    }
                    let intentional_shutdown = app_handle
                        .state::<SidecarStopping>()
                        .0
                        .lock()
                        .map(|guard| *guard)
                        .unwrap_or(false);
                    if intentional_shutdown {
                        continue;
                    }

                    let clean_exit = matches!(s.code, Some(0));
                    let base = format!("Sidecar terminated before startup: {:?}", s.code);
                    let detail = app_handle
                        .state::<SidecarError>()
                        .0
                        .lock()
                        .ok()
                        .and_then(|guard| guard.clone())
                        .or_else(|| {
                            app_handle
                                .state::<SidecarLastStderr>()
                                .0
                                .lock()
                                .ok()
                                .and_then(|guard| guard.clone())
                        });
                    let msg = detail
                        .filter(|line| !line.trim().is_empty())
                        .map(|line| format!("{base}. Last backend output: {line}"))
                        .unwrap_or(base);
                    if let Ok(mut guard) = app_handle.state::<SidecarError>().0.lock() {
                        *guard = Some(msg.clone());
                    }
                    let _ = app_handle.emit("sidecar-error", msg.clone());
                    let _ = app_handle.emit("sidecar-terminated", ());

                    if !clean_exit && restart_count < 3 {
                        let delay = std::time::Duration::from_secs(2_u64.pow(restart_count as u32));
                        eprintln!(
                            "[tauri] Auto-restarting sidecar in {:?} (attempt {}/3)",
                            delay,
                            restart_count + 1
                        );
                        std::thread::sleep(delay);
                        if let Err(error) = spawn_sidecar(app_handle.clone(), restart_count + 1) {
                            let _ = app_handle.emit("sidecar-error", error);
                        }
                    }
                }
                _ => {}
            }
        }
    });

    Ok(())
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
        .manage(SidecarLastStderr(Mutex::new(None)))
        .manage(SidecarStopping(Mutex::new(false)))
        .invoke_handler(tauri::generate_handler![
            get_sidecar_port,
            get_api_token,
            get_sidecar_error,
            get_update_install_status,
            notify_high_score_lead
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            cleanup_stale_sidecar(&handle);
            if let Err(error) = spawn_sidecar(handle.clone(), 0) {
                eprintln!("[tauri] {error}");
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri application");

    app.run(|app_handle, event| match event {
        RunEvent::WindowEvent { label, event, .. } => {
            eprintln!("[tauri] Window event on {label}: {event:?}");
            if matches!(
                event,
                WindowEvent::CloseRequested { .. } | WindowEvent::Destroyed
            ) {
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
