"""iFLYTEK LFASR async ASR provider."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from .common import RealtimeSubtitlePiece

XFYUN_LFASR_BASE_URL = "https://raasr.xfyun.cn/api"
XFYUN_LFASR_PREPARE_ENDPOINT = f"{XFYUN_LFASR_BASE_URL}/prepare"
XFYUN_LFASR_UPLOAD_ENDPOINT = f"{XFYUN_LFASR_BASE_URL}/upload"
XFYUN_LFASR_MERGE_ENDPOINT = f"{XFYUN_LFASR_BASE_URL}/merge"
XFYUN_LFASR_PROGRESS_ENDPOINT = f"{XFYUN_LFASR_BASE_URL}/getProgress"
XFYUN_LFASR_RESULT_ENDPOINT = f"{XFYUN_LFASR_BASE_URL}/getResult"
XFYUN_LFASR_SLICE_SIZE_BYTES = 10 * 1024 * 1024
XFYUN_LFASR_POLL_INTERVAL_SECONDS = 10.0
XFYUN_LFASR_POLL_TIMEOUT_SECONDS = 60 * 60
XFYUN_LFASR_HTTP_TIMEOUT_SECONDS = 120
XFYUN_LFASR_SUCCESS_STATUS = 9
XFYUN_LFASR_RUNNING_STATUSES = {0, 1, 2, 3, 4, 5}
XFYUN_LFASR_MAX_FILE_BYTES = 500 * 1024 * 1024


LOGGER = logging.getLogger("linguasub.transcription.xfyun_lfasr")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[LinguaSub][XfyunLFASR] %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


class XfyunLfasrError(RuntimeError):
    """Base error for iFLYTEK LFASR."""


class XfyunLfasrConfigError(XfyunLfasrError):
    """Raised when iFLYTEK LFASR config is incomplete."""


class XfyunLfasrPrepareError(XfyunLfasrError):
    """Raised when /prepare fails."""


class XfyunLfasrUploadError(XfyunLfasrError):
    """Raised when /upload fails."""


class XfyunLfasrMergeError(XfyunLfasrError):
    """Raised when /merge fails."""


class XfyunLfasrPollingError(XfyunLfasrError):
    """Raised when /getProgress fails or times out."""


class XfyunLfasrResultParseError(XfyunLfasrError):
    """Raised when /getResult returns no usable sentence timestamps."""


@dataclass(slots=True)
class XfyunLfasrConfig:
    appId: str
    secretKey: str
    prepareEndpoint: str = XFYUN_LFASR_PREPARE_ENDPOINT
    uploadEndpoint: str = XFYUN_LFASR_UPLOAD_ENDPOINT
    mergeEndpoint: str = XFYUN_LFASR_MERGE_ENDPOINT
    progressEndpoint: str = XFYUN_LFASR_PROGRESS_ENDPOINT
    resultEndpoint: str = XFYUN_LFASR_RESULT_ENDPOINT
    sliceSizeBytes: int = XFYUN_LFASR_SLICE_SIZE_BYTES
    pollIntervalSeconds: float = XFYUN_LFASR_POLL_INTERVAL_SECONDS
    pollTimeoutSeconds: int = XFYUN_LFASR_POLL_TIMEOUT_SECONDS


def build_xfyun_lfasr_config(
    app_id: str,
    secret_key: str,
) -> XfyunLfasrConfig:
    normalized_app_id = str(app_id).strip()
    normalized_secret_key = str(secret_key).strip()

    if not normalized_app_id:
        raise XfyunLfasrConfigError("XFYUN LFASR needs AppID.")
    if not normalized_secret_key:
        raise XfyunLfasrConfigError("XFYUN LFASR needs SecretKey.")

    return XfyunLfasrConfig(
        appId=normalized_app_id,
        secretKey=normalized_secret_key,
    )


def _build_xfyun_signa(app_id: str, secret_key: str, ts: str) -> str:
    base = f"{app_id}{ts}"
    md5_digest = hashlib.md5(base.encode("utf-8")).hexdigest()
    signature = hmac.new(
        secret_key.encode("utf-8"),
        md5_digest.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(signature).decode("utf-8")


def _build_auth_fields(config: XfyunLfasrConfig) -> dict[str, str]:
    ts = str(int(time.time()))
    signa = _build_xfyun_signa(config.appId, config.secretKey, ts)
    return {
        "app_id": config.appId,
        "ts": ts,
        "signa": signa,
    }


def _parse_common_response(
    response_text: str,
    *,
    error_type: type[XfyunLfasrError],
    action_label: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise error_type(
            f"XFYUN LFASR {action_label} returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise error_type(
            f"XFYUN LFASR {action_label} returned an unexpected payload."
        )

    ok = int(payload.get("ok", -1))
    if ok != 0:
        failed = str(payload.get("failed", "")).strip() or f"{action_label} failed"
        err_no = payload.get("err_no")
        raise error_type(
            f"XFYUN LFASR {action_label} failed with err_no={err_no}. {failed}"
        )

    return payload


def _post_form(
    *,
    url: str,
    fields: dict[str, str],
    error_type: type[XfyunLfasrError],
    action_label: str,
    timeout_seconds: int = XFYUN_LFASR_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    body = parse.urlencode(fields).encode("utf-8")
    http_request = request.Request(
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
    )
    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise error_type(
            f"XFYUN LFASR {action_label} failed with HTTP {exc.code}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise error_type(
            f"XFYUN LFASR {action_label} hit a network error. {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise error_type(f"XFYUN LFASR {action_label} timed out.") from exc

    return _parse_common_response(
        response_text,
        error_type=error_type,
        action_label=action_label,
    )


def _build_multipart_form_data(
    *,
    fields: dict[str, str],
    file_field_name: str,
    file_name: str,
    file_content: bytes,
) -> tuple[bytes, str]:
    boundary = f"----LinguaSubLFASR{int(time.time() * 1000)}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field_name}"; '
                f'filename="{file_name}"\r\n'
            ).encode("utf-8"),
            b"Content-Type: application/octet-stream\r\n\r\n",
            file_content,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _post_multipart(
    *,
    url: str,
    fields: dict[str, str],
    file_field_name: str,
    file_name: str,
    file_content: bytes,
    error_type: type[XfyunLfasrError],
    action_label: str,
    timeout_seconds: int = XFYUN_LFASR_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    body, content_type = _build_multipart_form_data(
        fields=fields,
        file_field_name=file_field_name,
        file_name=file_name,
        file_content=file_content,
    )
    http_request = request.Request(
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": content_type},
    )
    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise error_type(
            f"XFYUN LFASR {action_label} failed with HTTP {exc.code}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise error_type(
            f"XFYUN LFASR {action_label} hit a network error. {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise error_type(f"XFYUN LFASR {action_label} timed out.") from exc

    return _parse_common_response(
        response_text,
        error_type=error_type,
        action_label=action_label,
    )


def _iter_slices(file_path: Path, slice_size: int):
    with file_path.open("rb") as source:
        while True:
            chunk = source.read(slice_size)
            if not chunk:
                break
            yield chunk


class _SliceIdGenerator:
    def __init__(self) -> None:
        self._current = "aaaaaaaaa`"

    def next(self) -> str:
        current = self._current
        index = len(current) - 1
        while index >= 0:
            character = current[index]
            if character != "z":
                current = current[:index] + chr(ord(character) + 1) + current[index + 1 :]
                break
            current = current[:index] + "a" + current[index + 1 :]
            index -= 1
        self._current = current
        return self._current


def prepare_xfyun_task(
    file_path: Path,
    config: XfyunLfasrConfig,
) -> str:
    file_size = file_path.stat().st_size
    if file_size <= 0:
        raise XfyunLfasrPrepareError("XFYUN LFASR cannot prepare an empty audio file.")
    if file_size > XFYUN_LFASR_MAX_FILE_BYTES:
        raise XfyunLfasrPrepareError(
            f"XFYUN LFASR only supports files up to 500 MB, but got {round(file_size / (1024 * 1024), 1)} MB."
        )

    slice_num = max(1, math.ceil(file_size / config.sliceSizeBytes))
    payload = {
        **_build_auth_fields(config),
        "file_len": str(file_size),
        "file_name": file_path.name,
        "slice_num": str(slice_num),
        "lfasr_type": "0",
    }
    response_payload = _post_form(
        url=config.prepareEndpoint,
        fields=payload,
        error_type=XfyunLfasrPrepareError,
        action_label="prepare",
    )

    task_id = str(response_payload.get("data", "")).strip()
    if not task_id:
        raise XfyunLfasrPrepareError(
            "XFYUN LFASR prepare succeeded but returned no task_id."
        )

    LOGGER.info(
        "XFYUN LFASR prepare succeeded task_id=%s file_name=%s slice_num=%s",
        task_id,
        file_path.name,
        slice_num,
    )
    return task_id


def upload_xfyun_slices(
    task_id: str,
    file_path: Path,
    config: XfyunLfasrConfig,
) -> None:
    slice_id_generator = _SliceIdGenerator()
    for index, chunk in enumerate(_iter_slices(file_path, config.sliceSizeBytes), start=1):
        slice_id = slice_id_generator.next()
        fields = {
            **_build_auth_fields(config),
            "task_id": task_id,
            "slice_id": slice_id,
        }
        _post_multipart(
            url=config.uploadEndpoint,
            fields=fields,
            file_field_name="content",
            file_name=f"{file_path.name}.part{index}",
            file_content=chunk,
            error_type=XfyunLfasrUploadError,
            action_label="upload",
        )
        LOGGER.info(
            "XFYUN LFASR upload slice task_id=%s slice_id=%s size_bytes=%s",
            task_id,
            slice_id,
            len(chunk),
        )


def merge_xfyun_task(
    task_id: str,
    config: XfyunLfasrConfig,
) -> None:
    payload = {
        **_build_auth_fields(config),
        "task_id": task_id,
    }
    _post_form(
        url=config.mergeEndpoint,
        fields=payload,
        error_type=XfyunLfasrMergeError,
        action_label="merge",
    )
    LOGGER.info("XFYUN LFASR merge requested task_id=%s", task_id)


def _parse_data_json(
    payload: dict[str, Any],
    *,
    error_type: type[XfyunLfasrError],
    action_label: str,
) -> Any:
    data = payload.get("data")
    if data is None:
        return None
    if isinstance(data, str):
        stripped = data.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise error_type(
                f"XFYUN LFASR {action_label} returned invalid data JSON."
            ) from exc
    return data


def get_xfyun_progress(
    task_id: str,
    config: XfyunLfasrConfig,
) -> dict[str, Any]:
    payload = {
        **_build_auth_fields(config),
        "task_id": task_id,
    }
    response_payload = _post_form(
        url=config.progressEndpoint,
        fields=payload,
        error_type=XfyunLfasrPollingError,
        action_label="getProgress",
    )
    data_payload = _parse_data_json(
        response_payload,
        error_type=XfyunLfasrPollingError,
        action_label="getProgress",
    )
    if not isinstance(data_payload, dict):
        raise XfyunLfasrPollingError(
            "XFYUN LFASR getProgress returned no progress object."
        )
    return data_payload


def poll_xfyun_progress(
    task_id: str,
    config: XfyunLfasrConfig,
) -> dict[str, Any]:
    deadline = time.time() + max(config.pollTimeoutSeconds, 30)
    last_status = -1
    last_desc = ""

    while True:
        progress = get_xfyun_progress(task_id, config)
        status = int(progress.get("status", -1))
        desc = str(progress.get("desc", "")).strip()
        last_status = status
        last_desc = desc

        if status == XFYUN_LFASR_SUCCESS_STATUS:
            LOGGER.info("XFYUN LFASR progress complete task_id=%s status=%s", task_id, status)
            return progress
        if status not in XFYUN_LFASR_RUNNING_STATUSES:
            raise XfyunLfasrPollingError(
                f"XFYUN LFASR getProgress returned an unexpected terminal status task_id={task_id} status={status} desc={desc or '<empty>'}."
            )
        if time.time() >= deadline:
            raise XfyunLfasrPollingError(
                f"XFYUN LFASR polling timed out task_id={task_id} last_status={last_status} last_desc={last_desc or '<empty>'}."
            )
        time.sleep(max(config.pollIntervalSeconds, 1.0))


def get_xfyun_result(
    task_id: str,
    config: XfyunLfasrConfig,
) -> Any:
    payload = {
        **_build_auth_fields(config),
        "task_id": task_id,
    }
    response_payload = _post_form(
        url=config.resultEndpoint,
        fields=payload,
        error_type=XfyunLfasrResultParseError,
        action_label="getResult",
    )
    return _parse_data_json(
        response_payload,
        error_type=XfyunLfasrResultParseError,
        action_label="getResult",
    )


def parse_xfyun_lfasr_result(result_payload: Any) -> list[RealtimeSubtitlePiece]:
    if not isinstance(result_payload, list):
        raise XfyunLfasrResultParseError(
            "XFYUN LFASR getResult returned no sentence list."
        )

    pieces: list[RealtimeSubtitlePiece] = []
    seen: set[tuple[int, int, str]] = set()
    for item in result_payload:
        if not isinstance(item, dict):
            continue
        text = str(item.get("onebest", "")).strip()
        bg = str(item.get("bg", "")).strip()
        ed = str(item.get("ed", "")).strip()
        if not text or not bg or not ed:
            continue
        try:
            start_ms = max(0, int(round(float(bg))))
            end_ms = max(start_ms + 1, int(round(float(ed))))
        except ValueError:
            continue
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

    if not pieces:
        raise XfyunLfasrResultParseError(
            "XFYUN LFASR finished, but it did not return any usable sentence timestamps."
        )
    return pieces


def transcribe_with_xfyun_lfasr(
    file_path: Path,
    config: XfyunLfasrConfig,
) -> list[RealtimeSubtitlePiece]:
    task_id = prepare_xfyun_task(file_path, config)
    upload_xfyun_slices(task_id, file_path, config)
    merge_xfyun_task(task_id, config)
    poll_xfyun_progress(task_id, config)
    result_payload = get_xfyun_result(task_id, config)
    return parse_xfyun_lfasr_result(result_payload)
