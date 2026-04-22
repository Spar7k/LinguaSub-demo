# Step 2: Core Data Models

## Chosen Rule

LinguaSub stores `start` and `end` in milliseconds.

This choice makes later work easier:
- ASR tools usually give timestamps precise to milliseconds.
- SRT export also needs millisecond precision.
- Integers are safer than floating-point seconds when saving and loading JSON.

## TypeScript and Python Files

- Frontend models: `src/types/models.ts`
- Backend models: `backend/app/models.py`
- JSON example: `examples/data-models.example.json`

## 1. SubtitleSegment

Represents one subtitle row with a time range.

- `id`: Unique ID for one subtitle segment. Useful for editing, searching, and re-translation.
- `start`: Start time in milliseconds.
- `end`: End time in milliseconds.
- `sourceText`: Original sentence from ASR or imported SRT.
- `translatedText`: Translated sentence. Empty string means translation is not finished yet.
- `sourceLanguage`: Language of the original text, such as `en`, `ja`, `ko`, or `zh-CN`.
- `targetLanguage`: Language we want to translate into.

## 2. AppConfig

Stores the app-level settings.

- `apiProviders`: A list of saved provider configs. This lets the app remember multiple providers at the same time.
- `defaultProvider`: The provider selected by default.
- `apiKey`: The active provider's API key. This mirrors the selected provider so the settings form is easier to bind.
- `baseUrl`: The active provider's base URL.
- `model`: The active model name.
- `outputMode`: Export style. `bilingual` means two lines per subtitle block. `single` means one line only.

### Nested item inside `apiProviders`

- `provider`: Provider ID, currently `openaiCompatible` or `deepseek`.
- `displayName`: Name shown in the UI.
- `apiKey`: API key for that provider.
- `baseUrl`: Base URL for that provider.
- `model`: Default model for that provider.
- `enabled`: Whether this provider can be used.

## 3. TranslationTask

Represents one translation job.

- `provider`: Which provider should handle this task.
- `model`: Which model should handle this task.
- `sourceLanguage`: Source language for this task.
- `targetLanguage`: Target language for this task.
- `segments`: Subtitle segments waiting to be translated or already translated.
- `status`: Current task state. Step 2 uses `queued`, `translating`, `done`, and `error`.

## 4. ProjectState

Represents the current working project inside the app.

- `currentFile`: The file currently opened by the user. It is `null` before import.
- `segments`: All subtitle segments currently loaded in the editor.
- `status`: Current project phase. Step 2 uses `idle`, `transcribing`, `translating`, and `done`.
- `error`: Error message shown to the user. `null` means there is no error.

### Nested item inside `currentFile`

- `path`: Full local path.
- `name`: File name shown in the UI.
- `mediaType`: `video`, `audio`, or `subtitle`.
- `extension`: File extension like `.mp4` or `.srt`.
- `requiresAsr`: `true` means the app should run ASR first. `false` means it can skip directly to translation.

## How These Models Convert to SRT

Each `SubtitleSegment` becomes one SRT block.

### Conversion steps

1. Sort segments by `start`.
2. Convert `start` and `end` from milliseconds to SRT time format: `HH:MM:SS,mmm`.
3. Write the subtitle index, starting from `1`.
4. Write the time line as `start --> end`.
5. Write subtitle text:
   - If `outputMode` is `bilingual`, write `sourceText` on line 1 and `translatedText` on line 2.
   - If `outputMode` is `single`, write one line only. In most cases this should prefer `translatedText`, and fall back to `sourceText` if translation is empty.
6. Leave one empty line between subtitle blocks.

### Example SRT block

```srt
1
00:00:00,000 --> 00:00:02,430
Hello, everyone.
大家好。
```

## Why This Design Works for Later Steps

- ASR output can directly fill `SubtitleSegment.start`, `SubtitleSegment.end`, and `sourceText`.
- Translation can update `translatedText` in place.
- Subtitle preview can edit one segment at a time by `id`.
- SRT export only needs `segments` plus `outputMode`.
