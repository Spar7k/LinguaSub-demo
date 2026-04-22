"""Tencent file-async ASR provider."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from .common import RealtimeSubtitlePiece

TENCENT_FILE_ASYNC_HOST = "asr.tencentcloudapi.com"
TENCENT_FILE_ASYNC_ENDPOINT = f"https://{TENCENT_FILE_ASYNC_HOST}/"
TENCENT_FILE_ASYNC_SERVICE = "asr"
TENCENT_FILE_ASYNC_VERSION = "2019-06-14"
TENCENT_FILE_ASYNC_SOURCE_TYPE_URL = 0
TENCENT_FILE_ASYNC_CHANNEL_NUM = 1
TENCENT_FILE_ASYNC_RES_TEXT_FORMAT = 3
TENCENT_FILE_ASYNC_POLL_INTERVAL_SECONDS = 3.0
TENCENT_FILE_ASYNC_POLL_TIMEOUT_SECONDS = 30 * 60
TENCENT_FILE_ASYNC_TIMEOUT_SECONDS = 60

_RESULT_LINE_RE = re.compile(
    r"^\[\d+:(?P<start>\d+(?:\.\d+)?),\d+:(?P<end>\d+(?:\.\d+)?)\]\s*(?P<text>.+)$"
)


LOGGER = logging.getLogger("linguasub.transcription.tencent_file_async")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[LinguaSub][TencentFileASR] %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


class TencentFileAsyncConfigError(RuntimeError):
    """Raised when Tencent file-async ASR config is incomplete."""


class TencentFileAsyncAsrError(RuntimeError):
    """Raised when Tencent file-async ASR fails."""


@dataclass(slots=True)
class TencentFileAsyncConfig:
    secretId: str
    secretKey: str
    engineModelType: str
    endpoint: str = TENCENT_FILE_ASYNC_ENDPOINT
    pollIntervalSeconds: float = TENCENT_FILE_ASYNC_POLL_INTERVAL_SECONDS
    pollTimeoutSeconds: int = TENCENT_FILE_ASYNC_POLL_TIMEOUT_SECONDS


def build_tencent_file_async_config(
    secret_id: str,
    secret_key: str,
    engine_model_type: str,
) -> TencentFileAsyncConfig:
    normalized_secret_id = str(secret_id).strip()
    normalized_secret_key = str(secret_key).strip()
    normalized_engine = str(engine_model_type).strip() or "16k_zh"

    if not normalized_secret_id:
        raise TencentFileAsyncConfigError(
            "Tencent file ASR needs SecretId."
        )
    if not normalized_secret_key:
        raise TencentFileAsyncConfigError(
            "Tencent file ASR needs SecretKey."
        )
    if not normalized_engine:
        raise TencentFileAsyncConfigError(
            "Tencent file ASR needs engineModelType."
        )

    return TencentFileAsyncConfig(
        secretId=normalized_secret_id,
        secretKey=normalized_secret_key,
        engineModelType=normalized_engine,
    )


def _sha256_hex(data: str | bytes) -> str:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(payload).hexdigest()


def _hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _build_tc3_authorization(
    *,
    action: str,
    body: str,
    timestamp: int,
    config: TencentFileAsyncConfig,
) -> str:
    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
    credential_scope = f"{date}/{TENCENT_FILE_ASYNC_SERVICE}/tc3_request"
    canonical_headers = (
        "content-type:application/json; charset=utf-8\n"
        f"host:{TENCENT_FILE_ASYNC_HOST}\n"
    )
    signed_headers = "content-type;host"
    canonical_request = (
        "POST\n"
        "/\n"
        "\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{_sha256_hex(body)}"
    )
    string_to_sign = (
        "TC3-HMAC-SHA256\n"
        f"{timestamp}\n"
        f"{credential_scope}\n"
        f"{_sha256_hex(canonical_request)}"
    )

    secret_date = _hmac_sha256(
        f"TC3{config.secretKey}".encode("utf-8"),
        date,
    )
    secret_service = _hmac_sha256(secret_date, TENCENT_FILE_ASYNC_SERVICE)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        "TC3-HMAC-SHA256 "
        f"Credential={config.secretId}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )


def _post_tencent_api(
    *,
    action: str,
    payload: dict[str, Any],
    config: TencentFileAsyncConfig,
    timeout_seconds: int = TENCENT_FILE_ASYNC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False)
    timestamp = int(time.time())
    authorization = _build_tc3_authorization(
        action=action,
        body=body,
        timestamp=timestamp,
        config=config,
    )
    http_request = request.Request(
        url=config.endpoint,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": TENCENT_FILE_ASYNC_HOST,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": TENCENT_FILE_ASYNC_VERSION,
        },
    )

    LOGGER.info(
        "Calling Tencent file ASR action=%s engine_model_type=%s endpoint=%s",
        action,
        config.engineModelType,
        config.endpoint,
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise TencentFileAsyncAsrError(
            f"Tencent file ASR action '{action}' failed with HTTP {exc.code}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise TencentFileAsyncAsrError(
            f"Tencent file ASR action '{action}' hit a network error. {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise TencentFileAsyncAsrError(
            f"Tencent file ASR action '{action}' timed out."
        ) from exc

    try:
        payload_json = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise TencentFileAsyncAsrError(
            f"Tencent file ASR action '{action}' returned invalid JSON."
        ) from exc

    if not isinstance(payload_json, dict):
        raise TencentFileAsyncAsrError(
            f"Tencent file ASR action '{action}' returned an unexpected payload."
        )

    response_payload = payload_json.get("Response")
    if not isinstance(response_payload, dict):
        raise TencentFileAsyncAsrError(
            f"Tencent file ASR action '{action}' returned no Response object."
        )

    response_error = response_payload.get("Error")
    if isinstance(response_error, dict):
        error_code = str(response_error.get("Code", "")).strip() or "UnknownError"
        error_message = (
            str(response_error.get("Message", "")).strip() or "Unknown Tencent ASR error."
        )
        request_id = str(response_payload.get("RequestId", "")).strip()
        raise TencentFileAsyncAsrError(
            f"Tencent file ASR action '{action}' failed with {error_code}: {error_message}"
            + (f" request_id={request_id}" if request_id else "")
        )

    return response_payload


def create_tencent_rec_task(
    file_url: str,
    config: TencentFileAsyncConfig,
) -> int:
    normalized_url = str(file_url).strip()
    if not normalized_url:
        raise TencentFileAsyncAsrError("Tencent file ASR needs a non-empty file_url.")

    response_payload = _post_tencent_api(
        action="CreateRecTask",
        payload={
            "EngineModelType": config.engineModelType,
            "ChannelNum": TENCENT_FILE_ASYNC_CHANNEL_NUM,
            "ResTextFormat": TENCENT_FILE_ASYNC_RES_TEXT_FORMAT,
            "SourceType": TENCENT_FILE_ASYNC_SOURCE_TYPE_URL,
            "Url": normalized_url,
        },
        config=config,
    )

    task = response_payload.get("Data")
    if not isinstance(task, dict):
        raise TencentFileAsyncAsrError(
            "Tencent file ASR did not return task data after CreateRecTask."
        )

    task_id = task.get("TaskId")
    try:
        normalized_task_id = int(task_id)
    except (TypeError, ValueError) as exc:
        raise TencentFileAsyncAsrError(
            "Tencent file ASR returned an invalid TaskId after CreateRecTask."
        ) from exc

    LOGGER.info(
        "Tencent file ASR task created task_id=%s engine_model_type=%s",
        normalized_task_id,
        config.engineModelType,
    )
    return normalized_task_id


def describe_tencent_rec_task(
    task_id: int,
    config: TencentFileAsyncConfig,
) -> dict[str, Any]:
    response_payload = _post_tencent_api(
        action="DescribeTaskStatus",
        payload={"TaskId": int(task_id)},
        config=config,
    )

    task_status = response_payload.get("Data")
    if not isinstance(task_status, dict):
        raise TencentFileAsyncAsrError(
            f"Tencent file ASR returned no task status for task_id={task_id}."
        )
    return task_status


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


def _parse_result_detail(result_detail: Any) -> list[RealtimeSubtitlePiece]:
    if not isinstance(result_detail, list):
        return []

    pieces: list[RealtimeSubtitlePiece] = []
    seen: set[tuple[int, int, str]] = set()
    for index, item in enumerate(result_detail, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("FinalSentence", "")).strip()
        start_ms = _coerce_milliseconds(item.get("StartMs"))
        end_ms = _coerce_milliseconds(item.get("EndMs"))
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
    return pieces


def _parse_result_text(result_text: Any) -> list[RealtimeSubtitlePiece]:
    if not isinstance(result_text, str):
        return []

    pieces: list[RealtimeSubtitlePiece] = []
    seen: set[tuple[int, int, str]] = set()
    for raw_line in result_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _RESULT_LINE_RE.match(line)
        if not match:
            continue
        text = match.group("text").strip()
        if not text:
            continue
        start_ms = int(round(float(match.group("start")) * 1000))
        end_ms = max(int(round(float(match.group("end")) * 1000)), start_ms + 1)
        dedupe_key = (start_ms, end_ms, text)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        pieces.append(
            RealtimeSubtitlePiece(
                index=len(pieces) + 1,
                startMs=start_ms,
                endMs=end_ms,
                text=text,
            )
        )
    return pieces


def parse_tencent_file_async_result(task_status: dict[str, Any]) -> list[RealtimeSubtitlePiece]:
    pieces = _parse_result_detail(task_status.get("ResultDetail"))
    if pieces:
        return pieces

    pieces = _parse_result_text(task_status.get("Result"))
    if pieces:
        return pieces

    raise TencentFileAsyncAsrError(
        "Tencent file ASR finished, but it did not return any usable sentence timestamps."
    )


def poll_tencent_rec_task(
    task_id: int,
    config: TencentFileAsyncConfig,
) -> dict[str, Any]:
    deadline = time.time() + max(config.pollTimeoutSeconds, 30)
    last_status = ""

    while True:
        task_status = describe_tencent_rec_task(task_id, config)
        status = int(task_status.get("Status", -1))
        status_str = str(task_status.get("StatusStr", "")).strip().lower()
        if status_str:
            last_status = status_str

        if status == 2 or status_str == "success":
            LOGGER.info("Tencent file ASR task finished task_id=%s status=%s", task_id, status_str or status)
            return task_status
        if status == 3 or status_str == "failed":
            error_message = str(task_status.get("ErrorMsg", "")).strip() or "Tencent file ASR task failed."
            raise TencentFileAsyncAsrError(
                f"Tencent file ASR task failed task_id={task_id}. {error_message}"
            )

        if time.time() >= deadline:
            raise TencentFileAsyncAsrError(
                f"Tencent file ASR task timed out while polling task_id={task_id}. "
                f"last_status={last_status or status}"
            )

        time.sleep(max(config.pollIntervalSeconds, 1.0))


def transcribe_with_tencent_file_async(
    *,
    file_url: str,
    config: TencentFileAsyncConfig,
) -> list[RealtimeSubtitlePiece]:
    task_id = create_tencent_rec_task(file_url, config)
    task_status = poll_tencent_rec_task(task_id, config)
    return parse_tencent_file_async_result(task_status)
