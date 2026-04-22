# Step 9: Export Flow

## What Step 9 Adds

Step 9 closes the main workflow:

- Import
- Recognition or SRT parse
- Translation
- Preview and edit
- Export

The export feature now reads the current `ProjectState.segments`, generates SRT text through the existing backend SRT service, and writes the final file to disk.

## Frontend

Main files:

- `src/App.tsx`
- `src/components/ExportWorkspace.tsx`
- `src/services/exportService.ts`

What the frontend now does:

- Adds a real `Export` workspace to the main step flow
- Lets the user choose `bilingual` or `single` export mode
- Lets the user enter a custom file name or leave it empty for auto naming
- Sends the current subtitle list to `POST /export`
- Updates `ProjectState.status` to `exporting`, `done`, or `error`
- Shows clear warnings for empty translations in bilingual mode
- Shows the last exported file path after success

## Backend

Main files:

- `backend/app/export_service.py`
- `backend/app/server.py`
- `backend/app/srt_service.py`

What the backend now does:

- Reuses `generate_srt(...)` to build subtitle content
- Validates that subtitle segments exist before export
- Rejects bilingual export when any `translatedText` is empty
- Rejects invalid file names
- Returns clear errors for invalid time ranges
- Saves the exported file with `utf-8-sig` encoding for Windows-friendly SRT output

## ProjectState and SubtitleSegment Integration

The export module uses the same shared subtitle data structure as the rest of the app:

- `ProjectState.segments` is the only export input
- Every `SubtitleSegment` contributes one SRT block
- `sourceText` is always available for bilingual output
- `translatedText` is required for bilingual output
- In single-language mode, LinguaSub writes `translatedText` first and falls back to `sourceText`

Important behavior:

- Preview edits are exported immediately because export reads the live `ProjectState.segments`
- Export success updates the app status to `done`
- Export failure updates the app status to `error`

## Default Naming

If the user does not enter a file name:

- bilingual: `<source-name>.bilingual.srt`
- single: `<source-name>.single.srt`

The file is saved beside the imported source file.

## Validation Rules

- No segments: export button stays disabled and the backend also rejects the request
- Invalid timeline: backend returns a clear time range error
- Missing translation in bilingual mode: frontend shows a warning and backend rejects the export

## Example API Call

Request:

```json
{
  "segments": [
    {
      "id": "seg-001",
      "start": 1000,
      "end": 3000,
      "sourceText": "Hello there.",
      "translatedText": "你好。",
      "sourceLanguage": "en",
      "targetLanguage": "zh-CN"
    }
  ],
  "bilingual": true,
  "sourceFilePath": "D:\\codetest\\LinguaSub\\examples\\demo-import.srt",
  "fileName": "demo-export"
}
```

Response:

```json
{
  "path": "D:\\codetest\\LinguaSub\\examples\\demo-export.srt",
  "fileName": "demo-export.srt",
  "bilingual": true,
  "count": 1,
  "status": "done"
}
```
