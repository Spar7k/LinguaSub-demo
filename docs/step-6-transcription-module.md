# Step 6 - Local Transcription With faster-whisper

## Added Files

- `backend/app/transcription_service.py`
- `backend/tests/test_transcription_service.py`
- `examples/transcription-module.example.json`

## Python API

```python
from backend.app.transcription_service import transcribe_media

segments = transcribe_media(
    file_path="D:/videos/interview.mp4",
    language=None,
    model_size="small",
)
```

### `transcribe_media(file_path, language=None, model_size="small")`

- Accepts a local video path or audio path.
- If the input is video, it uses FFmpeg to extract mono 16k audio first.
- If the input is already audio, it sends that file directly to `faster-whisper`.
- Returns a `SubtitleSegment[]` list that matches the shared project model.

Each segment includes:

- `id`
- `start`
- `end`
- `sourceText`
- `translatedText` as an empty string for now
- `sourceLanguage`
- `targetLanguage` defaulting to `zh-CN` so the next translation step can run directly

## Language And Model Options

- Automatic language detection: `language=None` or `language="auto"`
- Manual language: `zh`, `en`, `ja`, `ko`
- Default model: `small`
- Other model names supported by `faster-whisper` can also be passed through `model_size`

Detected Chinese is normalized to `zh-CN` so it stays consistent with the existing shared data model.

## Error Handling

The module returns clear errors for:

- Missing FFmpeg
- Missing `faster-whisper`
- Model download or model preparation failures
- Corrupted or unreadable media files
- Unsupported file types such as `.srt` or `.txt`

## HTTP Endpoint

The local backend now exposes:

- `POST /transcribe`

Example request body:

```json
{
  "path": "D:/videos/interview.mp4",
  "language": null,
  "modelSize": "small"
}
```

## ProjectState Integration

This fits the current flow like this:

1. Step 4 import returns `route="recognition"` for video or audio files.
2. Read `recognitionInput.mediaPath` from the import result.
3. Call `transcribe_media(...)`.
4. Put the returned segments into `ProjectState.segments`.
5. Move `ProjectState.status` from `"transcribing"` to `"translating"`.
6. Pass the segments to the Step 3 translation service.

Example state after recognition:

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
      "translatedText": "",
      "sourceLanguage": "en",
      "targetLanguage": "zh-CN"
    }
  ],
  "status": "translating",
  "error": null
}
```

## Install And Test

Install the Python dependency:

```powershell
py -m pip install -r backend\requirements.txt
```

Install FFmpeg separately and make sure `ffmpeg` is on `PATH`.

Mock-based unit tests:

```powershell
py -3 -m unittest discover -s backend/tests -p "test_*.py"
```

Real manual smoke test after installing FFmpeg and `faster-whisper`:

```python
from backend.app.transcription_service import transcribe_media

segments = transcribe_media("D:/videos/interview.mp4", model_size="small")
print(segments[0].to_dict())
```
