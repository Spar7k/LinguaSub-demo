This folder is bundled into the Windows installer as the LinguaSub runtime resource directory.

Expected layout:

runtime/
`-- ffmpeg/
    |-- ffmpeg.exe
    `-- ffprobe.exe

Place the Windows FFmpeg and FFprobe binaries at:

- `src-tauri/resources/runtime/ffmpeg/ffmpeg.exe`
- `src-tauri/resources/runtime/ffmpeg/ffprobe.exe`

before running the release packaging flow.
