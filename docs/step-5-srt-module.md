# Step 5 - SRT Parse And Export

## Added Files

- `backend/app/srt_service.py`
- `backend/tests/test_srt_service.py`
- `examples/demo-bilingual-output.srt`
- `examples/srt-module.example.json`

## Python API

```python
from backend.app.srt_service import generate_srt, parse_srt

segments = parse_srt("examples/demo-import.srt")
content = generate_srt(segments, bilingual=True)
```

### `parse_srt(file_path)`

- Reads an SRT file from disk.
- Tries several common encodings so imported subtitles are less likely to fail.
- Converts each subtitle block into a `SubtitleSegment`.
- Ignores SRT numbering when building IDs, because numbering in real files is often messy.
- Stores `start` and `end` in milliseconds so the result matches the existing shared model.

### `generate_srt(segments, bilingual=True)`

- Converts a `SubtitleSegment` list back into standard SRT text.
- Always writes standard timeline lines like `00:00:01,000 --> 00:00:03,000`.
- Rebuilds subtitle numbering in order.
- In bilingual mode it writes:

```text
Original line
Translated line
```

- In single mode it writes translated text first, and falls back to source text if translation is empty.

## Error Handling

The module covers these common problems:

- Empty lines between subtitle blocks
- Wrong or unordered subtitle numbers
- Invalid timestamp formats such as `00:00:61,000`
- Invalid time ranges where end time is earlier than start time
- Encoding problems by trying several common subtitle encodings

## ProjectState Integration

This module plugs into the current project flow like this:

1. Step 4 import returns `route="translation"` and `subtitleInput.subtitlePath` for `.srt` files.
2. `parse_srt(subtitlePath)` converts that file into `SubtitleSegment[]`.
3. Put the parsed segments into `ProjectState.segments`.
4. Keep `ProjectState.status = "translating"` while translation runs.
5. After translation finishes, call `generate_srt(project_state.segments, bilingual=True)`.
6. Save the returned string as a new `.srt` file during export.

Example state update after parsing:

```json
{
  "currentFile": {
    "path": "D:/codetest/LinguaSub/examples/demo-import.srt",
    "name": "demo-import.srt",
    "mediaType": "subtitle",
    "extension": ".srt",
    "requiresAsr": false
  },
  "segments": [
    {
      "id": "seg-001",
      "start": 0,
      "end": 2000,
      "sourceText": "Hello, everyone.",
      "translatedText": "",
      "sourceLanguage": "en",
      "targetLanguage": "zh-CN"
    }
  ],
  "status": "translating",
  "error": null
}
```

## HTTP Endpoints

For later front-end integration, the backend now also exposes:

- `POST /srt/parse`
- `POST /srt/generate`

Example request bodies are in `examples/srt-module.example.json`.

## Test Command

```powershell
py -3 -m unittest discover -s backend/tests -p "test_*.py"
```
