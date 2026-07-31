"""Typed configuration layer.

Loads ``config/default.yaml`` and ``config/venues.yaml``, overlays environment
variables (``MLCE_`` prefix, ``__`` for nesting), validates everything through
pydantic, and fails fast at startup if a required secret is missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


class ConfigError(RuntimeError):
    """Raised when configuration files are missing or malformed."""


class MissingSecretError(ConfigError):
    """Raised at startup when a required secret is absent from the environment."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        names = ", ".join(missing)
        super().__init__(
            f"Missing required secret environment variable(s): {names}. "
            "Set them in the environment (see .env.example); secrets never enter the repo."
        )


class FeeTier(BaseModel):
    """One maker/taker fee tier, keyed by trailing 30-day USD volume lower bound."""

    volume_usd_30d: float = Field(ge=0)
    maker_bps: float = Field(ge=0)
    taker_bps: float = Field(ge=0)


class SnapshotBehaviour(BaseModel):
    """How a venue delivers order book snapshots."""

    on_subscribe: bool
    checksum: bool
    notes: str = ""


class InstrumentMeta(BaseModel):
    """Fixed decimal precisions for one symbol (price, quantity)."""

    price_decimals: int = Field(ge=0)
    qty_decimals: int = Field(ge=0)


class VenueConfig(BaseModel):
    """Static metadata for one venue."""

    name: str
    ws_url: str
    rest_status_url: str
    symbols: list[str]
    book_depth: int = Field(gt=0)
    snapshot: SnapshotBehaviour
    aws_region: str
    fee_tiers: list[FeeTier]
    instruments: dict[str, InstrumentMeta] = Field(default_factory=dict)
    # Does this feed stamp messages with a sequence number the recorder can
    # check for continuity? Defaults to False on purpose: an undeclared venue
    # is reported as "sequence check not applicable" rather than credited with
    # zero sequence gaps, so a missing declaration can never look like a pass.
    sequence_numbers: bool = False

    @field_validator("fee_tiers")
    @classmethod
    def _tiers_sorted_from_zero(cls, tiers: list[FeeTier]) -> list[FeeTier]:
        if not tiers:
            raise ValueError("fee_tiers must not be empty")
        if tiers[0].volume_usd_30d != 0:
            raise ValueError("first fee tier must start at volume 0")
        volumes = [t.volume_usd_30d for t in tiers]
        if volumes != sorted(volumes):
            raise ValueError("fee_tiers must be sorted by volume_usd_30d ascending")
        return tiers

    def fees_for_volume(self, volume_usd_30d: float) -> FeeTier:
        """Return the fee tier applying to the given trailing 30-day volume."""
        applicable = self.fee_tiers[0]
        for tier in self.fee_tiers:
            if volume_usd_30d >= tier.volume_usd_30d:
                applicable = tier
        return applicable


class RecorderSettings(BaseModel):
    backoff_initial_s: float = Field(default=1.0, gt=0)
    backoff_max_s: float = Field(default=60.0, gt=0)
    backoff_jitter: float = Field(default=0.3, ge=0, le=1)
    heartbeat_interval_s: float = Field(default=10.0, gt=0)
    dry_run_messages: int = Field(default=50, gt=0)


class DiskSettings(BaseModel):
    """Free-space thresholds for the recorder's disk guard.

    Advisory only: crossing either threshold logs, and nothing else. Nothing in
    the pipeline stops recording or deletes data on low disk.
    """

    warn_free_gb: float = Field(default=50.0, gt=0)
    critical_free_gb: float = Field(default=20.0, gt=0)

    @model_validator(mode="after")
    def _critical_below_warn(self) -> DiskSettings:
        if self.critical_free_gb > self.warn_free_gb:
            raise ValueError(
                f"critical_free_gb ({self.critical_free_gb}) must not exceed "
                f"warn_free_gb ({self.warn_free_gb})"
            )
        return self


class TelemetrySettings(BaseModel):
    interval_s: float = Field(default=60.0, gt=0)
    timeout_s: float = Field(default=5.0, gt=0)
    window: int = Field(default=240, gt=0)


class BookSettings(BaseModel):
    interval_snapshot_ms: int = Field(default=1000, gt=0)
    snapshot_depth: int = Field(default=10, gt=0)


class AppConfig(BaseSettings):
    """Full application configuration: YAML defaults overlaid by environment."""

    model_config = SettingsConfigDict(
        env_prefix="MLCE_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    data_root: Path = Path("data")
    logs_dir: Path = Path("logs")
    log_level: str = "INFO"
    recorder: RecorderSettings = RecorderSettings()
    disk: DiskSettings = DiskSettings()
    telemetry: TelemetrySettings = TelemetrySettings()
    book: BookSettings = BookSettings()
    required_secrets: list[str] = Field(default_factory=list)
    venues: dict[str, VenueConfig] = Field(default_factory=dict)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Environment beats the YAML values passed through init kwargs.
        return env_settings, dotenv_settings, init_settings, file_secret_settings

    @property
    def raw_dir(self) -> Path:
        return self.data_root / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_root / "processed"

    def require_secrets(self) -> None:
        """Raise :class:`MissingSecretError` if any required secret is unset or empty."""
        missing = [name for name in self.required_secrets if not os.environ.get(name)]
        if missing:
            raise MissingSecretError(missing)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Malformed YAML in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError(f"Top level of {path} must be a mapping, got {type(loaded).__name__}")
    return loaded


def load_config(config_dir: Path | None = None) -> AppConfig:
    """Load, overlay, and validate configuration; fail fast on missing secrets.

    Order of precedence (highest wins): environment variables, then
    ``default.yaml``/``venues.yaml``, then model defaults.
    """
    directory = config_dir if config_dir is not None else CONFIG_DIR
    defaults = _read_yaml(directory / "default.yaml")
    venues_doc = _read_yaml(directory / "venues.yaml")
    venues = venues_doc.get("venues")
    if not isinstance(venues, dict) or not venues:
        raise ConfigError(f"{directory / 'venues.yaml'} must define a non-empty 'venues' mapping")

    config = AppConfig(**{**defaults, "venues": venues})
    config.require_secrets()
    return config
