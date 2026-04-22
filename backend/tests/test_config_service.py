"""Tests for LinguaSub config storage recovery."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.config_service import load_config


class ConfigServiceTests(unittest.TestCase):
    def test_load_config_recovers_from_invalid_json(self) -> None:
        sandbox = Path(__file__).resolve().parent / "fixtures" / "runtime-sandbox" / "config-recovery"
        if sandbox.exists():
            shutil.rmtree(sandbox)
        sandbox.mkdir(parents=True, exist_ok=True)
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


if __name__ == "__main__":
    unittest.main()
