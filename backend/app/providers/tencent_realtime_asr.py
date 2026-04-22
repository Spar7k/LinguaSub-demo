"""Tencent realtime ASR provider."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import parse

from .common import (
    RealtimeSubtitlePiece,
    iter_binary_chunks,
    load_websocket_module,
    realtime_sleep,
)

TENCENT_REALTIME_ENDPOINT = "wss://asr.cloud.tencent.com"
TENCENT_SAMPLE_RATE = 16000
TENCENT_CHUNK_MS = 200
TENCENT_PCM_BYTES_PER_MS = int(TENCENT_SAMPLE_RATE * 2 / 1000)
TENCENT_CHUNK_SIZE = TENCENT_CHUNK_MS * TENCENT_PCM_BYTES_PER_MS
TENCENT_EXPIRES_AFTER_SECONDS = 60 * 60
TENCENT_FINAL_RECEIVE_TIMEOUT_SECONDS = 1.0
TENCENT_FINAL_RECEIVE_IDLE_LIMIT = 3
TENCENT_HANDSHAKE_TIMEOUT_SECONDS = 1.0
TENCENT_HANDSHAKE_PCM_BYTES = b"\x00" * TENCENT_CHUNK_SIZE
TENCENT_FLUSH_CHUNKS = 3


LOGGER = logging.getLogger("linguasub.transcription.tencent")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[LinguaSub][TencentASR] %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


class TencentRealtimeConfigError(RuntimeError):
    """Raised when Tencent realtime ASR config is incomplete."""


class TencentRealtimeAsrError(RuntimeError):
    """Raised when Tencent realtime ASR fails."""


@dataclass(slots=True)
class TencentRealtimeConfig:
    appId: str
    secretId: str
    secretKey: str
    engineModelType: str
    voiceId: str
    nonce: int
    timestamp: int
    expired: int
    websocketUrl: str


def _build_tencent_path(app_id: str) -> str:
    return f"/asr/v2/{app_id}"


def _build_tencent_query_params(
    config: TencentRealtimeConfig,
) -> list[tuple[str, str]]:
    return [
        ("engine_model_type", config.engineModelType),
        ("expired", str(config.expired)),
        ("nonce", str(config.nonce)),
        ("secretid", config.secretId),
        ("timestamp", str(config.timestamp)),
        ("voice_format", "1"),
        ("voice_id", config.voiceId),
    ]


def _build_tencent_signature_base(path: str, params: list[tuple[str, str]]) -> str:
    return f"asr.cloud.tencent.com{path}?{parse.urlencode(params)}"


def _build_tencent_signature(secret_key: str, signature_base: str) -> str:
    try:
        digest = hmac.new(
            secret_key.encode("utf-8"),
            signature_base.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    except Exception as exc:  # pragma: no cover - defensive
        raise TencentRealtimeAsrError(
            "腾讯实时识别签名生成失败。provider=tencent_realtime"
        ) from exc

    return base64.b64encode(digest).decode("utf-8")


def _build_tencent_websocket_url(
    app_id: str,
    params: list[tuple[str, str]],
    signature: str,
) -> str:
    try:
        path = _build_tencent_path(app_id)
        signed_query = parse.urlencode([*params, ("signature", signature)])
        return f"{TENCENT_REALTIME_ENDPOINT}{path}?{signed_query}"
    except Exception as exc:  # pragma: no cover - defensive
        raise TencentRealtimeAsrError(
            "腾讯实时识别 URL 生成失败。provider=tencent_realtime"
        ) from exc


def build_tencent_realtime_config(
    app_id: str,
    secret_id: str,
    secret_key: str,
    engine_model_type: str,
) -> TencentRealtimeConfig:
    normalized_app_id = str(app_id).strip()
    normalized_secret_id = str(secret_id).strip()
    normalized_secret_key = str(secret_key).strip()
    normalized_engine = str(engine_model_type).strip() or "16k_zh"

    if not normalized_app_id:
        raise TencentRealtimeConfigError("腾讯实时识别需要填写腾讯 AppID。")
    if not normalized_secret_id:
        raise TencentRealtimeConfigError("腾讯实时识别需要填写腾讯 SecretID。")
    if not normalized_secret_key:
        raise TencentRealtimeConfigError("腾讯实时识别需要填写腾讯 SecretKey。")
    if not normalized_engine:
        raise TencentRealtimeConfigError("腾讯实时识别需要填写引擎模型类型。")

    voice_id = uuid.uuid4().hex
    timestamp = int(time.time())
    expired = timestamp + TENCENT_EXPIRES_AFTER_SECONDS
    nonce = random.randint(10_000_000, 99_999_999)

    # Build a temporary config so the query/signature helpers can share one data object.
    config = TencentRealtimeConfig(
        appId=normalized_app_id,
        secretId=normalized_secret_id,
        secretKey=normalized_secret_key,
        engineModelType=normalized_engine,
        voiceId=voice_id,
        nonce=nonce,
        timestamp=timestamp,
        expired=expired,
        websocketUrl="",
    )

    try:
        path = _build_tencent_path(config.appId)
        params = _build_tencent_query_params(config)
        signature_base = _build_tencent_signature_base(path, params)
        signature = _build_tencent_signature(config.secretKey, signature_base)
        config.websocketUrl = _build_tencent_websocket_url(
            config.appId,
            params,
            signature,
        )
    except TencentRealtimeAsrError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise TencentRealtimeAsrError(
            "腾讯实时识别 URL / 签名生成失败。provider=tencent_realtime"
        ) from exc

    return config


def _open_tencent_socket(config: TencentRealtimeConfig, timeout_seconds: int):
    try:
        websocket = load_websocket_module()
        return websocket.create_connection(
            config.websocketUrl,
            timeout=timeout_seconds,
            enable_multithread=True,
        )
    except Exception as exc:  # pragma: no cover - network dependent
        raise TencentRealtimeAsrError(
            f"腾讯实时识别 WebSocket 建连失败。"
            f" provider=tencent_realtime engine_model_type={config.engineModelType} "
            f"url={config.websocketUrl}. {exc}"
        ) from exc


def _try_parse_payload(message: Any) -> dict[str, Any] | None:
    if isinstance(message, bytes):
        try:
            message = message.decode("utf-8", errors="replace")
        except Exception:
            return None

    if not isinstance(message, str):
        return None

    text = message.strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _extract_error_message(payload: dict[str, Any]) -> str | None:
    code = payload.get("code")
    if isinstance(code, (int, float)) and int(code) != 0:
        message = payload.get("message") or payload.get("msg") or "unknown error"
        return f"code={int(code)} message={message}"

    for key in ("message", "msg", "error", "error_msg"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            lowered = value.strip().lower()
            if lowered not in {"ok", "success"}:
                return f"{key}={value.strip()}"

    return None


def _iter_result_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if any(key in payload for key in ("voice_text_str", "start_time", "end_time")):
        return [payload]
    return []


def _extract_text(item: dict[str, Any]) -> str:
    for key in ("voice_text_str", "text", "result_text", "transcript"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _coerce_milliseconds(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            number = float(stripped)
        except ValueError:
            return None
    else:
        return None

    if number <= 0:
        return 0
    # Tencent realtime fields are typically reported in milliseconds. Keep values
    # as-is and normalize them into integers for the shared subtitle pipeline.
    return max(0, int(round(number)))


def _is_final_payload(payload: dict[str, Any], item: dict[str, Any]) -> bool:
    for candidate in (
        item.get("final"),
        payload.get("final"),
        item.get("is_final"),
        payload.get("is_final"),
    ):
        if candidate in (1, "1", True, "true", "True"):
            return True

    slice_type = item.get("slice_type")
    return slice_type in (2, 3, "2", "3")


def _store_piece(
    store: dict[tuple[int, int], str],
    *,
    start_ms: int,
    end_ms: int,
    text: str,
) -> None:
    key = (start_ms, end_ms)
    previous_text = store.get(key, "")
    if len(text) >= len(previous_text):
        store[key] = text


def _build_piece_stores(
    payloads: list[dict[str, Any]],
) -> tuple[dict[tuple[int, int], str], dict[tuple[int, int], str]]:
    final_store: dict[tuple[int, int], str] = {}
    fallback_store: dict[tuple[int, int], str] = {}

    for payload in payloads:
        for item in _iter_result_items(payload):
            text = _extract_text(item)
            if not text:
                continue

            start_ms = _coerce_milliseconds(item.get("start_time"))
            end_ms = _coerce_milliseconds(item.get("end_time"))
            if start_ms is None or end_ms is None:
                continue
            if end_ms <= start_ms:
                end_ms = start_ms + max(TENCENT_CHUNK_MS, 1)

            _store_piece(
                fallback_store,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
            )

            if _is_final_payload(payload, item):
                _store_piece(
                    final_store,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                )

    return final_store, fallback_store


def _stores_to_pieces(
    final_store: dict[tuple[int, int], str],
    fallback_store: dict[tuple[int, int], str],
) -> list[RealtimeSubtitlePiece]:
    source_store = final_store if final_store else fallback_store
    ordered_items = sorted(source_store.items(), key=lambda item: (item[0][0], item[0][1]))

    return [
        RealtimeSubtitlePiece(
            index=index + 1,
            startMs=start_ms,
            endMs=end_ms,
            text=text,
        )
        for index, ((start_ms, end_ms), text) in enumerate(ordered_items)
        if text.strip()
    ]


def _drain_socket_messages(
    socket_connection: Any,
    config: TencentRealtimeConfig,
    payloads: list[dict[str, Any]],
    *,
    timeout_seconds: float,
    idle_limit: int,
    phase_label: str,
) -> None:
    websocket = load_websocket_module()
    idle_count = 0
    socket_connection.settimeout(timeout_seconds)

    while idle_count < idle_limit:
        try:
            message = socket_connection.recv()
        except websocket.WebSocketTimeoutException:
            idle_count += 1
            continue
        except Exception as exc:  # pragma: no cover - network dependent
            raise TencentRealtimeAsrError(
                f"腾讯实时识别在{phase_label}接收结果失败。"
                f" provider=tencent_realtime engine_model_type={config.engineModelType}. {exc}"
            ) from exc

        idle_count = 0
        payload = _try_parse_payload(message)
        if not payload:
            continue
        payloads.append(payload)

        error_message = _extract_error_message(payload)
        if error_message:
            raise TencentRealtimeAsrError(
                f"腾讯实时识别返回错误。"
                f" provider=tencent_realtime engine_model_type={config.engineModelType}. "
                f"{error_message}"
            )


def validate_tencent_realtime_connection(
    config: TencentRealtimeConfig,
    timeout_seconds: int = 20,
) -> None:
    LOGGER.info(
        "Tencent validate start provider=tencent_realtime engine_model_type=%s endpoint=%s",
        config.engineModelType,
        config.websocketUrl,
    )
    socket_connection = _open_tencent_socket(config, timeout_seconds=timeout_seconds)
    websocket = load_websocket_module()
    try:
        try:
            socket_connection.send_binary(TENCENT_HANDSHAKE_PCM_BYTES)
        except Exception as exc:  # pragma: no cover - network dependent
            raise TencentRealtimeAsrError(
                f"腾讯实时识别握手发送失败。"
                f" provider=tencent_realtime engine_model_type={config.engineModelType}. {exc}"
            ) from exc

        # Best-effort: if the service responds immediately with an auth or request
        # error, surface it here so “测试连接”能区分建连和握手后的错误。
        socket_connection.settimeout(TENCENT_HANDSHAKE_TIMEOUT_SECONDS)
        try:
            payload = _try_parse_payload(socket_connection.recv())
        except websocket.WebSocketTimeoutException:
            payload = None

        if payload:
            error_message = _extract_error_message(payload)
            if error_message:
                raise TencentRealtimeAsrError(
                    f"腾讯实时识别最小握手校验失败。"
                    f" provider=tencent_realtime engine_model_type={config.engineModelType}. "
                    f"{error_message}"
                )

        LOGGER.info(
            "Tencent validate finish provider=tencent_realtime engine_model_type=%s endpoint=%s",
            config.engineModelType,
            config.websocketUrl,
        )
    finally:
        try:
            socket_connection.close()
        except Exception:
            pass


def transcribe_with_tencent_realtime(
    pcm_path: Path,
    config: TencentRealtimeConfig,
    timeout_seconds: int = 90,
) -> list[RealtimeSubtitlePiece]:
    LOGGER.info(
        "Tencent websocket start provider=tencent_realtime engine_model_type=%s endpoint=%s voice_id=%s",
        config.engineModelType,
        config.websocketUrl,
        config.voiceId,
    )
    socket_connection = _open_tencent_socket(config, timeout_seconds=timeout_seconds)
    payloads: list[dict[str, Any]] = []

    try:
        for chunk in iter_binary_chunks(pcm_path, TENCENT_CHUNK_SIZE):
            try:
                socket_connection.send_binary(chunk)
            except Exception as exc:  # pragma: no cover - network dependent
                raise TencentRealtimeAsrError(
                    f"腾讯实时识别推流失败。"
                    f" provider=tencent_realtime engine_model_type={config.engineModelType}. {exc}"
                ) from exc

            _drain_socket_messages(
                socket_connection,
                config,
                payloads,
                timeout_seconds=0.1,
                idle_limit=1,
                phase_label="推流阶段",
            )
            realtime_sleep(TENCENT_CHUNK_MS)

        # Send a few silent frames to help the realtime service flush the last
        # final segment without introducing a more complex end-of-stream protocol.
        for _ in range(TENCENT_FLUSH_CHUNKS):
            try:
                socket_connection.send_binary(TENCENT_HANDSHAKE_PCM_BYTES)
            except Exception as exc:  # pragma: no cover - network dependent
                raise TencentRealtimeAsrError(
                    f"腾讯实时识别结束推流失败。"
                    f" provider=tencent_realtime engine_model_type={config.engineModelType}. {exc}"
                ) from exc

            _drain_socket_messages(
                socket_connection,
                config,
                payloads,
                timeout_seconds=0.2,
                idle_limit=1,
                phase_label="收尾阶段",
            )
            realtime_sleep(TENCENT_CHUNK_MS)

        _drain_socket_messages(
            socket_connection,
            config,
            payloads,
            timeout_seconds=TENCENT_FINAL_RECEIVE_TIMEOUT_SECONDS,
            idle_limit=TENCENT_FINAL_RECEIVE_IDLE_LIMIT,
            phase_label="最终结果阶段",
        )
    finally:
        try:
            socket_connection.close()
        except Exception:
            pass

    final_store, fallback_store = _build_piece_stores(payloads)
    pieces = _stores_to_pieces(final_store, fallback_store)
    if not pieces:
        raise TencentRealtimeAsrError(
            "腾讯实时识别未返回可用的最终文本结果。"
            f" provider=tencent_realtime engine_model_type={config.engineModelType}"
        )

    LOGGER.info(
        "Tencent websocket finish provider=tencent_realtime engine_model_type=%s final_pieces=%s",
        config.engineModelType,
        len(pieces),
    )
    return pieces
