"""Small local HTTP API for config and translation."""

from __future__ import annotations

import json
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config_service import load_config, save_config, update_config
from .environment_service import build_startup_check
from .import_service import (
    FileNotFoundImportError,
    ImportServiceError,
    UnsupportedFileTypeError,
    import_file,
)
from .models import AppConfig, SubtitleSegment
from .export_service import ExportServiceError, export_subtitles
from .srt_service import (
    SrtServiceError,
    generate_srt,
    parse_srt,
)
from .transcription_service import (
    CloudTranscriptionApiError,
    CloudTranscriptionConfigError,
    CloudTranscriptionFileTooLargeError,
    CorruptedMediaError,
    FfmpegNotFoundError,
    FasterWhisperNotInstalledError,
    SpeechModelNotDownloadedError,
    TranscriptionServiceError,
    UnsupportedTranscriptionMediaError,
    transcribe_media,
    validate_speech_config,
)
from .speech_runtime_service import (
    SpeechModelCleanupError,
    SpeechModelDownloadConflictError,
    SpeechModelStorageValidationError,
    SpeechRuntimeError,
    cleanup_downloaded_models,
    start_model_download,
)
from .translation_service import (
    TranslationServiceError,
    translate_segments,
    validate_translation_config,
)
from .task_history_service import (
    TaskHistoryError,
    load_task_history,
    upsert_task_history_record,
)


class LinguaSubRequestHandler(BaseHTTPRequestHandler):
    server_version = "LinguaSubHTTP/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({}, status=HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/health":
                self._send_json({"ok": True})
                return

            if self.path == "/config":
                config = load_config()
                self._send_json(config.to_dict())
                return

            if self.path == "/environment/check":
                report = build_startup_check()
                self._send_json(report.to_dict())
                return

            if self.path == "/tasks":
                history = load_task_history()
                self._send_json(
                    {
                        "tasks": [item.to_dict() for item in history],
                        "count": len(history),
                    }
                )
                return

            self._send_error_json(HTTPStatus.NOT_FOUND, "Route not found.")
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self._handle_unexpected_error(exc)

    def do_PUT(self) -> None:  # noqa: N802
        try:
            if self.path != "/config":
                self._send_error_json(HTTPStatus.NOT_FOUND, "Route not found.")
                return

            try:
                payload = self._read_json_body()
                config = save_config(AppConfig.from_dict(payload))
            except (KeyError, TypeError, ValueError) as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return

            self._send_json(config.to_dict())
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self._handle_unexpected_error(exc)

    def do_PATCH(self) -> None:  # noqa: N802
        try:
            if self.path != "/config":
                self._send_error_json(HTTPStatus.NOT_FOUND, "Route not found.")
                return

            try:
                payload = self._read_json_body()
                config = update_config(payload)
            except (KeyError, TypeError, ValueError) as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return

            self._send_json(config.to_dict())
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self._handle_unexpected_error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/import":
                self._handle_import()
                return

            if self.path == "/config/validate":
                self._handle_config_validate()
                return

            if self.path in {
                "/config/validate-speech",
                "/config/validateSpeech",
                "/speech/config/validate",
            }:
                self._handle_speech_config_validate()
                return

            if self.path == "/transcribe":
                self._handle_transcribe()
                return

            if self.path == "/speech/models/download":
                self._handle_speech_model_download()
                return

            if self.path == "/speech/models/cleanup":
                self._handle_speech_model_cleanup()
                return

            if self.path == "/tasks/upsert":
                self._handle_task_history_upsert()
                return

            if self.path == "/srt/parse":
                self._handle_srt_parse()
                return

            if self.path == "/srt/generate":
                self._handle_srt_generate()
                return

            if self.path == "/export":
                self._handle_export()
                return

            if self.path != "/translate":
                if self.path.startswith("/config/validate") or self.path.startswith(
                    "/speech/config/validate"
                ):
                    self._send_error_json(
                        HTTPStatus.NOT_FOUND,
                        f"本地测试接口不存在：{self.path}。请确认 LinguaSub 后端已更新到最新版本。",
                    )
                    return

                self._send_error_json(HTTPStatus.NOT_FOUND, "Route not found.")
                return

            try:
                payload = self._read_json_body()
                config = AppConfig.from_dict(payload["config"])
                segments = [
                    SubtitleSegment.from_dict(item) for item in payload.get("segments", [])
                ]
                timeout_seconds = int(payload.get("timeoutSeconds", 40))
                batch_size = int(payload.get("batchSize", 20))
            except (KeyError, TypeError, ValueError) as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return

            try:
                result = translate_segments(
                    segments=segments,
                    config=config,
                    timeout_seconds=timeout_seconds,
                    batch_size=batch_size,
                )
            except TranslationServiceError as exc:
                self._send_error_json(HTTPStatus.BAD_GATEWAY, str(exc))
                return

            self._send_json(
                {
                    "segments": [segment.to_dict() for segment in result.segments],
                    "provider": result.provider,
                    "model": result.model,
                    "baseUrl": result.baseUrl,
                    "status": "done",
                }
            )
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self._handle_unexpected_error(exc)

    def _handle_import(self) -> None:
        try:
            payload = self._read_json_body()
            file_path = str(payload["path"])
            result = import_file(file_path)
        except FileNotFoundImportError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
            return
        except UnsupportedFileTypeError as exc:
            self._send_error_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, str(exc))
            return
        except ImportServiceError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(result.to_dict())

    def _handle_config_validate(self) -> None:
        try:
            payload = self._read_json_body()
            config_payload = payload.get("config", payload)
            config = AppConfig.from_dict(config_payload)
            timeout_seconds = int(payload.get("timeoutSeconds", 20))
            result = validate_translation_config(
                config=config,
                timeout_seconds=timeout_seconds,
            )
        except TranslationServiceError as exc:
            self._send_error_json(HTTPStatus.BAD_GATEWAY, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(
            {
                "ok": result.ok,
                "provider": result.provider,
                "model": result.model,
                "baseUrl": result.baseUrl,
                "message": result.message,
            }
        )

    def _handle_speech_config_validate(self) -> None:
        try:
            payload = self._read_json_body()
            config_payload = payload.get("config", payload)
            config = AppConfig.from_dict(config_payload)
            timeout_seconds = int(payload.get("timeoutSeconds", 20))
            provider = config.speechProvider or config.defaultTranscriptionProvider
            if provider == "baidu_realtime":
                detected_base_url = "wss://vop.baidu.com/realtime_asr"
                detected_model = config.baiduDevPid.strip() or "<missing>"
            elif provider == "tencent_realtime":
                detected_base_url = (
                    f"wss://asr.cloud.tencent.com/asr/v2/{config.tencentAppId.strip()}"
                    if config.tencentAppId.strip()
                    else "wss://asr.cloud.tencent.com/asr/v2/<appid>"
                )
                detected_model = config.tencentEngineModelType.strip() or "<missing>"
            else:
                detected_base_url = config.speechBaseUrl.strip() or "<missing>"
                detected_model = config.speechModel.strip() or "<missing>"
            print(
                "[LinguaSub][Settings] local_speech_validate "
                f"route={self.path} "
                f"provider={provider} "
                f"base_url={detected_base_url} "
                f"model={detected_model}"
            )
            result = validate_speech_config(
                config=config,
                timeout_seconds=timeout_seconds,
            )
        except (CloudTranscriptionConfigError, CloudTranscriptionApiError) as exc:
            self._send_error_json(HTTPStatus.BAD_GATEWAY, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(
            {
                "ok": result.ok,
                "provider": result.provider,
                "model": result.model,
                "baseUrl": result.baseUrl,
                "message": result.message,
            }
        )

    def _handle_transcribe(self) -> None:
        try:
            payload = self._read_json_body()
            file_path = str(payload["path"])
            language = payload.get("language")
            model_size = str(payload.get("modelSize", "small"))
            quality_preset = str(payload.get("qualityPreset", "balanced"))
            provider = payload.get("provider")
            config_payload = payload.get("config")
            config = AppConfig.from_dict(config_payload) if isinstance(config_payload, dict) else None
            result = transcribe_media(
                file_path=file_path,
                language=language,
                model_size=model_size,
                quality_preset=quality_preset,
                provider=provider,
                config=config,
            )
        except UnsupportedTranscriptionMediaError as exc:
            self._send_error_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, str(exc))
            return
        except CloudTranscriptionConfigError as exc:
            self._send_error_json(HTTPStatus.PRECONDITION_FAILED, str(exc))
            return
        except CloudTranscriptionFileTooLargeError as exc:
            self._send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, str(exc))
            return
        except CloudTranscriptionApiError as exc:
            self._send_error_json(HTTPStatus.BAD_GATEWAY, str(exc))
            return
        except (FfmpegNotFoundError, FasterWhisperNotInstalledError) as exc:
            self._send_error_json(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        except SpeechModelNotDownloadedError as exc:
            self._send_error_json(HTTPStatus.PRECONDITION_FAILED, str(exc))
            return
        except (CorruptedMediaError, TranscriptionServiceError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(
            {
                "segments": [segment.to_dict() for segment in result.segments],
                "count": len(result.segments),
                "sourceLanguage": result.sourceLanguage,
                "provider": result.provider,
                "mode": result.mode,
                "model": result.model,
                "baseUrl": result.diagnostics.providerBaseUrl,
                "qualityPreset": result.qualityPreset,
                "diagnostics": result.diagnostics.to_dict(),
                "status": "done",
            }
        )

    def _handle_speech_model_download(self) -> None:
        try:
            payload = self._read_json_body()
            model_size = str(payload.get("modelSize", "small"))
            storage_path_raw = payload.get("storagePath")
            storage_path = None if storage_path_raw in (None, "") else str(storage_path_raw)
            remember_storage_path = bool(payload.get("rememberStoragePath", True))
            status = start_model_download(
                model_size=model_size,
                storage_path=storage_path,
                remember_storage_path=remember_storage_path,
            )
        except SpeechModelDownloadConflictError as exc:
            self._send_error_json(HTTPStatus.CONFLICT, str(exc))
            return
        except SpeechModelStorageValidationError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except SpeechRuntimeError as exc:
            self._send_error_json(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(status.to_dict())

    def _handle_speech_model_cleanup(self) -> None:
        try:
            result = cleanup_downloaded_models()
        except SpeechModelCleanupError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except SpeechRuntimeError as exc:
            self._send_error_json(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return

        self._send_json(result.to_dict())

    def _handle_task_history_upsert(self) -> None:
        try:
            payload = self._read_json_body()
            task_payload = payload.get("task", payload)
            if not isinstance(task_payload, dict):
                raise ValueError("Task payload must be an object.")
            result = upsert_task_history_record(task_payload)
        except TaskHistoryError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(result.to_dict())

    def _handle_srt_parse(self) -> None:
        try:
            payload = self._read_json_body()
            file_path = str(payload["path"])
            source_language = payload.get("sourceLanguage", "auto")
            target_language = payload.get("targetLanguage", "zh-CN")
            segments = parse_srt(
                file_path=file_path,
                source_language=source_language,
                target_language=target_language,
            )
        except SrtServiceError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(
            {
                "segments": [segment.to_dict() for segment in segments],
                "count": len(segments),
            }
        )

    def _handle_srt_generate(self) -> None:
        try:
            payload = self._read_json_body()
            segments = [
                SubtitleSegment.from_dict(item) for item in payload.get("segments", [])
            ]
            bilingual = bool(payload.get("bilingual", True))
            content = generate_srt(segments=segments, bilingual=bilingual)
        except SrtServiceError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(
            {
                "content": content,
                "count": len(segments),
                "bilingual": bilingual,
            }
        )

    def _handle_export(self) -> None:
        try:
            payload = self._read_json_body()
            segments = [
                SubtitleSegment.from_dict(item) for item in payload.get("segments", [])
            ]
            export_format = str(payload.get("format", "srt"))
            bilingual = bool(payload.get("bilingual", True))
            word_mode = str(payload.get("wordMode", "bilingualTable"))
            source_file_path = payload.get("sourceFilePath")
            file_name = payload.get("fileName")
            result = export_subtitles(
                segments=segments,
                export_format=export_format,
                bilingual=bilingual,
                word_mode=word_mode,
                source_file_path=source_file_path,
                file_name=file_name,
            )
        except (ExportServiceError, SrtServiceError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self._send_json(
            {
                **result.to_dict(),
                "status": "done",
            }
        )

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")

        if not raw_body:
            return {}

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")

        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = b""
        if status != HTTPStatus.NO_CONTENT:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,PUT,PATCH,POST,OPTIONS")
        self.end_headers()

        if status != HTTPStatus.NO_CONTENT:
            self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _handle_unexpected_error(self, exc: Exception) -> None:
        traceback.print_exc()
        self._send_error_json(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "LinguaSub backend hit an unexpected error while processing this request.",
        )

    def log_message(self, format: str, *args: Any) -> None:
        # Keep server output tidy during local development.
        return


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), LinguaSubRequestHandler)
    print(f"LinguaSub backend listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
