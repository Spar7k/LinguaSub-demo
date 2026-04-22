# Step 7 - Translation Flow Integration

## What This Step Adds

Step 7 connects the existing backend modules into one front-end workflow:

1. Import video, audio, or SRT
2. Prepare subtitle segments
3. Send subtitle segments to the translation service
4. Write the translated result back into `SubtitleSegment.translatedText`
5. Move the project into preview

## Front-End Flow

The main orchestration now lives in:

- `src/App.tsx`
- `src/components/TranslationWorkspace.tsx`
- `src/components/SubtitlePreviewWorkspace.tsx`

New front-end backend callers:

- `src/services/transcriptionService.ts`
- `src/services/srtService.ts`
- `src/services/translationService.ts`
- `src/services/backendClient.ts`

## How The Flow Works

### Video or audio route

1. Step 4 import returns `route="recognition"`.
2. Step 7 calls `POST /transcribe`.
3. The transcription response becomes `ProjectState.segments`.
4. Step 7 then calls `POST /translate`.
5. The translation response replaces `ProjectState.segments` with updated `translatedText`.
6. `ProjectState.status` moves to `"done"`.

### SRT route

1. Step 4 import returns `route="translation"`.
2. Step 7 calls `POST /srt/parse`.
3. The parsed SRT segments become `ProjectState.segments`.
4. Step 7 then calls `POST /translate`.
5. The translation response writes translated text back into each segment.
6. `ProjectState.status` moves to `"done"`.

## ProjectState Integration

Current state transitions:

- `idle`
- `transcribing`
- `translating`
- `done`
- `error`

Typical media flow:

```json
{
  "currentFile": {
    "path": "D:/videos/interview.mp4",
    "name": "interview.mp4",
    "mediaType": "video",
    "extension": ".mp4",
    "requiresAsr": true
  },
  "segments": [
    {
      "id": "seg-001",
      "start": 0,
      "end": 1840,
      "sourceText": "Hello everyone, welcome to LinguaSub.",
      "translatedText": "[CN] Hello everyone, welcome to LinguaSub.",
      "sourceLanguage": "en",
      "targetLanguage": "zh-CN"
    }
  ],
  "status": "done",
  "error": null
}
```

## Translation Settings UI

The translation page now supports:

- Provider selection
- Model selection
- Output mode selection
- Start translation
- Reload saved config

When translation succeeds, the app automatically opens the preview page.

## Error Handling

The front end now surfaces backend errors through `ProjectState.error` and the task status card.

Examples:

- missing API key
- missing FFmpeg
- missing `faster-whisper`
- invalid SRT file
- provider API failure

On error:

- `ProjectState.status = "error"`
- `ProjectState.error = "clear backend error message"`

## Example Data

See:

- `examples/translation-flow.example.json`

## Verification

```powershell
npm.cmd run lint
npm.cmd run build
py -3 -m compileall backend\app backend\tests backend\run_server.py
py -3 -m unittest discover -s backend/tests -p "test_*.py"
```
