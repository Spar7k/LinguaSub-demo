"""Tencent COS upload helper for async speech providers."""

from __future__ import annotations

import hashlib
import hmac
import logging
import mimetypes
import posixpath
import uuid
from dataclasses import dataclass
from pathlib import Path
from time import gmtime, strftime, time
from urllib import error, parse, request

TENCENT_COS_OBJECT_PREFIX = "linguasub/asr"
TENCENT_COS_URL_EXPIRES_SECONDS = 60 * 60
TENCENT_COS_UPLOAD_TIMEOUT_SECONDS = 120


LOGGER = logging.getLogger("linguasub.upload.tencent_cos")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[LinguaSub][TencentCOS] %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


class TencentCosUploadConfigError(RuntimeError):
    """Raised when Tencent COS upload config is incomplete."""


class TencentCosUploadError(RuntimeError):
    """Raised when Tencent COS upload fails."""


class TencentCosUploadUrlError(TencentCosUploadError):
    """Raised when Tencent COS upload URL generation fails."""


@dataclass(slots=True)
class TencentCosUploadConfig:
    secretId: str
    secretKey: str
    bucket: str
    region: str
    objectPrefix: str = TENCENT_COS_OBJECT_PREFIX
    urlExpiresSeconds: int = TENCENT_COS_URL_EXPIRES_SECONDS


def build_tencent_cos_upload_config(
    *,
    secret_id: str,
    secret_key: str,
    bucket: str,
    region: str,
    object_prefix: str = TENCENT_COS_OBJECT_PREFIX,
    url_expires_seconds: int = TENCENT_COS_URL_EXPIRES_SECONDS,
) -> TencentCosUploadConfig:
    normalized_secret_id = str(secret_id).strip()
    normalized_secret_key = str(secret_key).strip()
    normalized_bucket = str(bucket).strip()
    normalized_region = str(region).strip()
    normalized_prefix = str(object_prefix).strip().strip("/")
    expires_seconds = max(int(url_expires_seconds or TENCENT_COS_URL_EXPIRES_SECONDS), 60)

    if not normalized_secret_id:
        raise TencentCosUploadConfigError("Tencent COS upload needs SecretId.")
    if not normalized_secret_key:
        raise TencentCosUploadConfigError("Tencent COS upload needs SecretKey.")
    if not normalized_bucket:
        raise TencentCosUploadConfigError("Tencent COS upload needs bucket.")
    if not normalized_region:
        raise TencentCosUploadConfigError("Tencent COS upload needs region.")

    return TencentCosUploadConfig(
        secretId=normalized_secret_id,
        secretKey=normalized_secret_key,
        bucket=normalized_bucket,
        region=normalized_region,
        objectPrefix=normalized_prefix or TENCENT_COS_OBJECT_PREFIX,
        urlExpiresSeconds=expires_seconds,
    )


def _sanitize_object_name(file_name: str) -> str:
    safe_name = "".join(
        char if char.isalnum() or char in {".", "_", "-"} else "_"
        for char in file_name
    ).strip("._")
    return safe_name or "audio.wav"


def _build_object_key(file_path: Path, object_prefix: str) -> str:
    date_prefix = strftime("%Y%m%d", gmtime())
    safe_name = _sanitize_object_name(file_path.name)
    unique_name = f"{uuid.uuid4().hex}-{safe_name}"
    parts = [segment for segment in (object_prefix.strip("/"), date_prefix, unique_name) if segment]
    return posixpath.join(*parts)


def _build_cos_host(bucket: str, region: str) -> str:
    return f"{bucket}.cos.{region}.myqcloud.com"


def _build_cos_path(object_key: str) -> str:
    normalized_key = object_key.lstrip("/")
    return "/" + parse.quote(normalized_key, safe="/-_.~")


def _normalize_signature_value(value: str) -> str:
    compact = " ".join(str(value).strip().split())
    return parse.quote(compact, safe="-_.~")


def _build_canonical_components(items: dict[str, str]) -> tuple[str, str]:
    normalized_items = sorted(
        (
            _normalize_signature_value(key.lower()),
            _normalize_signature_value(value),
        )
        for key, value in items.items()
    )
    if not normalized_items:
        return "", ""

    pairs = "&".join(f"{key}={value}" for key, value in normalized_items)
    names = ";".join(key for key, _ in normalized_items)
    return pairs, names


def _sha1_hex(data: str | bytes) -> str:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha1(payload).hexdigest()


def _build_authorization_header(
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    config: TencentCosUploadConfig,
    sign_start: int,
    sign_end: int,
) -> str:
    header_string, header_list = _build_canonical_components(headers)
    http_string = f"{method.lower()}\n{path}\n\n{header_string}\n"
    sign_time = f"{sign_start};{sign_end}"
    sign_key = hmac.new(
        config.secretKey.encode("utf-8"),
        sign_time.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    string_to_sign = f"sha1\n{sign_time}\n{_sha1_hex(http_string)}\n"
    signature = hmac.new(
        sign_key,
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()

    return (
        "q-sign-algorithm=sha1"
        f"&q-ak={config.secretId}"
        f"&q-sign-time={sign_time}"
        f"&q-key-time={sign_time}"
        f"&q-header-list={header_list}"
        "&q-url-param-list="
        f"&q-signature={signature}"
    )


def _build_presigned_get_url(
    *,
    host: str,
    path: str,
    config: TencentCosUploadConfig,
) -> str:
    sign_start = int(time()) - 5
    sign_end = sign_start + config.urlExpiresSeconds
    signed_headers = {"host": host}
    authorization = _build_authorization_header(
        method="GET",
        path=path,
        headers=signed_headers,
        config=config,
        sign_start=sign_start,
        sign_end=sign_end,
    )

    query_items = []
    for part in authorization.split("&"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        query_items.append((key, value))

    query_string = parse.urlencode(query_items)
    return f"https://{host}{path}?{query_string}"


def upload_audio_file(
    file_path: str | Path,
    config: TencentCosUploadConfig,
    *,
    timeout_seconds: int = TENCENT_COS_UPLOAD_TIMEOUT_SECONDS,
) -> str:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise TencentCosUploadError(f"Local audio file does not exist: {path}")
    if not path.is_file():
        raise TencentCosUploadError(f"Audio upload path is not a file: {path}")

    object_key = _build_object_key(path, config.objectPrefix)
    host = _build_cos_host(config.bucket, config.region)
    cos_path = _build_cos_path(object_key)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    try:
        file_bytes = path.read_bytes()
    except OSError as exc:
        raise TencentCosUploadError(
            f"Failed to read local audio file before COS upload: {path}"
        ) from exc

    payload_sha1 = hashlib.sha1(file_bytes).hexdigest()
    sign_start = int(time()) - 5
    sign_end = sign_start + max(timeout_seconds, 60)
    signed_headers = {
        "content-length": str(len(file_bytes)),
        "content-type": content_type,
        "host": host,
        "x-cos-content-sha1": payload_sha1,
    }

    try:
        authorization = _build_authorization_header(
            method="PUT",
            path=cos_path,
            headers=signed_headers,
            config=config,
            sign_start=sign_start,
            sign_end=sign_end,
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise TencentCosUploadUrlError(
            "Failed to build Tencent COS upload authorization."
        ) from exc

    upload_url = f"https://{host}{cos_path}"
    LOGGER.info(
        "Uploading audio to Tencent COS bucket=%s region=%s object_key=%s size_bytes=%s",
        config.bucket,
        config.region,
        object_key,
        len(file_bytes),
    )

    http_request = request.Request(
        url=upload_url,
        data=file_bytes,
        headers={
            "Authorization": authorization,
            "Content-Length": str(len(file_bytes)),
            "Content-Type": content_type,
            "Host": host,
            "x-cos-content-sha1": payload_sha1,
        },
        method="PUT",
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", 200)
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise TencentCosUploadError(
            f"Tencent COS upload failed with HTTP {exc.code}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise TencentCosUploadError(
            f"Tencent COS upload hit a network error. {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise TencentCosUploadError("Tencent COS upload timed out.") from exc

    if status_code < 200 or status_code >= 300:
        raise TencentCosUploadError(
            f"Tencent COS upload returned unexpected HTTP {status_code}."
        )

    try:
        file_url = _build_presigned_get_url(host=host, path=cos_path, config=config)
    except Exception as exc:  # pragma: no cover - defensive
        raise TencentCosUploadUrlError(
            "Tencent COS upload succeeded, but the temporary file URL could not be generated."
        ) from exc

    LOGGER.info(
        "Tencent COS upload finished bucket=%s region=%s object_key=%s",
        config.bucket,
        config.region,
        object_key,
    )
    return file_url
