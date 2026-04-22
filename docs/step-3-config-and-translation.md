# Step 3: Config System and Translation Service

## What This Step Adds

- Local JSON config storage in Python
- Config APIs: `loadConfig()`, `saveConfig()`, `updateConfig()`
- Provider adapter structure for OpenAI-compatible APIs and DeepSeek
- Batch subtitle translation through `translateSegments(segments, config)`
- TypeScript service functions that call the Python backend

## Python Modules

- `backend/app/config_service.py`
- `backend/app/translation_service.py`
- `backend/app/server.py`
- `backend/run_server.py`

## TypeScript Modules

- `src/services/configService.ts`
- `src/services/translationService.ts`
- `src/examples/step3ClientExample.ts`

## How Config Storage Works

Config is stored in a local JSON file:

`backend/storage/app-config.json`

If the file does not exist yet, `loadConfig()` creates a default config automatically.

### Available config operations

- `loadConfig()`: Read local config from JSON.
- `saveConfig()`: Save a full config object.
- `updateConfig()`: Update part of the config and keep the rest unchanged.

## Provider Adapter Design

The translation layer uses an adapter base class:

- `TranslationProviderAdapter`
- `ChatCompletionTranslationAdapter`
- `OpenAICompatibleAdapter`
- `DeepSeekAdapter`

This keeps provider-specific details isolated, so later providers can be added without changing the main translation flow.

## Translation Flow

`translateSegments(segments, config)` works like this:

1. Read the active provider from `config.defaultProvider`
2. Pick the matching provider adapter
3. Split subtitle segments into smaller batches
4. Send each batch to `/chat/completions`
5. Ask the model to return JSON only
6. Parse the JSON and write `translatedText` back into each segment

## Prompt Rules Used by the Service

The Python prompt tells the model to:

- preserve the original meaning
- output concise and natural subtitle text
- avoid explanations or notes
- keep subtitle length moderate
- return JSON only

## TypeScript Call Example

```ts
import { loadConfig, updateConfig } from '../services/configService'
import { translateSegments } from '../services/translationService'

const config = await loadConfig()

await updateConfig({
  defaultProvider: 'deepseek',
  outputMode: 'bilingual',
})

const translated = await translateSegments(
  [
    {
      id: 'seg-001',
      start: 0,
      end: 2100,
      sourceText: 'Hello, everyone.',
      translatedText: '',
      sourceLanguage: 'en',
      targetLanguage: 'zh-CN',
    },
  ],
  config,
)
```

## Example Input and Output

See:

- `examples/translation-service.example.json`

## Running the Python Backend

```powershell
cd D:\codetest\LinguaSub
py -3 backend\run_server.py
```

Then the frontend services can call:

- `GET http://127.0.0.1:8765/config`
- `PUT http://127.0.0.1:8765/config`
- `PATCH http://127.0.0.1:8765/config`
- `POST http://127.0.0.1:8765/translate`

## Notes About the APIs

- OpenAI Chat Completions accepts `POST /v1/chat/completions` with `messages` and `model`. Source: OpenAI API Reference, Chat Completions.
- DeepSeek documents `POST /chat/completions` and notes that `https://api.deepseek.com/v1` is also supported as an OpenAI-compatible base URL. Source: DeepSeek API Docs, Your First API Call and Create Chat Completion.
- DeepSeek JSON Output requires `response_format: {"type": "json_object"}` and prompt instructions that explicitly ask for JSON. Source: DeepSeek API Docs, JSON Output.

## Current Limits

- Real translation requests still need a valid API key from the user.
- This step provides a local HTTP backend, but it is not yet wired into a Tauri native command.
- Retry and richer logging can be added later if we want stronger production behavior.
