"""Local JSON config storage for LinguaSub."""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import strftime
from typing import Any

from .models import ApiProviderConfig, AppConfig, ProviderName, create_default_app_config

CONFIG_FILE_ENV = "LINGUASUB_CONFIG_PATH"
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "storage" / "app-config.json"
)


def _build_invalid_config_backup_path(config_path: Path) -> Path:
    timestamp = strftime("%Y%m%d-%H%M%S")
    return config_path.with_name(f"{config_path.stem}.invalid-{timestamp}{config_path.suffix}")


def _reset_invalid_config(config_path: Path) -> AppConfig:
    # Keep a copy of the broken config on disk so users do not silently lose it.
    if config_path.exists():
        backup_path = _build_invalid_config_backup_path(config_path)
        try:
            config_path.replace(backup_path)
        except OSError:
            try:
                backup_path.write_text(
                    config_path.read_text(encoding="utf-8", errors="replace"),
                    encoding="utf-8",
                )
                config_path.unlink(missing_ok=True)
            except OSError:
                pass

    default_config = create_default_app_config()
    save_config(default_config)
    return default_config


def get_default_user_data_dir() -> Path:
    for env_name in ("APPDATA", "LOCALAPPDATA"):
        env_value = os.getenv(env_name)
        if env_value:
            return Path(env_value).expanduser().resolve() / "LinguaSub"

    return DEFAULT_CONFIG_PATH.parent


def get_recommended_release_config_path() -> Path:
    return get_default_user_data_dir() / "app-config.json"


def get_config_path() -> Path:
    configured_path = os.getenv(CONFIG_FILE_ENV)
    if configured_path:
        return Path(configured_path).expanduser().resolve()

    return DEFAULT_CONFIG_PATH


def ensure_config_parent_exists() -> Path:
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    return config_path


def get_provider_entry(
    config: AppConfig, provider_name: ProviderName
) -> ApiProviderConfig | None:
    for provider in config.apiProviders:
        if provider.provider == provider_name:
            return provider

    return None


def get_default_provider_entry(provider_name: ProviderName) -> ApiProviderConfig:
    fallback = get_provider_entry(create_default_app_config(), provider_name)
    if fallback is None:
        raise ValueError(f"Unsupported provider: {provider_name}")

    return fallback


def get_active_provider_config(config: AppConfig) -> ApiProviderConfig:
    existing = get_provider_entry(config, config.defaultProvider)
    if existing:
        return existing

    fallback = get_default_provider_entry(config.defaultProvider)
    config.apiProviders.append(fallback)
    return fallback


def _normalize_text(value: str) -> str:
    return value.strip()


def get_conflicting_default_provider(
    provider_name: ProviderName,
    base_url: str,
    model: str,
) -> ProviderName | None:
    normalized_base_url = _normalize_text(base_url)
    normalized_model = _normalize_text(model)
    if not normalized_base_url or not normalized_model:
        return None

    for provider in create_default_app_config().apiProviders:
        if provider.provider == provider_name:
            continue
        if (
            normalized_base_url == _normalize_text(provider.baseUrl)
            and normalized_model == _normalize_text(provider.model)
        ):
            return provider.provider

    return None


def repair_active_provider_fields(
    config: AppConfig, active_provider: ApiProviderConfig
) -> None:
    defaults = get_default_provider_entry(config.defaultProvider)

    # Older mixed configs could keep another provider's default endpoint/model
    # pair under the selected provider. Repair the obvious cross-provider pair
    # before mirroring values back to the flat fields.
    if get_conflicting_default_provider(
        config.defaultProvider,
        active_provider.baseUrl,
        active_provider.model,
    ):
        active_provider.baseUrl = defaults.baseUrl
        active_provider.model = defaults.model

    if not _normalize_text(active_provider.baseUrl):
        if (
            _normalize_text(config.baseUrl)
            and not get_conflicting_default_provider(
                config.defaultProvider,
                config.baseUrl,
                config.model,
            )
        ):
            active_provider.baseUrl = config.baseUrl
        else:
            active_provider.baseUrl = defaults.baseUrl

    if not _normalize_text(active_provider.model):
        if (
            _normalize_text(config.model)
            and not get_conflicting_default_provider(
                config.defaultProvider,
                config.baseUrl,
                config.model,
            )
        ):
            active_provider.model = config.model
        else:
            active_provider.model = defaults.model


def sync_active_provider_fields(config: AppConfig) -> AppConfig:
    active_provider = get_active_provider_config(config)
    repair_active_provider_fields(config, active_provider)

    config.apiKey = active_provider.apiKey
    config.baseUrl = active_provider.baseUrl
    config.model = active_provider.model
    config.speechProvider = config.defaultTranscriptionProvider
    return config


def merge_provider_configs(
    existing: list[ApiProviderConfig], updates: list[dict[str, Any]]
) -> list[ApiProviderConfig]:
    provider_map: dict[str, ApiProviderConfig] = {
        provider.provider: provider for provider in existing
    }

    for patch in updates:
        provider_name = patch["provider"]
        target = provider_map.get(provider_name)

        if target is None:
            default_provider = get_provider_entry(
                create_default_app_config(), provider_name
            )
            if default_provider is None:
                raise ValueError(f"Unsupported provider: {provider_name}")
            target = default_provider
            provider_map[provider_name] = target

        for field_name in ("displayName", "apiKey", "baseUrl", "model", "enabled"):
            if field_name in patch:
                setattr(target, field_name, patch[field_name])

    return list(provider_map.values())


def load_config() -> AppConfig:
    config_path = ensure_config_parent_exists()

    if not config_path.exists():
        default_config = create_default_app_config()
        save_config(default_config)
        return default_config

    try:
        with config_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        config = AppConfig.from_dict(data)
        return sync_active_provider_fields(config)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _reset_invalid_config(config_path)


def save_config(config: AppConfig | dict[str, Any]) -> AppConfig:
    if isinstance(config, dict):
        config = AppConfig.from_dict(config)

    config = sync_active_provider_fields(config)
    config_path = ensure_config_parent_exists()

    with config_path.open("w", encoding="utf-8") as file:
        json.dump(config.to_dict(), file, ensure_ascii=False, indent=2)

    return config


def update_config(patch: dict[str, Any]) -> AppConfig:
    config = load_config()

    if "apiProviders" in patch:
        config.apiProviders = merge_provider_configs(
            config.apiProviders, patch["apiProviders"]
        )

    for field_name in (
        "defaultProvider",
        "defaultTranscriptionProvider",
        "speechProvider",
        "apiKey",
        "baseUrl",
        "model",
        "speechApiKey",
        "speechBaseUrl",
        "speechModel",
        "baiduAppId",
        "baiduApiKey",
        "baiduDevPid",
        "baiduCuid",
        "baiduFileAppId",
        "baiduFileApiKey",
        "baiduFileSecretKey",
        "baiduFileDevPid",
        "baiduFileSpeechUrl",
        "tencentAppId",
        "tencentSecretId",
        "tencentSecretKey",
        "tencentEngineModelType",
        "tencentFileSecretId",
        "tencentFileSecretKey",
        "tencentFileEngineModelType",
        "xfyunAppId",
        "xfyunSecretKey",
        "xfyunSpeedAppId",
        "xfyunSpeedApiKey",
        "xfyunSpeedApiSecret",
        "uploadCosSecretId",
        "uploadCosSecretKey",
        "uploadCosBucket",
        "uploadCosRegion",
        "outputMode",
        "modelStoragePath",
        "managedModelRoots",
        "managedModelPaths",
    ):
        if field_name in patch:
            setattr(config, field_name, patch[field_name])

    if "speechProvider" in patch and "defaultTranscriptionProvider" not in patch:
        config.defaultTranscriptionProvider = patch["speechProvider"]
    if "defaultTranscriptionProvider" in patch:
        config.speechProvider = patch["defaultTranscriptionProvider"]

    return save_config(config)


# CamelCase aliases keep the API names aligned with the user requirements.
loadConfig = load_config
saveConfig = save_config
updateConfig = update_config
