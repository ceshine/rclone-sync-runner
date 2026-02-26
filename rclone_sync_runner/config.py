"""Configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from rclone_sync_runner.models import RunnerConfig


class ConfigError(RuntimeError):
    """Raised when configuration loading or validation fails."""


def load_config(config_path: Path) -> RunnerConfig:
    """Load and validate runner configuration from YAML.

    Args:
        config_path: Path to YAML config file.

    Returns:
        Parsed and validated runner config.

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
