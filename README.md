# LinguaSub

LinguaSub is a Windows desktop subtitle tool for:

- local media transcription with `faster-whisper`
- cloud subtitle translation through OpenAI-compatible providers and DeepSeek
- bilingual subtitle preview, editing, and export

Current stack:

- frontend: Tauri + React + TypeScript
- backend: Python
- media tools: FFmpeg + faster-whisper

## Current Project Status

Implemented in this repo:

- import workflow for video, audio, and SRT
- SRT parsing and SRT export
- Word export with bilingual table and transcript `.docx` output
- local transcription service interface
- translation config and provider adapters
- editable subtitle preview page
- export page with SRT and Word output options
- startup environment check for Windows packaging guidance
- in-app Windows uninstall entry on the Settings page

Still dependent on the local machine:

- Rust and Tauri toolchain for desktop packaging
- FFmpeg and the faster-whisper runtime for development-mode media recognition
- Whisper model download before first local transcription
- a valid translation API key for actual translation requests

## Development Run

1. Install frontend dependencies:

```powershell
cd D:\codetest\LinguaSub
npm.cmd install
```

2. Create the Python environment:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
```

3. Start the backend:

```powershell
npm.cmd run backend:dev
```

4. Start the frontend browser shell:

```powershell
npm.cmd run dev
```

5. Start the Tauri desktop shell after Rust is ready:

```powershell
npm.cmd run tauri:dev
```

## Build Commands

Frontend production build:

```powershell
npm.cmd run build
```

Desktop package build:

```powershell
npm.cmd run tauri:build
```

Current Windows installer target:

- NSIS installer (`-setup.exe`)
- start menu shortcut is kept from Tauri's default installer flow
- desktop shortcut is created automatically after install through `src-tauri/windows/hooks.nsh`
- the installed app can trigger the Windows uninstall flow from the Settings page

Backend tests:

```powershell
py -3 -m unittest discover -s backend/tests -p "test_*.py"
```

## Startup Check

LinguaSub now exposes a local startup report:

- `GET /environment/check`

The report shows:

- current config path
- recommended Windows user data path
- FFmpeg availability
- `faster-whisper` availability
- whether the current default provider has an API key
- whether media workflow and SRT workflow are ready

The import page displays this report directly in the UI.

## Config and User Data

Current development default:

- config file: `backend/storage/app-config.json`

Release recommendation:

- config file: `%APPDATA%\LinguaSub\app-config.json`
- environment variable: `LINGUASUB_CONFIG_PATH`

This keeps user settings outside the app install directory.

## Export Behavior

Default export logic:

- export path: same folder as the imported source file
- default bilingual name: `<source>.bilingual.srt`
- default single-language name: `<source>.single.srt`
- default Word table name: `<source>_bilingual.docx`
- default Word transcript name: `<source>_transcript.docx`
- encoding: `utf-8-sig`

## Windows Packaging

Two practical release paths are documented in:

- [step-10-windows-packaging.md](docs/step-10-windows-packaging.md)

Short version:

- development demo build: run Tauri frontend and Python backend separately
- release delivery build: package the Tauri app and ship a bundled backend runtime folder or a packaged backend executable
- current installer format in this repo: NSIS with a post-install desktop shortcut hook

## Notes

- If `ffmpeg` is missing, video and audio transcription will fail with a clear backend error.
- If `faster-whisper` is missing, local ASR will fail with a clear backend error.
- If the translation provider has no API key, translation will fail until one is configured.
- This repo already contains the workflow, validation, and packaging documentation, but a full one-click Windows installer still depends on the packaging tools available on the target machine.
