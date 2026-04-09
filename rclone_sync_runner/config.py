"""Configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import RunnerConfig, SyncJob


class ConfigError(RuntimeError):
    """Raised when configuration loading or validation fails."""


def render_config_yaml(config: RunnerConfig) -> str:
    """Serialise a RunnerConfig to a clean YAML string.

    Args:
        config (RunnerConfig): The runner configuration to serialise.

    Returns:
        str: A YAML-formatted string representation of the configuration.
            The ``notifications`` block is omitted when no Telegram config is set.
    """
    data = config.model_dump(mode="json", by_alias=True)

    # Strip the notifications block when it carries no real config
    if config.notifications.telegram is None:
        data.pop("notifications", None)

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def load_config(config_path: Path) -> RunnerConfig:
    """Load and validate runner configuration from YAML.

    Args:
        config_path (Path): Path to YAML config file.

    Returns:
        RunnerConfig: Parsed and validated runner config.

    Raises:
        ConfigError: If file is missing, unreadable, malformed, or invalid.
    """
    if not config_path.exists():
        raise ConfigError(f"Config file does not exist: {config_path}")
    if not config_path.is_file():
        raise ConfigError(f"Config path is not a file: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            raw_data: Any = yaml.safe_load(handle)
    except OSError as error:
        raise ConfigError(f"Unable to read config file {config_path}: {error}") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"Invalid YAML in config file {config_path}: {error}") from error

    if raw_data is None:
        raise ConfigError(f"Config file is empty: {config_path}")
    if not isinstance(raw_data, dict):
        raise ConfigError("Config root must be a mapping/object.")

    try:
        return RunnerConfig.model_validate(raw_data)
    except ValidationError as error:
        raise ConfigError(f"Configuration validation failed: {error}") from error


def build_runner_config(jobs: list[SyncJob]) -> RunnerConfig:
    """Wrap jobs in a minimal version=1 RunnerConfig with default GlobalConfig.

    Args:
        jobs (list[SyncJob]): Sync job definitions to include in the config.

    Returns:
        RunnerConfig: Validated runner configuration with version 1 and default global settings.
    """
    return RunnerConfig.model_validate(
        {
            "version": 1,
            "global": {},
            "jobs": [job.model_dump() for job in jobs],
        }
    )
