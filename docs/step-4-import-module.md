# Step 4: File Import Module

## What This Step Adds

- Frontend import page UI
- Backend `/import` endpoint
- File type detection for video, audio, and SRT
- Project state updates after import
- Placeholder handoff objects for future ASR and SRT parsing

## Supported Files

- Video: `.mp4`, `.mov`, `.mkv`
- Audio: `.mp3`, `.wav`, `.m4a`
- Subtitle: `.srt`

## Import Rules

- If the imported file is `srt`, LinguaSub skips recognition and moves to translation.
- If the imported file is video or audio, LinguaSub moves to recognition first.

## Backend Entry Point

`POST /import`

Request:

```json
{
  "path": "D:/codetest/LinguaSub/examples/demo-import.srt"
}
```

Response includes:

- `currentFile`
- `projectState`
- `workflow`
- `route`
- `shouldSkipTranscription`
- `recognitionInput`
- `subtitleInput`

## State Update Logic

- Subtitle file -> `projectState.status = "translating"`
- Video or audio file -> `projectState.status = "transcribing"`
- Missing file -> backend returns `404`
- Unsupported file type -> backend returns `415`

## Frontend UI

The import page now shows:

- local path input
- supported file types
- imported file summary
- expected workflow preview
- backend handoff preview for later modules

## Example Files

- Demo subtitle: `examples/demo-import.srt`
- Example request/response: `examples/import-module.example.json`
