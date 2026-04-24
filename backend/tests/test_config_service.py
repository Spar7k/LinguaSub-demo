"""Tests for LinguaSub config storage recovery."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.config_service import load_config, save_config
from backend.app.models import create_default_app_config


class ConfigServiceTests(unittest.TestCase):
    def create_sandbox(self, name: str) -> Path:
        sandbox = Path(__file__).resolve().parent / "fixtures" / "runtime-sandbox" / name
        if sandbox.exists():
            shutil.rmtree(sandbox)
        sandbox.mkdir(parents=True, exist_ok=True)
        return sandbox

    def test_load_config_recovers_from_invalid_json(self) -> None:
        sandbox = self.create_sandbox("config-recovery")
        config_path = sandbox / "app-config.json"
        config_path.write_text("{ invalid json", encoding="utf-8")

        with patch.dict(
            "os.environ",
            {"LINGUASUB_CONFIG_PATH": str(config_path)},
            clear=False,
        ):
            config = load_config()

        self.assertEqual(config.defaultProvider, "openaiCompatible")
        self.assertTrue(config_path.exists())

        recovered_data = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(recovered_data["defaultProvider"], "openaiCompatible")

        backup_files = list(sandbox.glob("app-config.invalid-*.json"))
        self.assertTrue(backup_files)

    def test_save_and_load_prefer_selected_provider_entry_over_stale_flat_fields(self) -> None:
        sandbox = self.create_sandbox("config-sync-active-provider")
        config_path = sandbox / "app-config.json"
        config = create_default_app_config()
        config.defaultProvider = "deepseek"
        config.apiKey = "sk-openai-flat"
        config.baseUrl = "https://api.openai.com/v1"
        config.model = "gpt-4.1-mini"

        deepseek_config = next(
            provider for provider in config.apiProviders if provider.provider == "deepseek"
        )
        deepseek_config.apiKey = "sk-deepseek"
        deepseek_config.baseUrl = "https://api.deepseek.com/v1"
        deepseek_config.model = "deepseek-chat"

        with patch.dict(
            "os.environ",
            {"LINGUASUB_CONFIG_PATH": str(config_path)},
            clear=False,
        ):
            saved_config = save_config(config)
            loaded_config = load_config()

        self.assertEqual(saved_config.defaultProvider, "deepseek")
        self.assertEqual(saved_config.apiKey, "sk-deepseek")
        self.assertEqual(saved_config.baseUrl, "https://api.deepseek.com/v1")
        self.assertEqual(saved_config.model, "deepseek-chat")
        self.assertEqual(loaded_config.apiKey, "sk-deepseek")
        self.assertEqual(loaded_config.baseUrl, "https://api.deepseek.com/v1")
        self.assertEqual(loaded_config.model, "deepseek-chat")

        saved_data = json.loads(config_path.read_text(encoding="utf-8"))
        saved_deepseek = next(
            provider for provider in saved_data["apiProviders"] if provider["provider"] == "deepseek"
        )
        self.assertEqual(saved_deepseek["baseUrl"], "https://api.deepseek.com/v1")
        self.assertEqual(saved_deepseek["model"], "deepseek-chat")

    def test_save_and_load_repair_obvious_cross_provider_defaults(self) -> None:
        sandbox = self.create_sandbox("config-sync-repair-mixup")
        config_path = sandbox / "app-config.json"
        config = create_default_app_config()
        config.defaultProvider = "deepseek"
        config.apiKey = "sk-deepseek"
        config.baseUrl = "https://api.openai.com/v1"
        config.model = "gpt-4.1-mini"

        deepseek_config = next(
            provider for provider in config.apiProviders if provider.provider == "deepseek"
        )
        deepseek_config.apiKey = "sk-deepseek"
        deepseek_config.baseUrl = "https://api.openai.com/v1"
        deepseek_config.model = "gpt-4.1-mini"

        with patch.dict(
            "os.environ",
            {"LINGUASUB_CONFIG_PATH": str(config_path)},
            clear=False,
        ):
            saved_config = save_config(config)
            loaded_config = load_config()

        self.assertEqual(saved_config.baseUrl, "https://api.deepseek.com/v1")
        self.assertEqual(saved_config.model, "deepseek-chat")
        self.assertEqual(loaded_config.baseUrl, "https://api.deepseek.com/v1")
        self.assertEqual(loaded_config.model, "deepseek-chat")

        saved_data = json.loads(config_path.read_text(encoding="utf-8"))
        saved_deepseek = next(
            provider for provider in saved_data["apiProviders"] if provider["provider"] == "deepseek"
        )
        self.assertEqual(saved_deepseek["baseUrl"], "https://api.deepseek.com/v1")
        self.assertEqual(saved_deepseek["model"], "deepseek-chat")


if __name__ == "__main__":
    unittest.main()
