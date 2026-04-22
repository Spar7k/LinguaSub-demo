# Step 10: Windows Packaging and Release Plan

## Goal

This step closes the project with a practical Windows delivery plan.

LinguaSub should now be:

- explainable to teammates and testers
- runnable in development
- demoable as a desktop workflow
- deliverable with a realistic Windows release plan

## What Is Already Completed

Already implemented in the codebase:

- React + Tauri desktop frontend shell
- Python backend for import, SRT, transcription, translation, preview, and export
- startup environment check at `GET /environment/check`
- clear backend errors for missing FFmpeg, missing `faster-whisper`, invalid SRT, invalid export, and missing API key
- editable subtitle workflow from import through export

Still depends on the local build machine:

- Rust toolchain and Tauri CLI
- Visual Studio Build Tools for Windows desktop packaging
- WebView2 runtime
- FFmpeg
- `faster-whisper`
- Python runtime or a packaged backend executable

## Two Delivery Modes

### 1. Development Build

Use this when:

- the team is still iterating
- the app is being demoed internally
- desktop packaging is not the main focus yet

How it runs:

- frontend runs with Vite or Tauri dev mode
- backend runs separately with Python
- config stays in the repo-local backend storage folder unless `LINGUASUB_CONFIG_PATH` is set

Commands:

```powershell
cd D:\codetest\LinguaSub
npm.cmd install
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
npm.cmd run backend:dev
npm.cmd run tauri:dev
```

Advantages:

- easiest to debug
- easiest to modify
- no packaging blockers

Tradeoffs:

- user must start the backend separately
- Python must exist on the machine
- FFmpeg must already be installed or added to `PATH`

### 2. Release Delivery Build

Use this when:

- the app needs to be handed to testers or non-technical users
- a desktop installer or zip package is needed
- the backend should ship with the app

Recommended near-term plan:

- build the frontend with Tauri
- package the Python backend separately
- place backend runtime files beside the installed app or inside a runtime folder
- point the app to the packaged backend through a launcher or a fixed local backend URL

This is not yet a one-click all-in-one installer in the repo, but it is a practical release path.

## Frontend Build Steps

1. Install Node dependencies:

```powershell
npm.cmd install
```

2. Build the frontend:

```powershell
npm.cmd run build
```

3. Build the Tauri desktop package:

```powershell
npm.cmd run tauri:build
```

Expected result:

- Tauri creates Windows build artifacts such as an installer or desktop bundle in the Tauri target output folder

Current limitation:

- this requires the Rust and Windows desktop build toolchain on the build machine

## Python Backend Distribution

### Option A: Ship Python Separately

Good for internal demos and developer machines.

What to ship:

- app frontend build
- full project backend folder
- `.venv` creation instructions
- `backend/requirements.txt`

How users run it:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
py -3 backend\run_server.py
```

Pros:

- simplest to maintain
- matches the current repo exactly

Cons:

- Python must be installed on the user machine
- first-run setup is heavier

### Option B: Package the Backend as an Executable

Good for tester delivery and non-technical users.

Suggested tool:

- PyInstaller

Suggested output:

- `linguasub-backend.exe`
- packaged Python runtime files
- model and runtime support files if needed

Suggested command direction:

```powershell
py -m pip install pyinstaller
py -m PyInstaller backend\run_server.py --name linguasub-backend --onefile
```

Pros:

- users do not need Python installed
- easier to distribute with Tauri output

Cons:

- build machine must support PyInstaller packaging
- `faster-whisper` runtime size is larger
- model download behavior still needs testing on the target machine

## Release Directory Structure

A practical Windows release folder can look like this:

```text
LinguaSub-Release/
|-- LinguaSub.exe
|-- runtime/
|   |-- linguasub-backend.exe
|   |-- ffmpeg.exe
|   `-- README-runtime.txt
|-- config/
|   `-- app-config.json   # optional, better stored in %APPDATA%\LinguaSub
`-- logs/
```

Alternative installer-oriented layout:

```text
Program Files/
`-- LinguaSub/
    |-- LinguaSub.exe
    `-- runtime/
        |-- linguasub-backend.exe
        `-- ffmpeg.exe
```

Recommended user data layout:

```text
%APPDATA%\LinguaSub\
|-- app-config.json
|-- logs\
`-- cache\
```

## Config File Path

Current code behavior:

- default development config path: `backend/storage/app-config.json`
- override environment variable: `LINGUASUB_CONFIG_PATH`

Recommended release behavior:

- set `LINGUASUB_CONFIG_PATH=%APPDATA%\LinguaSub\app-config.json`

Why:

- installed apps should not try to write config into `Program Files`
- user settings should survive reinstall and update

## User Data Directory

Recommended Windows user data directory:

- `%APPDATA%\LinguaSub`

Recommended contents:

- provider config
- logs
- cache
- future downloaded models or workflow temp files if needed

Current code now reports both:

- current config path
- recommended release config path

through the startup environment check endpoint.

## Export File Default Save Logic

Current export behavior is already implemented:

- exported file is saved beside the imported source file
- bilingual file name default: `<source>.bilingual.srt`
- single-language file name default: `<source>.single.srt`
- export encoding: `utf-8-sig`
- export refuses to overwrite the imported source file directly

This means export behavior is already safe and understandable for demos.

## FFmpeg Handling

Current code behavior:

- FFmpeg is required for video-to-audio extraction
- if missing, backend returns a clear `FFmpeg was not found on PATH` style error

Release recommendations:

- easiest development path: install FFmpeg system-wide and add it to `PATH`
- better release path: bundle `ffmpeg.exe` inside a runtime folder and ensure the backend can resolve it

Current status:

- missing FFmpeg is already detected by the backend
- startup check now reports whether FFmpeg is available

## faster-whisper Handling

Current code behavior:

- `faster-whisper` is loaded from Python
- if missing, backend returns a clear install hint
- model loading and download failures already return separate errors

Release recommendations:

- development mode: `py -m pip install -r backend\requirements.txt`
- release mode: include `faster-whisper` in the packaged backend runtime
- test model download once on a clean machine before external delivery

Current status:

- missing `faster-whisper` is already detected by the backend
- startup check now reports whether it is available

## First Start Check Logic

Current implemented first-start logic:

1. frontend calls `GET /environment/check`
2. backend returns:
   - runtime mode
   - current config path
   - recommended Windows user data path
   - dependency status for FFmpeg and `faster-whisper`
   - whether the active provider has an API key
   - whether SRT and media workflows are ready
   - warnings and next actions
3. frontend shows this report on the Import page

This gives testers a clear answer before they start:

- can SRT-only flow run now
- can media transcription run now
- is translation configured
- where config should live in a release build

## Missing Dependency Error and Prompt Plan

Already implemented in backend errors:

- missing FFmpeg
- missing `faster-whisper`
- model download failure
- corrupted media
- unsupported file type
- missing translation API key

Recommended frontend messaging pattern:

- show missing FFmpeg as: “Video and audio recognition is unavailable until FFmpeg is installed or bundled.”
- show missing `faster-whisper` as: “Local speech recognition is unavailable until the Python dependency or packaged backend runtime is ready.”
- show missing API key as: “Translation setup is incomplete. Add the provider API key before starting translation.”

Current UI status:

- Import page now shows startup warnings and next actions
- Translation and export pages already show clear backend error messages

## Manual Deployment Plan

If full installer automation is not ready, the team can still deliver a working Windows package:

1. Build the frontend with Tauri.
2. Package or prepare the backend.
3. Bundle `ffmpeg.exe`.
4. Create `%APPDATA%\LinguaSub` on first launch.
5. Set `LINGUASUB_CONFIG_PATH` to `%APPDATA%\LinguaSub\app-config.json`.
6. Launch the backend first.
7. Launch the desktop frontend.

That is enough for a demoable and handoff-friendly Windows release.

## Recommended Next Packaging Task

The next practical engineering step after this repo state is:

- teach the Tauri shell to launch and monitor the packaged backend automatically

That would convert the current “deliverable with separate backend runtime” plan into a smoother desktop product.

## What Was Verified in This Workspace

Verified locally in this repo:

- frontend lint
- frontend production build
- backend unit tests
- backend compile check
- startup environment check endpoint

Not verified in this workspace:

- actual `tauri build` output
- actual Windows installer generation
- packaged backend executable generation

Those still require the matching build tools on the local machine.
