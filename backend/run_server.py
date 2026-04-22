"""Entry point for the local LinguaSub backend."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence

try:
    from app.server import run_server
    from app.speech_runtime_service import cleanup_downloaded_models
except ModuleNotFoundError:  # pragma: no cover - helps unit tests import as backend.run_server
    from backend.app.server import run_server
    from backend.app.speech_runtime_service import cleanup_downloaded_models


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="linguasub-backend")
    parser.add_argument(
        "--cleanup-models",
        action="store_true",
        help="Remove only LinguaSub-managed downloaded speech models, then exit.",
    )
    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Override the LinguaSub config path for maintenance commands.",
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Override the default speech model root for maintenance commands.",
    )
    return parser


def _apply_runtime_overrides(args: argparse.Namespace) -> None:
    if args.config_path:
        os.environ["LINGUASUB_CONFIG_PATH"] = args.config_path
    if args.model_dir:
        os.environ["LINGUASUB_MODEL_DIR"] = args.model_dir


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _apply_runtime_overrides(args)

    if args.cleanup_models:
        try:
            result = cleanup_downloaded_models()
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": error_text,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1

        print(
            json.dumps(
                {
                    "ok": True,
                    "result": result.to_dict(),
                },
                ensure_ascii=False,
            )
        )
        return 0

    run_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
