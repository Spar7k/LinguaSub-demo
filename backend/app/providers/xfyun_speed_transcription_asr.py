"""iFLYTEK speed transcription ASR provider."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from email.utils import formatdate
from pathlib import Path
from typing import Any, Iterator
from urllib import error, parse, request

from ..import_service import UnsupportedFileTypeError, detect_file_type
from ..speech_runtime_service import resolve_ffmpeg_binary
from .common import RealtimeSubtitlePiece

XFYUN_SPEED_UPLOAD_HOST = "upload-ost-api.xfyun.cn"
XFYUN_SPEED_UPLOAD_ENDPOINT = f"https://{XFYUN_SPEED_UPLOAD_HOST}/file/upload"
XFYUN_SPEED_MULTIPART_INIT_ENDPOINT = (
    f"https://{XFYUN_SPEED_UPLOAD_HOST}/file/mpupload/init"
)
XFYUN_SPEED_MULTIPART_UPLOAD_ENDPOINT = (
    f"https://{XFYUN_SPEED_UPLOAD_HOST}/file/mpupload/upload"
)
XFYUN_SPEED_MULTIPART_COMPLETE_ENDPOINT = (
    f"https://{XFYUN_SPEED_UPLOAD_HOST}/file/mpupload/complete"
)
XFYUN_SPEED_TASK_HOST = "ost-api.xfyun.cn"
XFYUN_SPEED_CREATE_ENDPOINT = f"https://{XFYUN_SPEED_TASK_HOST}/v2/ost/pro_create"
XFYUN_SPEED_QUERY_ENDPOINT = f"https://{XFYUN_SPEED_TASK_HOST}/v2/ost/query"

XFYUN_SPEED_SMALL_FILE_THRESHOLD_BYTES = 30 * 1024 * 1024
XFYUN_SPEED_SLICE_SIZE_BYTES = 10 * 1024 * 1024
XFYUN_SPEED_POLL_INTERVAL_SECONDS = 10.0
XFYUN_SPEED_POLL_TIMEOUT_SECONDS = 60 * 60
XFYUN_SPEED_HTTP_TIMEOUT_SECONDS = 120
XFYUN_SPEED_UPLOAD_TIMEOUT_SECONDS = 300
XFYUN_SPEED_AUDIO_SAMPLE_RATE = 16000
XFYUN_SPEED_AUDIO_CHANNELS = 1
XFYUN_SPEED_AUDIO_FORMAT = "audio/L16;rate=16000"
XFYUN_SPEED_AUDIO_ENCODING = "raw"
XFYUN_SPEED_LANGUAGE = "zh_cn"
XFYUN_SPEED_DOMAIN = "pro_ost_ed"
XFYUN_SPEED_ACCENT = "mandarin"
XFYUN_SPEED_RUNNING_STATUSES = {"1", "2"}
XFYUN_SPEED_SUCCESS_STATUSES = {"3", "4"}
XFYUN_SPEED_MAX_FILE_BYTES = 500 * 1024 * 1024
XFYUN_SPEED_PREPROCESSING_PROFILE = "video/audio -> mono 16 kHz 16-bit PCM WAV"


LOGGER = logging.getLogger("linguasub.transcription.xfyun_speed")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[LinguaSub][XfyunSpeedASR] %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


class XfyunSpeedTranscriptionError(RuntimeError):
    """Base error for iFLYTEK speed transcription."""


class XfyunSpeedTranscriptionConfigError(XfyunSpeedTranscriptionError):
    """Raised when speed transcription config is incomplete."""


class XfyunSpeedTranscriptionPreprocessError(XfyunSpeedTranscriptionError):
    """Raised when audio cannot be converted into the required format."""


class XfyunSpeedTranscriptionUploadError(XfyunSpeedTranscriptionError):
    """Raised when file upload fails."""


class XfyunSpeedTranscriptionTaskCreateError(XfyunSpeedTranscriptionError):
    """Raised when task creation fails."""


class XfyunSpeedTranscriptionPollingError(XfyunSpeedTranscriptionError):
    """Raised when query polling fails or times out."""


class XfyunSpeedTranscriptionResultParseError(XfyunSpeedTranscriptionError):
    """Raised when query returns no usable sentence timestamps."""


@dataclass(slots=True)
class XfyunSpeedTranscriptionConfig:
    appId: str
    apiKey: str
    apiSecret: str
    uploadEndpoint: str = XFYUN_SPEED_UPLOAD_ENDPOINT
    multipartInitEndpoint: str = XFYUN_SPEED_MULTIPART_INIT_ENDPOINT
    multipartUploadEndpoint: str = XFYUN_SPEED_MULTIPART_UPLOAD_ENDPOINT
    multipartCompleteEndpoint: str = XFYUN_SPEED_MULTIPART_COMPLETE_ENDPOINT
    createEndpoint: str = XFYUN_SPEED_CREATE_ENDPOINT
    queryEndpoint: str = XFYUN_SPEED_QUERY_ENDPOINT
    language: str = XFYUN_SPEED_LANGUAGE
    domain: str = XFYUN_SPEED_DOMAIN
    accent: str = XFYUN_SPEED_ACCENT
    audioFormat: str = XFYUN_SPEED_AUDIO_FORMAT
    audioEncoding: str = XFYUN_SPEED_AUDIO_ENCODING
    smallFileThresholdBytes: int = XFYUN_SPEED_SMALL_FILE_THRESHOLD_BYTES
    sliceSizeBytes: int = XFYUN_SPEED_SLICE_SIZE_BYTES
    pollIntervalSeconds: float = XFYUN_SPEED_POLL_INTERVAL_SECONDS
    pollTimeoutSeconds: int = XFYUN_SPEED_POLL_TIMEOUT_SECONDS


def build_xfyun_speed_config(
    app_id: str,
    api_key: str,
    api_secret: str,
) -> XfyunSpeedTranscriptionConfig:
    normalized_app_id = str(app_id).strip()
    normalized_api_key = str(api_key).strip()
    normalized_api_secret = str(api_secret).strip()

    if not normalized_app_id:
        raise XfyunSpeedTranscriptionConfigError(
            "讯飞极速录音转写大模型需要 AppID。"
        )
    if not normalized_api_key:
        raise XfyunSpeedTranscriptionConfigError(
            "讯飞极速录音转写大模型需要 APIKey。"
        )
    if not normalized_api_secret:
        raise XfyunSpeedTranscriptionConfigError(
            "讯飞极速录音转写大模型需要 APISecret。"
        )

    return XfyunSpeedTranscriptionConfig(
        appId=normalized_app_id,
        apiKey=normalized_api_key,
        apiSecret=normalized_api_secret,
    )


def _run_ffmpeg_command(command: list[str]) -> None:
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _build_xfyun_speed_ffmpeg_command(
    ffmpeg_binary: Path,
    input_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        str(ffmpeg_binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-map",
        "0:a:0?",
        "-vn",
        "-ac",
        str(XFYUN_SPEED_AUDIO_CHANNELS),
        "-ar",
        str(XFYUN_SPEED_AUDIO_SAMPLE_RATE),
        "-sample_fmt",
        "s16",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        str(output_path),
    ]


def _prepare_xfyun_speed_audio(file_path: Path, output_path: Path) -> None:
    ffmpeg_binary = resolve_ffmpeg_binary()
    if ffmpeg_binary is None:
        raise XfyunSpeedTranscriptionPreprocessError(
            "无法预处理讯飞极速录音转写大模型所需音频：系统未找到 FFmpeg。"
        )

    command = _build_xfyun_speed_ffmpeg_command(ffmpeg_binary, file_path, output_path)
    LOGGER.info(
        "Preparing XFYUN speed audio for '%s' with mono 16k 16-bit WAV.",
        file_path.name,
    )
    try:
        _run_ffmpeg_command(command)
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip() or "未知 FFmpeg 错误。"
        raise XfyunSpeedTranscriptionPreprocessError(
            f"无法将 '{file_path.name}' 预处理为讯飞极速录音转写大模型要求的 16k/16bit/单声道音频。{message}"
        ) from exc


@contextmanager
def prepare_xfyun_speed_audio_input(file_path: Path) -> Iterator[Path]:
    try:
        media_type = detect_file_type(file_path)
    except UnsupportedFileTypeError as exc:
        raise XfyunSpeedTranscriptionPreprocessError(str(exc)) from exc

    if media_type not in {"video", "audio"}:
        raise XfyunSpeedTranscriptionPreprocessError(
            "讯飞极速录音转写大模型只支持音频或视频文件。"
        )

    with tempfile.TemporaryDirectory(prefix="linguasub-xfyun-speed-") as temp_dir:
        output_path = Path(temp_dir) / f"{file_path.stem}.xfyun-speed.wav"
        _prepare_xfyun_speed_audio(file_path, output_path)
        yield output_path


def _new_request_id() -> str:
    return f"linguasub-{uuid.uuid4().hex}"


def _sha256_digest(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "SHA-256=" + base64.b64encode(digest).decode("utf-8")


def _build_xfyun_speed_headers(
    *,
    host: str,
    path: str,
    body: bytes,
    content_type: str,
    config: XfyunSpeedTranscriptionConfig,
) -> dict[str, str]:
    date = formatdate(timeval=None, localtime=False, usegmt=True)
    digest = _sha256_digest(body)
    signature_origin = (
        f"host: {host}\n"
        f"date: {date}\n"
        f"POST {path} HTTP/1.1\n"
        f"digest: {digest}"
    )
    signature = base64.b64encode(
        hmac.new(
            config.apiSecret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    authorization = (
        f'api_key="{config.apiKey}",'
        'algorithm="hmac-sha256",'
        'headers="host date request-line digest",'
        f'signature="{signature}"'
    )
    return {
        "Host": host,
        "Date": date,
        "Digest": digest,
        "Authorization": authorization,
        "Content-Type": content_type,
        "Accept": "application/json",
    }


def _build_multipart_form_data(
    *,
    fields: dict[str, str],
    file_field_name: str,
    file_name: str,
    file_content: bytes,
) -> tuple[bytes, str]:
    boundary = f"----LinguaSubXfyunSpeed{int(time.time() * 1000)}"
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


def _send_signed_request(
    *,
    url: str,
    body: bytes,
    content_type: str,
    error_type: type[XfyunSpeedTranscriptionError],
    action_label: str,
    config: XfyunSpeedTranscriptionConfig,
    timeout_seconds: int,
) -> dict[str, Any]:
    parsed = parse.urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"
    headers = _build_xfyun_speed_headers(
        host=host,
        path=path,
        body=body,
        content_type=content_type,
        config=config,
    )

    http_request = request.Request(
        url=url,
        data=body,
        method="POST",
        headers=headers,
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise error_type(
            f"讯飞极速录音转写大模型{action_label}失败，HTTP {exc.code}。{error_text}"
        ) from exc
    except error.URLError as exc:
        raise error_type(
            f"讯飞极速录音转写大模型{action_label}失败，网络异常：{exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise error_type(f"讯飞极速录音转写大模型{action_label}超时。") from exc

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise error_type(
            f"讯飞极速录音转写大模型{action_label}返回了无效 JSON。"
        ) from exc

    if not isinstance(payload, dict):
        raise error_type(
            f"讯飞极速录音转写大模型{action_label}返回了异常响应。"
        )

    code = int(payload.get("code", -1))
    if code != 0:
        message = str(payload.get("message", "")).strip() or f"{action_label}失败"
        raise error_type(
            f"讯飞极速录音转写大模型{action_label}失败，code={code}。{message}"
        )

    return payload


def _post_json(
    *,
    url: str,
    payload: dict[str, Any],
    error_type: type[XfyunSpeedTranscriptionError],
    action_label: str,
    config: XfyunSpeedTranscriptionConfig,
    timeout_seconds: int = XFYUN_SPEED_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _send_signed_request(
        url=url,
        body=body,
        content_type="application/json",
        error_type=error_type,
        action_label=action_label,
        config=config,
        timeout_seconds=timeout_seconds,
    )


def _post_multipart(
    *,
    url: str,
    fields: dict[str, str],
    file_field_name: str,
    file_name: str,
    file_content: bytes,
    error_type: type[XfyunSpeedTranscriptionError],
    action_label: str,
    config: XfyunSpeedTranscriptionConfig,
    timeout_seconds: int = XFYUN_SPEED_UPLOAD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    body, content_type = _build_multipart_form_data(
        fields=fields,
        file_field_name=file_field_name,
        file_name=file_name,
        file_content=file_content,
    )
    return _send_signed_request(
        url=url,
        body=body,
        content_type=content_type,
        error_type=error_type,
        action_label=action_label,
        config=config,
        timeout_seconds=timeout_seconds,
    )


def _normalize_upload_url(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        file_url = str(data.get("url", "")).strip()
        if file_url:
            return file_url
    raise XfyunSpeedTranscriptionUploadError(
        "讯飞极速录音转写大模型上传成功，但未返回可用的 file_url。"
    )


def _normalize_upload_id(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        upload_id = str(data.get("upload_id", "")).strip()
        if upload_id:
            return upload_id
    raise XfyunSpeedTranscriptionUploadError(
        "讯飞极速录音转写大模型分块上传初始化成功，但未返回 upload_id。"
    )


def _upload_small_file(
    file_path: Path,
    config: XfyunSpeedTranscriptionConfig,
) -> str:
    request_id = _new_request_id()
    file_content = file_path.read_bytes()
    payload = _post_multipart(
        url=config.uploadEndpoint,
        fields={
            "request_id": request_id,
            "app_id": config.appId,
        },
        file_field_name="data",
        file_name=file_path.name,
        file_content=file_content,
        error_type=XfyunSpeedTranscriptionUploadError,
        action_label="小文件上传",
        config=config,
    )
    return _normalize_upload_url(payload)


def _init_multipart_upload(
    request_id: str,
    config: XfyunSpeedTranscriptionConfig,
) -> str:
    payload = _post_json(
        url=config.multipartInitEndpoint,
        payload={
            "request_id": request_id,
            "app_id": config.appId,
        },
        error_type=XfyunSpeedTranscriptionUploadError,
        action_label="分块上传初始化",
        config=config,
    )
    return _normalize_upload_id(payload)


def _upload_part(
    *,
    request_id: str,
    upload_id: str,
    slice_id: int,
    chunk: bytes,
    config: XfyunSpeedTranscriptionConfig,
) -> None:
    _post_multipart(
        url=config.multipartUploadEndpoint,
        fields={
            "request_id": request_id,
            "app_id": config.appId,
            "upload_id": upload_id,
            "slice_id": str(slice_id),
        },
        file_field_name="data",
        file_name=f"slice-{slice_id}.bin",
        file_content=chunk,
        error_type=XfyunSpeedTranscriptionUploadError,
        action_label=f"分块上传 slice_id={slice_id}",
        config=config,
    )


def _complete_multipart_upload(
    *,
    request_id: str,
    upload_id: str,
    config: XfyunSpeedTranscriptionConfig,
) -> str:
    payload = _post_json(
        url=config.multipartCompleteEndpoint,
        payload={
            "request_id": request_id,
            "app_id": config.appId,
            "upload_id": upload_id,
        },
        error_type=XfyunSpeedTranscriptionUploadError,
        action_label="分块上传完成",
        config=config,
    )
    return _normalize_upload_url(payload)


def upload_xfyun_speed_file(
    file_path: Path,
    config: XfyunSpeedTranscriptionConfig,
) -> str:
    file_size = file_path.stat().st_size
    if file_size <= 0:
        raise XfyunSpeedTranscriptionUploadError("待上传的讯飞音频文件为空。")
    if file_size > XFYUN_SPEED_MAX_FILE_BYTES:
        raise XfyunSpeedTranscriptionUploadError(
            "讯飞极速录音转写大模型上传失败：音频文件超过 500MB 限制。"
        )

    if file_size < config.smallFileThresholdBytes:
        LOGGER.info(
            "Uploading XFYUN speed file '%s' with small-file endpoint size_mb=%.2f",
            file_path.name,
            file_size / (1024 * 1024),
        )
        return _upload_small_file(file_path, config)

    LOGGER.info(
        "Uploading XFYUN speed file '%s' with multipart endpoint size_mb=%.2f",
        file_path.name,
        file_size / (1024 * 1024),
    )
    request_id = _new_request_id()
    upload_id = _init_multipart_upload(request_id, config)
    with file_path.open("rb") as source:
        slice_id = 1
        while True:
            chunk = source.read(config.sliceSizeBytes)
            if not chunk:
                break
            _upload_part(
                request_id=request_id,
                upload_id=upload_id,
                slice_id=slice_id,
                chunk=chunk,
                config=config,
            )
            slice_id += 1

    return _complete_multipart_upload(
        request_id=request_id,
        upload_id=upload_id,
        config=config,
    )


def create_xfyun_speed_task(
    file_url: str,
    config: XfyunSpeedTranscriptionConfig,
) -> str:
    normalized_file_url = str(file_url).strip()
    if not normalized_file_url:
        raise XfyunSpeedTranscriptionTaskCreateError(
            "讯飞极速录音转写大模型创建任务失败：file_url 为空。"
        )

    payload = _post_json(
        url=config.createEndpoint,
        payload={
            "common": {
                "app_id": config.appId,
            },
            "business": {
                "request_id": _new_request_id(),
                "language": config.language,
                "domain": config.domain,
                "accent": config.accent,
            },
            "data": {
                "audio_url": normalized_file_url,
                "audio_src": "http",
                "format": config.audioFormat,
                "encoding": config.audioEncoding,
            },
        },
        error_type=XfyunSpeedTranscriptionTaskCreateError,
        action_label="创建任务",
        config=config,
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise XfyunSpeedTranscriptionTaskCreateError(
            "讯飞极速录音转写大模型创建任务失败：未返回 data。"
        )
    task_id = str(data.get("task_id", "")).strip()
    if not task_id:
        raise XfyunSpeedTranscriptionTaskCreateError(
            "讯飞极速录音转写大模型创建任务失败：未返回 task_id。"
        )
    LOGGER.info("XFYUN speed task created task_id=%s", task_id)
    return task_id


def query_xfyun_speed_task(
    task_id: str,
    config: XfyunSpeedTranscriptionConfig,
) -> dict[str, Any]:
    normalized_task_id = str(task_id).strip()
    if not normalized_task_id:
        raise XfyunSpeedTranscriptionPollingError(
            "讯飞极速录音转写大模型查询任务失败：task_id 无效。"
        )

    return _post_json(
        url=config.queryEndpoint,
        payload={
            "common": {
                "app_id": config.appId,
            },
            "business": {
                "task_id": normalized_task_id,
            },
        },
        error_type=XfyunSpeedTranscriptionPollingError,
        action_label="查询任务",
        config=config,
        timeout_seconds=60,
    )


def _extract_query_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise XfyunSpeedTranscriptionPollingError(
            "讯飞极速录音转写大模型查询任务失败：未返回 data。"
        )
    return data


def _normalize_task_status(data: dict[str, Any]) -> str:
    status = data.get("task_status")
    if status is None:
        return ""
    return str(status).strip()


def _query_has_usable_result(data: dict[str, Any]) -> bool:
    result = _maybe_parse_json(data.get("result"))
    if not isinstance(result, dict):
        return False
    for key in ("lattice", "lattice2"):
        value = _maybe_parse_json(result.get(key))
        if isinstance(value, list) and value:
            return True
    return False


def poll_xfyun_speed_task(
    task_id: str,
    config: XfyunSpeedTranscriptionConfig,
) -> dict[str, Any]:
    deadline = time.time() + max(config.pollTimeoutSeconds, 30)
    last_status = ""

    while True:
        payload = query_xfyun_speed_task(task_id, config)
        data = _extract_query_data(payload)
        status = _normalize_task_status(data)
        if status:
            last_status = status

        if status in XFYUN_SPEED_SUCCESS_STATUSES or _query_has_usable_result(data):
            LOGGER.info("XFYUN speed task finished task_id=%s status=%s", task_id, status)
            return payload
        if status and status not in XFYUN_SPEED_RUNNING_STATUSES:
            message = str(payload.get("message", "")).strip() or "任务进入失败状态。"
            raise XfyunSpeedTranscriptionPollingError(
                f"讯飞极速录音转写大模型轮询失败：task_id={task_id} status={status}。{message}"
            )

        if time.time() >= deadline:
            raise XfyunSpeedTranscriptionPollingError(
                f"讯飞极速录音转写大模型轮询超时：task_id={task_id} last_status={last_status or '<unknown>'}。"
            )

        time.sleep(max(config.pollIntervalSeconds, 1.0))


def _maybe_parse_json(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return value
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


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


def _extract_text_from_json_1best(json_1best: Any) -> str:
    payload = _maybe_parse_json(json_1best)
    if not isinstance(payload, dict):
        return ""

    sentence = payload.get("st")
    if not isinstance(sentence, dict):
        return ""

    fragments: list[str] = []
    for result in sentence.get("rt", []):
        if not isinstance(result, dict):
            continue
        for word_slot in result.get("ws", []):
            if not isinstance(word_slot, dict):
                continue
            candidates = word_slot.get("cw")
            if not isinstance(candidates, list):
                continue
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                text = str(candidate.get("w", ""))
                if text:
                    fragments.append(text)
                break

    return "".join(fragments).strip()


def _iter_sentence_items(result_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(result_payload, dict):
        return []

    result_data = _maybe_parse_json(result_payload.get("result"))
    if not isinstance(result_data, dict):
        result_data = result_payload.get("result")
    if not isinstance(result_data, dict):
        return []

    for key in ("lattice", "lattice2"):
        value = _maybe_parse_json(result_data.get(key))
        if isinstance(value, list) and value:
            return [item for item in value if isinstance(item, dict)]
    return []


def parse_xfyun_speed_result(payload: dict[str, Any]) -> list[RealtimeSubtitlePiece]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise XfyunSpeedTranscriptionResultParseError(
            "讯飞极速录音转写大模型结果解析失败：未返回 data。"
        )

    sentence_items = _iter_sentence_items(data)
    if not sentence_items:
        raise XfyunSpeedTranscriptionResultParseError(
            "讯飞极速录音转写大模型结果解析失败：没有可用的句级结果。"
        )

    pieces: list[RealtimeSubtitlePiece] = []
    seen: set[tuple[int, int, str]] = set()

    for item in sentence_items:
        json_1best = item.get("json_1best")
        payload_1best = _maybe_parse_json(json_1best)
        if not isinstance(payload_1best, dict):
            continue

        sentence = payload_1best.get("st")
        if not isinstance(sentence, dict):
            continue

        start_ms = _coerce_milliseconds(sentence.get("bg"))
        end_ms = _coerce_milliseconds(sentence.get("ed"))
        text = _extract_text_from_json_1best(payload_1best)
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

    raise XfyunSpeedTranscriptionResultParseError(
        "讯飞极速录音转写大模型结果解析失败：无法提取可用的句级时间与文本。"
    )


def transcribe_with_xfyun_speed_transcription(
    file_path: Path,
    config: XfyunSpeedTranscriptionConfig,
) -> list[RealtimeSubtitlePiece]:
    with prepare_xfyun_speed_audio_input(file_path) as audio_path:
        file_url = upload_xfyun_speed_file(audio_path, config)
        task_id = create_xfyun_speed_task(file_url, config)
        query_payload = poll_xfyun_speed_task(task_id, config)
        return parse_xfyun_speed_result(query_payload)
