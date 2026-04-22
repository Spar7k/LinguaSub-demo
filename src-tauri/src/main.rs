#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[cfg(target_os = "windows")]
use std::{
    env,
    fs,
    net::{SocketAddr, TcpStream},
    os::windows::process::CommandExt,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::Mutex,
    time::Duration,
};

use tauri::Manager;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;
#[cfg(target_os = "windows")]
const BACKEND_HOST: [u8; 4] = [127, 0, 0, 1];
#[cfg(target_os = "windows")]
const BACKEND_PORT: u16 = 8765;
#[cfg(target_os = "windows")]
const UNINSTALL_REGISTRY_KEYS: [&str; 3] = [
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\LinguaSub",
    r"HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\LinguaSub",
    r"HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\LinguaSub",
];

#[cfg(target_os = "windows")]
struct BackendSidecar(Mutex<Option<std::process::Child>>);

#[cfg(target_os = "windows")]
struct UninstallTarget {
    program: String,
    raw_args: Option<String>,
    working_directory: Option<PathBuf>,
}

#[cfg(target_os = "windows")]
fn backend_socket_addr() -> SocketAddr {
    SocketAddr::from((BACKEND_HOST, BACKEND_PORT))
}

#[cfg(target_os = "windows")]
fn backend_is_reachable() -> bool {
    TcpStream::connect_timeout(&backend_socket_addr(), Duration::from_millis(250)).is_ok()
}

#[cfg(target_os = "windows")]
fn resolve_sidecar_path() -> Result<PathBuf, String> {
    let current_executable =
        env::current_exe().map_err(|error| format!("Failed to resolve current executable: {error}"))?;
    let executable_dir = current_executable
        .parent()
        .ok_or_else(|| "Could not resolve the LinguaSub executable directory.".to_string())?;
    let sidecar_path = executable_dir.join("linguasub-backend.exe");

    if sidecar_path.exists() {
        return Ok(sidecar_path);
    }

    Err(format!(
        "Bundled backend sidecar was not found at {}.",
        sidecar_path.display()
    ))
}

#[cfg(target_os = "windows")]
fn ensure_app_data_file_path(app: &tauri::AppHandle, file_name: &str) -> Result<PathBuf, String> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Failed to resolve the LinguaSub app data directory: {error}"))?;
    fs::create_dir_all(&app_data_dir)
        .map_err(|error| format!("Failed to prepare the LinguaSub app data directory: {error}"))?;
    Ok(app_data_dir.join(file_name))
}

#[cfg(target_os = "windows")]
fn ensure_app_data_subdir(app: &tauri::AppHandle, directory_name: &str) -> Result<PathBuf, String> {
    let directory_path = ensure_app_data_file_path(app, directory_name)?;
    fs::create_dir_all(&directory_path)
        .map_err(|error| format!("Failed to prepare the LinguaSub runtime directory: {error}"))?;
    Ok(directory_path)
}

#[cfg(target_os = "windows")]
fn resolve_release_runtime_dir(app: &tauri::AppHandle) -> Result<Option<PathBuf>, String> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Failed to resolve the LinguaSub resource directory: {error}"))?;
    candidates.push(resource_dir.join("runtime"));
    candidates.push(resource_dir.clone());

    let current_executable = env::current_exe()
        .map_err(|error| format!("Failed to resolve the LinguaSub executable path: {error}"))?;
    if let Some(executable_dir) = current_executable.parent() {
        candidates.push(executable_dir.join("resources").join("runtime"));
        candidates.push(executable_dir.join("runtime"));
    }

    for runtime_dir in candidates {
        let ffmpeg_path = runtime_dir.join("ffmpeg").join("ffmpeg.exe");
        if ffmpeg_path.exists() && ffmpeg_path.is_file() {
            return Ok(Some(runtime_dir));
        }
    }

    Ok(None)
}

#[cfg(target_os = "windows")]
fn start_backend_sidecar(app: &tauri::AppHandle) -> Result<(), String> {
    if cfg!(debug_assertions) || backend_is_reachable() {
        return Ok(());
    }

    let sidecar_path = resolve_sidecar_path()?;
    let sidecar_dir = sidecar_path
        .parent()
        .ok_or_else(|| "Could not resolve the backend sidecar directory.".to_string())?;
    let config_path = ensure_app_data_file_path(app, "app-config.json")?;
    let temp_dir = ensure_app_data_subdir(app, "backend-temp")?;
    let model_dir = ensure_app_data_subdir(app, "speech-models")?;
    let runtime_dir = resolve_release_runtime_dir(app)?;

    let mut command = Command::new(&sidecar_path);
    command
        .current_dir(sidecar_dir)
        .env("LINGUASUB_CONFIG_PATH", &config_path)
        .env("LINGUASUB_MODEL_DIR", &model_dir)
        .env("TEMP", &temp_dir)
        .env("TMP", &temp_dir)
        .creation_flags(CREATE_NO_WINDOW)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    if let Some(runtime_dir) = runtime_dir {
        let ffmpeg_path = runtime_dir.join("ffmpeg").join("ffmpeg.exe");
        command
            .env("LINGUASUB_RUNTIME_DIR", &runtime_dir)
            .env("LINGUASUB_FFMPEG_PATH", &ffmpeg_path);
    }

    let child = command
        .spawn()
        .map_err(|error| format!("Failed to start the bundled backend sidecar: {error}"))?;

    let state = app.state::<BackendSidecar>();
    let mut sidecar = state
        .0
        .lock()
        .map_err(|_| "Failed to store the LinguaSub backend process handle.".to_string())?;
    *sidecar = Some(child);

    Ok(())
}

#[cfg(target_os = "windows")]
fn stop_backend_sidecar(app: &tauri::AppHandle) {
    if let Ok(mut sidecar) = app.state::<BackendSidecar>().0.lock() {
        if let Some(child) = sidecar.as_mut() {
            let _ = child.kill();
            let _ = child.wait();
        }

        *sidecar = None;
    }
}

#[cfg(target_os = "windows")]
fn extract_uninstall_string(reg_query_output: &str) -> Option<String> {
    for line in reg_query_output.lines() {
        let trimmed = line.trim();
        if !trimmed.starts_with("UninstallString") {
            continue;
        }

        for value_type in ["REG_SZ", "REG_EXPAND_SZ"] {
            if let Some(index) = trimmed.find(value_type) {
                let command = trimmed[index + value_type.len()..].trim();
                if !command.is_empty() {
                    return Some(command.to_string());
                }
            }
        }
    }

    None
}

#[cfg(target_os = "windows")]
fn split_uninstall_command(command_line: &str) -> Result<(String, Option<String>), String> {
    let trimmed = command_line.trim();
    if trimmed.is_empty() {
        return Err("The uninstall command is empty.".to_string());
    }

    if let Some(rest) = trimmed.strip_prefix('"') {
        let closing_quote_index = rest
            .find('"')
            .ok_or_else(|| "The uninstall command has an invalid quoted path.".to_string())?;
        let program = rest[..closing_quote_index].trim().to_string();
        let raw_args = rest[closing_quote_index + 1..].trim();

        return Ok((
            program,
            if raw_args.is_empty() {
                None
            } else {
                Some(raw_args.to_string())
            },
        ));
    }

    if let Some((program, raw_args)) = trimmed.split_once(char::is_whitespace) {
        let trimmed_args = raw_args.trim();
        return Ok((
            program.trim().to_string(),
            if trimmed_args.is_empty() {
                None
            } else {
                Some(trimmed_args.to_string())
            },
        ));
    }

    Ok((trimmed.to_string(), None))
}

#[cfg(target_os = "windows")]
fn resolve_installed_uninstaller_target() -> Result<Option<UninstallTarget>, String> {
    let current_executable =
        env::current_exe().map_err(|_| "Could not resolve the current LinguaSub executable.".to_string())?;
    let executable_dir = current_executable
        .parent()
        .ok_or_else(|| "Could not resolve the LinguaSub install directory.".to_string())?;
    let uninstaller_path = executable_dir.join("uninstall.exe");

    if !uninstaller_path.exists() {
        return Ok(None);
    }

    Ok(Some(UninstallTarget {
        program: uninstaller_path.to_string_lossy().into_owned(),
        raw_args: None,
        working_directory: Some(executable_dir.to_path_buf()),
    }))
}

#[cfg(target_os = "windows")]
fn path_like_program(program: &str) -> bool {
    program.contains('\\') || program.contains('/') || program.contains(':')
}

#[cfg(target_os = "windows")]
fn build_registry_uninstall_target(command_line: &str) -> Result<UninstallTarget, String> {
    let (program, raw_args) = split_uninstall_command(command_line)?;
    let working_directory = if path_like_program(&program) {
        let program_path = PathBuf::from(&program);
        if !program_path.exists() {
            return Err("The registered uninstall target does not exist.".to_string());
        }

        program_path.parent().map(Path::to_path_buf)
    } else {
        None
    };

    Ok(UninstallTarget {
        program,
        raw_args,
        working_directory,
    })
}

#[cfg(target_os = "windows")]
fn find_uninstall_target() -> Result<UninstallTarget, String> {
    if let Some(target) = resolve_installed_uninstaller_target()? {
        return Ok(target);
    }

    for registry_key in UNINSTALL_REGISTRY_KEYS {
        let output = Command::new("reg")
            .args(["query", registry_key, "/v", "UninstallString"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null())
            .stderr(Stdio::null())
            .output()
            .map_err(|error| format!("Failed to query the Windows uninstall registry: {error}"))?;

        if !output.status.success() {
            continue;
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        if let Some(command) = extract_uninstall_string(&stdout) {
            if let Ok(target) = build_registry_uninstall_target(&command) {
                return Ok(target);
            }
        }
    }

    Err(
        "Could not find the installed LinguaSub uninstaller. Reinstall the app or uninstall it from Windows Settings."
            .to_string(),
    )
}

#[cfg(target_os = "windows")]
fn spawn_uninstall_helper(target: &UninstallTarget) -> Result<(), String> {
    let wait_for_parent_and_uninstall = r#"
      $parentId = [int]$env:LINGUASUB_UNINSTALL_PARENT_PID
      if ($parentId -gt 0) {
        Wait-Process -Id $parentId -Timeout 10 -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 400
      }
      $program = $env:LINGUASUB_UNINSTALL_PROGRAM
      if ([string]::IsNullOrWhiteSpace($program)) { exit 1 }
      $workingDirectory = $env:LINGUASUB_UNINSTALL_CWD
      if ([string]::IsNullOrWhiteSpace($workingDirectory)) {
        $workingDirectory = Split-Path -Parent $program
      }
      $rawArgs = $env:LINGUASUB_UNINSTALL_ARGS
      if ([string]::IsNullOrWhiteSpace($rawArgs)) {
        Start-Process -FilePath $program -WorkingDirectory $workingDirectory -WindowStyle Hidden
      } else {
        Start-Process -FilePath $program -ArgumentList $rawArgs -WorkingDirectory $workingDirectory -WindowStyle Hidden
      }
    "#;

    let mut command = Command::new("powershell.exe");
    command
        .args([
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            wait_for_parent_and_uninstall,
        ])
        .env(
            "LINGUASUB_UNINSTALL_PARENT_PID",
            std::process::id().to_string(),
        )
        .env("LINGUASUB_UNINSTALL_PROGRAM", &target.program)
        .env(
            "LINGUASUB_UNINSTALL_ARGS",
            target.raw_args.clone().unwrap_or_default(),
        )
        .env(
            "LINGUASUB_UNINSTALL_CWD",
            target
                .working_directory
                .as_ref()
                .map(|value| value.to_string_lossy().into_owned())
                .unwrap_or_default(),
        )
        .creation_flags(CREATE_NO_WINDOW)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    command
        .spawn()
        .map_err(|_| "Could not prepare the LinguaSub uninstaller helper. Please try again or uninstall it from Windows Settings.".to_string())?;

    Ok(())
}

#[tauri::command]
fn path_exists(path: String) -> Result<bool, String> {
    #[cfg(target_os = "windows")]
    {
        let normalized_path = PathBuf::from(path);
        return Ok(normalized_path.exists());
    }

    #[allow(unreachable_code)]
    Err("LinguaSub path checks are only available on Windows.".to_string())
}

#[tauri::command]
fn open_path_in_file_manager(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        let normalized_path = PathBuf::from(path);
        if !normalized_path.exists() {
            return Err(
                "The selected file or folder could not be found. It may have been moved or deleted."
                    .to_string(),
            );
        }

        let mut command = Command::new("explorer.exe");
        if normalized_path.is_file() {
            command.arg(format!("/select,{}", normalized_path.display()));
        } else {
            command.arg(normalized_path.as_os_str());
        }

        command
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("Could not open the selected location in Windows Explorer: {error}"))?;

        return Ok(());
    }

    #[allow(unreachable_code)]
    Err("LinguaSub file-manager actions are only available on Windows.".to_string())
}

#[tauri::command]
fn start_uninstall(app: tauri::AppHandle) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        let uninstall_target = find_uninstall_target()?;
        spawn_uninstall_helper(&uninstall_target)?;
        app.exit(0);
        return Ok(());
    }

    #[allow(unreachable_code)]
    Err("LinguaSub uninstall is only available on Windows.".to_string())
}

fn main() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            start_uninstall,
            open_path_in_file_manager,
            path_exists
        ])
        .setup(|app| {
            #[cfg(target_os = "windows")]
            {
                app.manage(BackendSidecar(Mutex::new(None)));
                if let Err(error) = start_backend_sidecar(&app.handle()) {
                    eprintln!("{error}");
                }
            }

            Ok(())
        });

    let app = builder
        .build(tauri::generate_context!())
        .expect("error while running LinguaSub");

    app.run(|app_handle, event| {
        #[cfg(target_os = "windows")]
        if matches!(
            event,
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
        ) {
            stop_backend_sidecar(app_handle);
        }
    });
}

#[cfg(all(test, target_os = "windows"))]
mod tests {
    use super::{build_registry_uninstall_target, split_uninstall_command};
    use std::{fs, path::PathBuf, time::{SystemTime, UNIX_EPOCH}};

    fn unique_temp_path(file_name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time should be after unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("linguasub-{stamp}-{file_name}"))
    }

    #[test]
    fn split_uninstall_command_handles_quoted_paths_and_args() {
        let (program, raw_args) = split_uninstall_command(
            r#""C:\Program Files\LinguaSub\uninstall.exe" /S _?=C:\Users\demo\AppData\Local\LinguaSub"#,
        )
        .expect("quoted uninstall command should parse");

        assert_eq!(program, r#"C:\Program Files\LinguaSub\uninstall.exe"#);
        assert_eq!(
            raw_args.as_deref(),
            Some(r#"/S _?=C:\Users\demo\AppData\Local\LinguaSub"#),
        );
    }

    #[test]
    fn build_registry_uninstall_target_preserves_working_directory_for_real_paths() {
        let program_path = unique_temp_path("uninstall.exe");
        fs::write(&program_path, b"fake").expect("should create fake uninstaller");

        let target = build_registry_uninstall_target(&format!(
            "\"{}\" /S",
            program_path.display()
        ))
        .expect("registry uninstall target should build");

        assert_eq!(target.program, program_path.to_string_lossy());
        assert_eq!(target.raw_args.as_deref(), Some("/S"));
        assert_eq!(
            target.working_directory.as_deref(),
            program_path.parent(),
        );

        fs::remove_file(program_path).ok();
    }
}
