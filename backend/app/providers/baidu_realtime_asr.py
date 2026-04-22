"""Baidu realtime ASR websocket provider."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import RealtimeSubtitlePiece, iter_binary_chunks, load_websocket_module, realtime_sleep

BAIDU_REALTIME_ENDPOINT = "wss://vop.baidu.com/realtime_asr"
BAIDU_SAMPLE_RATE = 16000
BAIDU_CHUNK_MS = 160
BAIDU_PCM_BYTES_PER_MS = int(BAIDU_SAMPLE_RATE * 2 / 1000)
BAIDU_CHUNK_SIZE = BAIDU_CHUNK_MS * BAIDU_PCM_BYTES_PER_MS


LOGGER = logging.getLogger("linguasub.transcription.baidu")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[LinguaSub][BaiduASR] %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


class BaiduRealtimeConfigError(RuntimeError):
    """Raised when Baidu realtime ASR config is incomplete."""


class BaiduRealtimeAsrError(RuntimeError):
    """Raised when Baidu realtime ASR fails."""


@dataclass(slots=True)
class BaiduRealtimeConfig:
    appId: str
    apiKey: str
    devPid: str
    cuid: str
    sn: str
    websocketUrl: str


def build_baidu_realtime_config(app_id: str, api_key: str, dev_pid: str, cuid: str) -> BaiduRealtimeConfig:
    normalized_app_id = str(app_id).strip()
    normalized_api_key = str(api_key).strip()
    normalized_dev_pid = str(dev_pid).strip() or "15372"
    normalized_cuid = str(cuid).strip() or "linguasub-desktop"

    if not normalized_app_id:
        raise BaiduRealtimeConfigError("百度实时识别需要填写百度 AppID。")
    if not normalized_api_key:
        raise BaiduRealtimeConfigError("百度实时识别需要填写百度 API Key。")
    if not normalized_dev_pid:
        raise BaiduRealtimeConfigError("百度实时识别需要填写百度识别模型 PID。")
    if not normalized_cuid:
        raise BaiduRealtimeConfigError("百度实时识别需要填写 CUID。")

    sn = uuid.uuid4().hex
    return BaiduRealtimeConfig(
        appId=normalized_app_id,
        apiKey=normalized_api_key,
        devPid=normalized_dev_pid,
        cuid=normalized_cuid,
        sn=sn,
        websocketUrl=f"{BAIDU_REALTIME_ENDPOINT}?sn={sn}",
    )


def _build_start_frame(config: BaiduRealtimeConfig) -> str:
    return json.dumps(
        {
            "type": "START",
            "data": {
                "appid": config.appId,
                "appkey": config.apiKey,
                "dev_pid": config.devPid,
                "cuid": config.cuid,
                "format": "pcm",
                "sample": BAIDU_SAMPLE_RATE,
            },
        },
        ensure_ascii=False,
    )


def _build_finish_frame() -> str:
    return json.dumps({"type": "FINISH"}, ensure_ascii=False)


def _open_baidu_socket(config: BaiduRealtimeConfig, timeout_seconds: int):
    websocket = load_websocket_module()
    try:
        return websocket.create_connection(
            config.websocketUrl,
            timeout=timeout_seconds,
            enable_multithread=True,
        )
    except Exception as exc:  # pragma: no cover - network dependent
        raise BaiduRealtimeAsrError(
            f"无法连接百度实时识别 WebSocket。provider=baidu_realtime dev_pid={config.devPid} url={config.websocketUrl}。{exc}"
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


def _extract_error(payload: dict[str, Any]) -> str | None:
    candidates = [
        ("error_msg", "error_msg"),
        ("error", "error"),
        ("message", "message"),
        ("desc", "desc"),
        ("error_code", "error_code"),
        ("err_no", "err_no"),
    ]
    for key, label in candidates:
        value = payload.get(key)
        if value not in (None, "", 0, "0"):
            return f"{label}={value}"
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_error(data)
    return None


def _extract_text(payload: dict[str, Any]) -> str:
    for key in ("voice_text_str", "best_result", "result", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            joined = "".join(str(item).strip() for item in value if str(item).strip())
            if joined:
                return joined

    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_text(data)

    return ""


def _extract_timestamp(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(round(float(value))))
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_timestamp(data, *keys)
    return None


def _extract_segment_pieces(
    payloads: list[dict[str, Any]],
    fallback_total_duration_ms: int,
) -> list[RealtimeSubtitlePiece]:
    pieces: list[RealtimeSubtitlePiece] = []
    seen_keys: set[tuple[int, int, str]] = set()

    for payload in payloads:
        text = _extract_text(payload)
        if not text:
            continue

        start_ms = _extract_timestamp(payload, "start_time", "startTime", "bg")
        end_ms = _extract_timestamp(payload, "end_time", "endTime", "ed")

        if start_ms is None:
            start_ms = pieces[-1].endMs if pieces else 0
        if end_ms is None or end_ms <= start_ms:
            end_ms = max(start_ms + BAIDU_CHUNK_MS, start_ms + len(text) * 120)

        dedupe_key = (start_ms, end_ms, text)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        pieces.append(
            RealtimeSubtitlePiece(
                index=len(pieces) + 1,
                startMs=start_ms,
                endMs=end_ms,
                text=text,
            )
        )

    if not pieces and payloads:
        joined_text = "".join(_extract_text(payload) for payload in payloads).strip()
        if joined_text:
            pieces.append(
                RealtimeSubtitlePiece(
                    index=1,
                    startMs=0,
                    endMs=max(fallback_total_duration_ms, BAIDU_CHUNK_MS),
                    text=joined_text,
                )
            )

    return pieces


def validate_baidu_realtime_connection(
    config: BaiduRealtimeConfig,
    timeout_seconds: int = 20,
) -> None:
    LOGGER.info(
        "Baidu validate start provider=baidu_realtime dev_pid=%s endpoint=%s",
        config.devPid,
        config.websocketUrl,
    )
    websocket = load_websocket_module()
    socket_connection = _open_baidu_socket(config, timeout_seconds=timeout_seconds)
    try:
        socket_connection.send(_build_start_frame(config))
        try:
            response = socket_connection.recv()
        except websocket.WebSocketTimeoutException:
            response = None

        payload = _try_parse_payload(response)
        if payload:
            error_message = _extract_error(payload)
            if error_message:
                raise BaiduRealtimeAsrError(
                    f"百度实时识别连接失败。provider=baidu_realtime dev_pid={config.devPid} endpoint={config.websocketUrl}。{error_message}"
                )

        socket_connection.send(_build_finish_frame())
        LOGGER.info(
            "Baidu validate finish provider=baidu_realtime dev_pid=%s endpoint=%s",
            config.devPid,
            config.websocketUrl,
        )
    finally:
        try:
            socket_connection.close()
        except Exception:
            pass


def transcribe_with_baidu_realtime(
    pcm_path: Path,
    config: BaiduRealtimeConfig,
    timeout_seconds: int = 90,
) -> list[RealtimeSubtitlePiece]:
    LOGGER.info(
        "Baidu websocket start provider=baidu_realtime dev_pid=%s endpoint=%s",
        config.devPid,
        config.websocketUrl,
    )
    websocket = load_websocket_module()
    socket_connection = _open_baidu_socket(config, timeout_seconds=timeout_seconds)
    payloads: list[dict[str, Any]] = []
    total_duration_ms = 0

    try:
        socket_connection.send(_build_start_frame(config))
        try:
            start_payload = _try_parse_payload(socket_connection.recv())
            if start_payload:
                payloads.append(start_payload)
                error_message = _extract_error(start_payload)
                if error_message:
                    raise BaiduRealtimeAsrError(
                        f"百度实时识别启动失败。provider=baidu_realtime dev_pid={config.devPid} endpoint={config.websocketUrl}。{error_message}"
                    )
        except websocket.WebSocketTimeoutException:
            pass

        for chunk in iter_binary_chunks(pcm_path, BAIDU_CHUNK_SIZE):
            socket_connection.send_binary(chunk)
            total_duration_ms += BAIDU_CHUNK_MS
            realtime_sleep(BAIDU_CHUNK_MS)

            while True:
                try:
                    socket_connection.settimeout(0.1)
                    message = socket_connection.recv()
                except websocket.WebSocketTimeoutException:
                    break

                payload = _try_parse_payload(message)
                if not payload:
                    continue
                payloads.append(payload)
                error_message = _extract_error(payload)
                if error_message:
                    raise BaiduRealtimeAsrError(
                        f"百度实时识别返回错误。provider=baidu_realtime dev_pid={config.devPid} endpoint={config.websocketUrl}。{error_message}"
                    )

        socket_connection.settimeout(timeout_seconds)
        socket_connection.send(_build_finish_frame())

        while True:
            try:
                message = socket_connection.recv()
            except websocket.WebSocketTimeoutException:
                break
            except Exception:
                break

            payload = _try_parse_payload(message)
            if not payload:
                continue
            payloads.append(payload)

            error_message = _extract_error(payload)
            if error_message:
                raise BaiduRealtimeAsrError(
                    f"百度实时识别结束时返回错误。provider=baidu_realtime dev_pid={config.devPid} endpoint={config.websocketUrl}。{error_message}"
                )

            message_type = str(payload.get("type", "")).upper()
            if message_type in {"FIN_TEXT", "FINISH", "FINISHED", "END"}:
                break
    finally:
        try:
            socket_connection.close()
        except Exception:
            pass
        LOGGER.info(
            "Baidu websocket finish provider=baidu_realtime dev_pid=%s endpoint=%s",
            config.devPid,
            config.websocketUrl,
        )

    pieces = _extract_segment_pieces(payloads, total_duration_ms)
    if not pieces:
        raise BaiduRealtimeAsrError(
            "百度实时识别未返回可用结果。请检查音频内容、百度应用配置或稍后重试。"
        )

    return pieces

