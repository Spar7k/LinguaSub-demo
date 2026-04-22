"""Shared helpers for realtime cloud ASR providers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(slots=True)
class RealtimeSubtitlePiece:
    index: int
    startMs: int
    endMs: int
    text: str


def load_websocket_module():
    try:
        import websocket  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "实时语音识别依赖 websocket-client。请在后端环境中安装 websocket-client 后再试。"
        ) from exc

    return websocket


def iter_binary_chunks(file_path: Path, chunk_size: int) -> Iterator[bytes]:
    with file_path.open("rb") as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            yield chunk


def realtime_sleep(chunk_ms: int) -> None:
    time.sleep(max(chunk_ms, 20) / 1000)

