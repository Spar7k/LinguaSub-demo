"""Baidu file-async ASR provider."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from .common import RealtimeSubtitlePiece

BAIDU_FILE_ASYNC_TOKEN_ENDPOINT = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_FILE_ASYNC_CREATE_ENDPOINT = "https://aip.baidubce.com/rpc/2.0/aasr/v1/create"
BAIDU_FILE_ASYNC_QUERY_ENDPOINT = "https://aip.baidubce.com/rpc/2.0/aasr/v1/query"
BAIDU_FILE_ASYNC_SAMPLE_RATE = 16000
BAIDU_FILE_ASYNC_CHANNEL = 1
BAIDU_FILE_ASYNC_POLL_INTERVAL_SECONDS = 3.0
BAIDU_FILE_ASYNC_POLL_TIMEOUT_SECONDS = 30 * 60
BAIDU_FILE_ASYNC_TIMEOUT_SECONDS = 60
BAIDU_FILE_ASYNC_SPEECH_URL_EXPIRES_SECONDS = 24 * 60 * 60

BAIDU_FILE_ASYNC_SUCCESS_STATES = {
    "success",
    "succeeded",
    "done",
    "finished",
    "complete",
    "completed",
}
BAIDU_FILE_ASYNC_FAILURE_STATES = {
    "fail",
    "failed",
    "error",
    "cancelled",
    "canceled",
}


LOGGER = logging.getLogger("linguasub.transcription.baidu_file_async")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[LinguaSub][BaiduFileASR] %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


class BaiduFileAsyncConfigError(RuntimeError):
    """Raised when Baidu file-async ASR config is incomplete."""


class BaiduFileAsyncAsrError(RuntimeError):
    """Raised when Baidu file-async ASR fails."""


@dataclass(slots=True)
class BaiduFileAsyncConfig:
    appId: str
    apiKey: str
    secretKey: str
    devPid: str
    tokenEndpoint: str = BAIDU_FILE_ASYNC_TOKEN_ENDPOINT
    createEndpoint: str = BAIDU_FILE_ASYNC_CREATE_ENDPOINT
    queryEndpoint: str = BAIDU_FILE_ASYNC_QUERY_ENDPOINT
    pollIntervalSeconds: float = BAIDU_FILE_ASYNC_POLL_INTERVAL_SECONDS
    pollTimeoutSeconds: int = BAIDU_FILE_ASYNC_POLL_TIMEOUT_SECONDS
    speechUrlExpiresSeconds: int = BAIDU_FILE_ASYNC_SPEECH_URL_EXPIRES_SECONDS


def build_baidu_file_async_config(
    app_id: str,
    api_key: str,
    secret_key: str,
    dev_pid: str,
) -> BaiduFileAsyncConfig:
    normalized_app_id = str(app_id).strip()
    normalized_api_key = str(api_key).strip()
    normalized_secret_key = str(secret_key).strip()
    normalized_dev_pid = str(dev_pid).strip() or "15372"

    if not normalized_api_key:
        raise BaiduFileAsyncConfigError("Baidu file ASR needs API Key.")
    if not normalized_secret_key:
        raise BaiduFileAsyncConfigError("Baidu file ASR needs SecretKey.")
    if not normalized_dev_pid:
        raise BaiduFileAsyncConfigError("Baidu file ASR needs devPid.")

    return BaiduFileAsyncConfig(
        appId=normalized_app_id,
        apiKey=normalized_api_key,
        secretKey=normalized_secret_key,
        devPid=normalized_dev_pid,
    )


def _post_json(
    *,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int = BAIDU_FILE_ASYNC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise BaiduFileAsyncAsrError(
            f"Baidu file ASR request failed with HTTP {exc.code}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise BaiduFileAsyncAsrError(
            f"Baidu file ASR request hit a network error. {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise BaiduFileAsyncAsrError("Baidu file ASR request timed out.") from exc

    try:
        payload_json = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise BaiduFileAsyncAsrError(
            "Baidu file ASR returned invalid JSON."
        ) from exc

    if not isinstance(payload_json, dict):
        raise BaiduFileAsyncAsrError(
            "Baidu file ASR returned an unexpected payload."
        )
    return payload_json


def fetch_baidu_access_token(
    config: BaiduFileAsyncConfig,
    *,
    timeout_seconds: int = BAIDU_FILE_ASYNC_TIMEOUT_SECONDS,
) -> str:
    query = parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": config.apiKey,
            "client_secret": config.secretKey,
        }
    )
    token_url = f"{config.tokenEndpoint}?{query}"
    http_request = request.Request(url=token_url, method="POST")

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise BaiduFileAsyncAsrError(
            f"Baidu file ASR token request failed with HTTP {exc.code}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise BaiduFileAsyncAsrError(
            f"Baidu file ASR token request hit a network error. {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise BaiduFileAsyncAsrError(
            "Baidu file ASR token request timed out."
        ) from exc

    try:
        payload_json = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise BaiduFileAsyncAsrError(
            "Baidu file ASR token request returned invalid JSON."
        ) from exc

    if not isinstance(payload_json, dict):
        raise BaiduFileAsyncAsrError(
            "Baidu file ASR token request returned an unexpected payload."
        )

    access_token = str(payload_json.get("access_token", "")).strip()
    if access_token:
        return access_token

    error_description = (
        str(payload_json.get("error_description", "")).strip()
        or str(payload_json.get("error", "")).strip()
        or "missing access_token"
    )
    raise BaiduFileAsyncAsrError(
        f"Baidu file ASR token request failed. {error_description}"
    )


def _guess_baidu_file_format(speech_url: str) -> str:
    lower_url = parse.urlparse(speech_url).path.lower()
    for suffix in (".wav", ".pcm", ".mp3", ".m4a", ".amr"):
        if lower_url.endswith(suffix):
            return suffix.lstrip(".")
    return "m4a"


def create_baidu_file_task(
    speech_url: str,
    config: BaiduFileAsyncConfig,
    access_token: str,
) -> str:
    normalized_speech_url = str(speech_url).strip()
    if not normalized_speech_url:
        raise BaiduFileAsyncAsrError("Baidu file ASR needs a non-empty speech_url.")

    create_url = f"{config.createEndpoint}?access_token={parse.quote(access_token, safe='')}"
    response_payload = _post_json(
        url=create_url,
        payload={
            "speech_url": normalized_speech_url,
            "format": _guess_baidu_file_format(normalized_speech_url),
            "pid": int(config.devPid),
            "rate": BAIDU_FILE_ASYNC_SAMPLE_RATE,
            "channel": BAIDU_FILE_ASYNC_CHANNEL,
        },
    )

    task_id = (
        str(response_payload.get("task_id", "")).strip()
        or str(response_payload.get("taskId", "")).strip()
    )
    if not task_id:
        error_message = (
            str(response_payload.get("error_msg", "")).strip()
            or str(response_payload.get("message", "")).strip()
            or "missing task_id"
        )
        raise BaiduFileAsyncAsrError(
            f"Baidu file ASR task creation failed. {error_message}"
        )

    LOGGER.info(
        "Baidu file ASR task created task_id=%s dev_pid=%s",
        task_id,
        config.devPid,
    )
    return task_id


def query_baidu_file_task(
    task_id: str,
    config: BaiduFileAsyncConfig,
    access_token: str,
) -> dict[str, Any]:
    normalized_task_id = str(task_id).strip()
    if not normalized_task_id:
        raise BaiduFileAsyncAsrError("Baidu file ASR query needs a valid task_id.")

    query_url = f"{config.queryEndpoint}?access_token={parse.quote(access_token, safe='')}"
    response_payload = _post_json(
        url=query_url,
        payload={"task_ids": [normalized_task_id]},
    )
    return response_payload


def _extract_task_info(query_payload: dict[str, Any], task_id: str) -> dict[str, Any]:
    tasks_info = query_payload.get("tasks_info")
    if isinstance(tasks_info, list):
        for item in tasks_info:
            if isinstance(item, dict):
                item_task_id = str(item.get("task_id", "")).strip()
                if not task_id or item_task_id == task_id:
                    return item

    if isinstance(query_payload.get("task_result"), dict):
        return query_payload

    raise BaiduFileAsyncAsrError(
        f"Baidu file ASR query returned no task info for task_id={task_id}."
    )


def _normalize_task_status(task_info: dict[str, Any]) -> str:
    for key in ("task_status", "status", "taskStatus", "task_status_text"):
        value = task_info.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            number = int(value)
            if number == 3:
                return "success"
            if number in {4, -1}:
                return "failed"
            if number in {0, 1, 2}:
                return "running"
            return str(number)
        text = str(value).strip().lower()
        if text:
            return text
    return ""


def poll_baidu_file_task(
    task_id: str,
    config: BaiduFileAsyncConfig,
    access_token: str,
) -> dict[str, Any]:
    deadline = time.time() + max(config.pollTimeoutSeconds, 30)
    last_status = ""

    while True:
        query_payload = query_baidu_file_task(task_id, config, access_token)
        task_info = _extract_task_info(query_payload, task_id)
        status = _normalize_task_status(task_info)
        if status:
            last_status = status

        if status in BAIDU_FILE_ASYNC_SUCCESS_STATES:
            LOGGER.info("Baidu file ASR task finished task_id=%s status=%s", task_id, status)
            return task_info
        if status in BAIDU_FILE_ASYNC_FAILURE_STATES:
            error_message = (
                str(task_info.get("error_msg", "")).strip()
                or str(task_info.get("message", "")).strip()
                or "Baidu file ASR task failed."
            )
            raise BaiduFileAsyncAsrError(
                f"Baidu file ASR task failed task_id={task_id}. {error_message}"
            )

        if time.time() >= deadline:
            raise BaiduFileAsyncAsrError(
                f"Baidu file ASR task timed out while polling task_id={task_id}. "
                f"last_status={last_status or '<unknown>'}"
            )

        time.sleep(max(config.pollIntervalSeconds, 1.0))


def _coerce_milliseconds(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return max(0, int(round(float(value))))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return max(0, int(round(float(stripped))))
        except ValueError:
            return None
    return None


def _extract_text(item: dict[str, Any]) -> str:
    for key in ("res", "text", "result", "sentence", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            joined = "".join(str(part).strip() for part in value if str(part).strip())
            if joined:
                return joined
    return ""


def _extract_timestamps(item: dict[str, Any]) -> tuple[int | None, int | None]:
    start_ms = None
    end_ms = None
    for key in ("begin_time", "start_time", "startTime", "start_ms", "bg"):
        start_ms = _coerce_milliseconds(item.get(key))
        if start_ms is not None:
            break
    for key in ("end_time", "endTime", "end_ms", "ed"):
        end_ms = _coerce_milliseconds(item.get(key))
        if end_ms is not None:
            break
    return start_ms, end_ms


def _collect_sentence_items(payload: Any) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if any(
                key in node
                for key in (
                    "begin_time",
                    "start_time",
                    "start_ms",
                    "res",
                    "sentence",
                    "text",
                )
            ):
                collected.append(node)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return collected


def parse_baidu_file_async_result(task_info: dict[str, Any]) -> list[RealtimeSubtitlePiece]:
    task_result = task_info.get("task_result", task_info)
    sentence_items = _collect_sentence_items(task_result)
    pieces: list[RealtimeSubtitlePiece] = []
    seen: set[tuple[int, int, str]] = set()

    for item in sentence_items:
        text = _extract_text(item)
        start_ms, end_ms = _extract_timestamps(item)
        if not text or start_ms is None or end_ms is None:
            continue
        normalized_end = max(end_ms, start_ms + 1)
        dedupe_key = (start_ms, normalized_end, text)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        pieces.append(
            RealtimeSubtitlePiece(
                index=len(pieces) + 1,
                startMs=start_ms,
                endMs=normalized_end,
                text=text,
            )
        )

    if pieces:
        return pieces

    raise BaiduFileAsyncAsrError(
        "Baidu file ASR finished, but it did not return any usable sentence timestamps."
    )


def transcribe_with_baidu_file_async(
    *,
    speech_url: str,
    config: BaiduFileAsyncConfig,
) -> list[RealtimeSubtitlePiece]:
    access_token = fetch_baidu_access_token(config)
    task_id = create_baidu_file_task(speech_url, config, access_token)
    task_info = poll_baidu_file_task(task_id, config, access_token)
    return parse_baidu_file_async_result(task_info)
