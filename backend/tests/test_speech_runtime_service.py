"""Tests for bundled speech runtime helpers."""

from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.config_service import load_config, save_config
from backend.app.models import create_default_app_config
from backend.app.speech_runtime_service import (
    FasterWhisperRuntimeStatus,
    SpeechModelDownloadFailedError,
    SpeechModelDownloadStatus,
    SpeechModelStorageValidationError,
    build_speech_model_statuses,
    cleanup_downloaded_models,
    download_speech_model,
    get_faster_whisper_runtime_status,
    get_model_download_dir,
    register_model_path,
    resolve_ffmpeg_binary,
    resolve_installed_model_path,
    validate_model_storage_directory,
    verify_model_directory,
)

SANDBOX_ROOT = Path(__file__).resolve().parent / "fixtures" / "runtime-sandbox"
SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)


def reset_sandbox(name: str) -> Path:
    target = SANDBOX_ROOT / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return target


class SpeechRuntimeServiceTests(unittest.TestCase):
    def test_resolve_ffmpeg_binary_prefers_env_path(self) -> None:
        sandbox = reset_sandbox("ffmpeg-env")
        ffmpeg_path = sandbox / "ffmpeg.exe"
        ffmpeg_path.write_text("fake", encoding="utf-8")

        with patch.dict(
            os.environ,
            {"LINGUASUB_FFMPEG_PATH": str(ffmpeg_path)},
            clear=False,
        ):
            resolved = resolve_ffmpeg_binary()

        self.assertEqual(resolved, ffmpeg_path.resolve())

    def test_resolve_ffmpeg_binary_falls_back_to_packaged_runtime_layout(self) -> None:
        sandbox = reset_sandbox("ffmpeg-packaged-runtime")
        executable_dir = sandbox / "LinguaSub"
        runtime_dir = executable_dir / "resources" / "runtime" / "ffmpeg"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_path = runtime_dir / "ffmpeg.exe"
        ffmpeg_path.write_text("fake", encoding="utf-8")
        fake_executable = executable_dir / "linguasub-backend.exe"
        fake_executable.write_text("backend", encoding="utf-8")

        with (
            patch.dict(
                os.environ,
                {"LINGUASUB_FFMPEG_PATH": "", "LINGUASUB_RUNTIME_DIR": ""},
                clear=False,
            ),
            patch(
                "backend.app.speech_runtime_service.sys.executable",
                str(fake_executable),
            ),
            patch("backend.app.speech_runtime_service.shutil.which", return_value=None),
        ):
            resolved = resolve_ffmpeg_binary()

        self.assertEqual(resolved, ffmpeg_path.resolve())

    def test_resolve_ffmpeg_binary_falls_back_to_current_working_directory_runtime(self) -> None:
        sandbox = reset_sandbox("ffmpeg-working-directory")
        runtime_dir = sandbox / "resources" / "runtime" / "ffmpeg"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_path = runtime_dir / "ffmpeg.exe"
        ffmpeg_path.write_text("fake", encoding="utf-8")

        with (
            patch.dict(
                os.environ,
                {"LINGUASUB_FFMPEG_PATH": "", "LINGUASUB_RUNTIME_DIR": ""},
                clear=False,
            ),
            patch("backend.app.speech_runtime_service.Path.cwd", return_value=sandbox),
            patch(
                "backend.app.speech_runtime_service.sys.argv",
                ["Z:/unexpected/linguasub-backend.exe"],
            ),
            patch(
                "backend.app.speech_runtime_service.sys.executable",
                "Z:/unexpected/linguasub-backend.exe",
            ),
            patch("backend.app.speech_runtime_service.shutil.which", return_value=None),
        ):
            resolved = resolve_ffmpeg_binary()

        self.assertEqual(resolved, ffmpeg_path.resolve())

    def test_register_model_path_and_resolve_installed_model_path(self) -> None:
        model_root = reset_sandbox("model-registry")
        model_dir = model_root / "small-local"
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (model_dir / "model.bin").write_text("binary", encoding="utf-8")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        with patch.dict(
            os.environ,
            {"LINGUASUB_MODEL_DIR": str(model_root)},
            clear=False,
        ):
            register_model_path("small", model_dir)
            resolved = resolve_installed_model_path("small")

        self.assertEqual(resolved, model_dir.resolve())

    def test_build_speech_model_statuses_marks_missing_when_runtime_ready(self) -> None:
        model_root = reset_sandbox("model-missing")
        with (
            patch.dict(
                os.environ,
                {"LINGUASUB_MODEL_DIR": str(model_root)},
                clear=False,
            ),
            patch(
                "backend.app.speech_runtime_service._load_config_managed_model_paths",
                return_value=set(),
            ),
            patch(
                "backend.app.speech_runtime_service._load_config_managed_model_roots",
                return_value=set(),
            ),
            patch(
                "backend.app.speech_runtime_service.get_faster_whisper_runtime_status",
                return_value=FasterWhisperRuntimeStatus(
                    available=True,
                    detectedPath="C:/runtime/faster_whisper/__init__.py",
                    details="runtime ready",
                ),
            ),
        ):
            statuses = build_speech_model_statuses()

        self.assertTrue(any(model.size == "small" and model.status == "missing" for model in statuses))

    def test_resolve_installed_model_path_finds_managed_custom_root_even_if_not_saved(self) -> None:
        sandbox = reset_sandbox("managed-custom-root")
        config_path = sandbox / "app-config.json"
        default_root = sandbox / "default-speech-models"
        custom_parent = sandbox / "ExternalDrive"
        custom_root = custom_parent / "LinguaSub" / "Models"
        model_dir = custom_root / "small"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (model_dir / "model.bin").write_text("binary", encoding="utf-8")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        config = create_default_app_config()
        config.modelStoragePath = ""
        config.managedModelPaths = [str(model_dir.resolve())]

        with patch.dict(
            os.environ,
            {
                "LINGUASUB_CONFIG_PATH": str(config_path),
                "LINGUASUB_MODEL_DIR": str(default_root),
            },
            clear=False,
        ):
            save_config(config)
            register_model_path("small", model_dir)
            resolved = resolve_installed_model_path("small")

        self.assertEqual(resolved, model_dir.resolve())

    def test_validate_model_storage_directory_creates_target_folder(self) -> None:
        sandbox = reset_sandbox("storage-validation")
        selected_parent = sandbox / "custom-models"

        result = validate_model_storage_directory("small", selected_parent)
        owned_root = selected_parent / "LinguaSub" / "Models"

        self.assertEqual(result.path, str(owned_root.resolve()))
        self.assertTrue(owned_root.exists())
        self.assertTrue((owned_root / ".linguasub-model-root.json").exists())
        self.assertTrue(result.createdDirectory)
        self.assertTrue(result.writable)
        self.assertEqual(result.recommendedFreeSpaceBytes, 3_000 * 1024 * 1024)

    def test_register_model_path_records_managed_root(self) -> None:
        sandbox = reset_sandbox("managed-root-recording")
        config_path = sandbox / "app-config.json"
        model_root = sandbox / "drive" / "LinguaSub" / "Models"
        model_dir = model_root / "small"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (model_dir / "model.bin").write_text("binary", encoding="utf-8")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        with patch.dict(
            os.environ,
            {"LINGUASUB_CONFIG_PATH": str(config_path)},
            clear=False,
        ):
            register_model_path("small", model_dir)
            config = load_config()

        self.assertIn(str(model_root.resolve()), config.managedModelRoots)
        self.assertIn(str(model_dir.resolve()), config.managedModelPaths)

    def test_cleanup_downloaded_models_removes_only_owned_root(self) -> None:
        sandbox = reset_sandbox("cleanup-owned-root")
        selected_parent = sandbox / "CustomParent"
        selected_parent.mkdir(parents=True, exist_ok=True)
        unrelated_file = selected_parent / "keep-me.txt"
        unrelated_file.write_text("safe", encoding="utf-8")

        config_path = sandbox / "app-config.json"
        config = create_default_app_config()
        owned_root = selected_parent / "LinguaSub" / "Models"
        model_dir = owned_root / "small"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (model_dir / "model.bin").write_text("binary", encoding="utf-8")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        config.modelStoragePath = str(owned_root.resolve())
        config.managedModelPaths = [str(model_dir.resolve())]

        with patch.dict(
            os.environ,
            {"LINGUASUB_CONFIG_PATH": str(config_path)},
            clear=False,
        ):
            save_config(config)
            register_model_path("small", model_dir)
            result = cleanup_downloaded_models()

        self.assertIn(str(model_dir.resolve()), result.removedModelPaths)
        self.assertIn(str(owned_root.resolve()), result.removedRootPaths)
        self.assertTrue(selected_parent.exists())
        self.assertTrue(unrelated_file.exists())
        self.assertFalse(model_dir.exists())
        self.assertFalse(owned_root.exists())

    def test_cleanup_downloaded_models_skips_unowned_paths(self) -> None:
        sandbox = reset_sandbox("cleanup-protected")
        config_path = sandbox / "app-config.json"
        unowned_root = sandbox / "UserFolder"
        model_dir = unowned_root / "small"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (model_dir / "model.bin").write_text("binary", encoding="utf-8")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        config = create_default_app_config()
        config.managedModelPaths = [str(model_dir.resolve())]

        with patch.dict(
            os.environ,
            {"LINGUASUB_CONFIG_PATH": str(config_path)},
            clear=False,
        ):
            save_config(config)
            result = cleanup_downloaded_models()

        self.assertTrue(model_dir.exists())
        self.assertIn(str(unowned_root.resolve()), result.protectedPaths)

    def test_cleanup_downloaded_models_skips_link_like_paths(self) -> None:
        sandbox = reset_sandbox("cleanup-link-protected")
        config_path = sandbox / "app-config.json"
        selected_parent = sandbox / "CustomParent"
        owned_root = selected_parent / "LinguaSub" / "Models"
        model_dir = owned_root / "small"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (model_dir / "model.bin").write_text("binary", encoding="utf-8")
        (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")

        config = create_default_app_config()
        config.modelStoragePath = str(owned_root.resolve())
        config.managedModelRoots = [str(owned_root.resolve())]
        config.managedModelPaths = [str(model_dir.resolve())]

        with (
            patch.dict(
                os.environ,
                {"LINGUASUB_CONFIG_PATH": str(config_path)},
                clear=False,
            ),
            patch(
                "backend.app.speech_runtime_service._has_link_like_segment",
                side_effect=lambda path, stop_at=None: Path(path).resolve()
                == model_dir.resolve(),
            ),
        ):
            save_config(config)
            register_model_path("small", model_dir)
            result = cleanup_downloaded_models()

        self.assertTrue(model_dir.exists())
        self.assertIn(str(model_dir.resolve()), result.protectedPaths)

    def test_validate_model_storage_directory_rejects_file_path(self) -> None:
        sandbox = reset_sandbox("storage-validation-file")
        target_file = sandbox / "not-a-folder.txt"
        target_file.write_text("demo", encoding="utf-8")

        with self.assertRaises(SpeechModelStorageValidationError):
            validate_model_storage_directory("base", target_file)

    def test_verify_model_directory_reports_missing_required_files(self) -> None:
        sandbox = reset_sandbox("verify-model")
        model_dir = sandbox / "tiny"
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")

        is_valid, missing_files = verify_model_directory(model_dir)

        self.assertFalse(is_valid)
        self.assertIn("model.bin", missing_files)
        self.assertIn("tokenizer", missing_files)

    def test_download_speech_model_requires_verified_files(self) -> None:
        sandbox = reset_sandbox("download-verification")
        storage_dir = sandbox / "storage"
        broken_model_dir = storage_dir / "small"
        broken_model_dir.mkdir(parents=True, exist_ok=True)
        (broken_model_dir / "config.json").write_text("{}", encoding="utf-8")

        with (
            patch(
                "backend.app.speech_runtime_service._load_download_model_callable",
                return_value=lambda *_args, **_kwargs: object(),
            ),
            patch(
                "backend.app.speech_runtime_service._resolve_downloaded_model_path",
                return_value=broken_model_dir,
            ),
        ):
            with self.assertRaises(SpeechModelDownloadFailedError):
                download_speech_model("small", storage_dir)

    def test_download_speech_model_uses_model_specific_output_directory(self) -> None:
        sandbox = reset_sandbox("download-target-path")
        selected_parent = sandbox / "Downloads"
        captured_kwargs: dict[str, str] = {}

        def fake_download_model(
            _model_size: str,
            output_dir: str | None = None,
            cache_dir: str | None = None,
            **_kwargs: str,
        ) -> str:
            if output_dir is None:
                raise AssertionError("expected output_dir")
            captured_kwargs["output_dir"] = output_dir
            if cache_dir is not None:
                captured_kwargs["cache_dir"] = cache_dir
            target_dir = Path(output_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "config.json").write_text("{}", encoding="utf-8")
            (target_dir / "model.bin").write_text("binary", encoding="utf-8")
            (target_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
            return str(target_dir)

        with patch(
            "backend.app.speech_runtime_service._load_download_model_callable",
            return_value=fake_download_model,
        ):
            resolved_path, validation = download_speech_model("small", selected_parent)

        expected_root = Path(validation.path)
        expected_model_dir = get_model_download_dir(expected_root, "small")
        self.assertEqual(resolved_path, expected_model_dir)
        self.assertEqual(captured_kwargs["output_dir"], str(expected_model_dir))
        self.assertEqual(captured_kwargs["cache_dir"], str(expected_root))

    def test_download_speech_model_registers_verified_model_directory(self) -> None:
        sandbox = reset_sandbox("download-registers-model")
        config_path = sandbox / "app-config.json"
        selected_parent = sandbox / "PortableModels"

        def fake_download_model(
            _model_size: str,
            output_dir: str | None = None,
            cache_dir: str | None = None,
            **_kwargs: str,
        ) -> str:
            self.assertIsNotNone(output_dir)
            self.assertIsNotNone(cache_dir)
            target_dir = Path(output_dir or "")
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "config.json").write_text("{}", encoding="utf-8")
            (target_dir / "model.bin").write_text("binary", encoding="utf-8")
            (target_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
            return str(target_dir)

        with (
            patch.dict(
                os.environ,
                {"LINGUASUB_CONFIG_PATH": str(config_path)},
                clear=False,
            ),
            patch(
                "backend.app.speech_runtime_service._load_download_model_callable",
                return_value=fake_download_model,
            ),
        ):
            resolved_path, validation = download_speech_model("small", selected_parent)
            resolved_again = resolve_installed_model_path("small")
            config = load_config()

        expected_root = Path(validation.path)
        expected_model_dir = get_model_download_dir(expected_root, "small")
        self.assertEqual(resolved_path, expected_model_dir)
        self.assertEqual(resolved_again, expected_model_dir)
        self.assertIn(str(expected_root.resolve()), config.managedModelRoots)
        self.assertIn(str(expected_model_dir.resolve()), config.managedModelPaths)

    def test_download_speech_model_finalizes_snapshot_result_into_managed_target(self) -> None:
        sandbox = reset_sandbox("download-snapshot-finalization")
        config_path = sandbox / "app-config.json"
        selected_parent = sandbox / "PortableModels"
        snapshot_root = sandbox / "hf-cache" / "models--small" / "snapshots" / "abc123"

        def fake_download_model(
            _model_size: str,
            output_dir: str | None = None,
            cache_dir: str | None = None,
            **_kwargs: str,
        ) -> str:
            self.assertIsNotNone(output_dir)
            self.assertIsNotNone(cache_dir)
            snapshot_root.mkdir(parents=True, exist_ok=True)
            (snapshot_root / "config.json").write_text("{}", encoding="utf-8")
            (snapshot_root / "model.bin").write_text("binary", encoding="utf-8")
            (snapshot_root / "tokenizer.json").write_text("{}", encoding="utf-8")
            return str(snapshot_root)

        with (
            patch.dict(
                os.environ,
                {"LINGUASUB_CONFIG_PATH": str(config_path)},
                clear=False,
            ),
            patch(
                "backend.app.speech_runtime_service._load_download_model_callable",
                return_value=fake_download_model,
            ),
        ):
            resolved_path, validation = download_speech_model("small", selected_parent)
            config = load_config()

        expected_root = Path(validation.path)
        expected_model_dir = get_model_download_dir(expected_root, "small")
        self.assertEqual(resolved_path, expected_model_dir)
        self.assertTrue((expected_model_dir / "config.json").exists())
        self.assertTrue((expected_model_dir / "model.bin").exists())
        self.assertTrue((expected_model_dir / "tokenizer.json").exists())
        self.assertIn(str(expected_root.resolve()), config.managedModelRoots)
        self.assertIn(str(expected_model_dir.resolve()), config.managedModelPaths)

    def test_build_speech_model_statuses_marks_failed_download(self) -> None:
        with (
            patch(
                "backend.app.speech_runtime_service.get_faster_whisper_runtime_status",
                return_value=FasterWhisperRuntimeStatus(
                    available=True,
                    detectedPath="C:/runtime/faster_whisper/__init__.py",
                    details="runtime ready",
                ),
            ),
            patch(
                "backend.app.speech_runtime_service.resolve_installed_model_path",
                return_value=None,
            ),
            patch(
                "backend.app.speech_runtime_service.get_download_status",
                return_value=SpeechModelDownloadStatus(
                    active=False,
                    modelSize="small",
                    status="error",
                    targetPath="D:/models/small",
                    usingDefaultStorage=False,
                    progress=0,
                    message="Model download failed for 'small'.",
                    error="Missing: model.bin",
                ),
            ),
        ):
            statuses = build_speech_model_statuses()

        small_status = next(model for model in statuses if model.size == "small")
        self.assertEqual(small_status.status, "error")
        self.assertIn("model.bin", small_status.details)

    def test_get_faster_whisper_runtime_status_reports_missing_module(self) -> None:
        with patch(
            "backend.app.speech_runtime_service.importlib.import_module",
            side_effect=ModuleNotFoundError("No module named 'faster_whisper'"),
        ):
            status = get_faster_whisper_runtime_status()

        self.assertFalse(status.available)
        self.assertIn("faster_whisper", status.details)


if __name__ == "__main__":
    unittest.main()
