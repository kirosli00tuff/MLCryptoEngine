"""Typed configuration layer.

Loads ``config/default.yaml`` and ``config/venues.yaml``, overlays environment
variables (``MLCE_`` prefix, ``__`` for nesting), validates everything through
pydantic, and fails fast at startup if a required secret is missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
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
    # Futures venues charge a fixed sum per contract per side, not a share of
    # notional, so their cost in bps depends on the price at the time of the
    # trade. When this is set it supersedes the bps fields, and the cost model
    # refuses to price a sample whose entry price it does not know rather than
    # falling back to a percentage that was never charged. See ADR-023.
    fee_usd_per_contract_per_side: float | None = Field(default=None, ge=0)


class SnapshotBehaviour(BaseModel):
    """How a venue delivers order book snapshots."""

    on_subscribe: bool
    checksum: bool
    notes: str = ""


class InstrumentMeta(BaseModel):
    """Fixed decimal precisions for one symbol (price, quantity)."""

    price_decimals: int = Field(ge=0)
    qty_decimals: int = Field(ge=0)
    # Units of the underlying per contract (MBT 0.1 BTC, MES $5 per index
    # point). Notional is price x this, which is what turns a per-contract
    # fee into basis points. Absent for spot instruments, where one unit of
    # the symbol is one unit of the underlying.
    contract_multiplier: float | None = Field(default=None, gt=0)


# How a stream of data reaches this project, and therefore how it is validated.
#
#   recorder  captured live by data/recorder/ into data/raw/venue=<venue>/,
#             validated by replaying that raw capture (data/validate/replay.py).
#   vendor    no recorder exists: days arrive as purchased vendor files under
#             data/vendor/ and are scored by data/databento/validate.py.
#   archive   free public historical bars, downloaded once and never live. Not
#             a venue this project trades on — it may not even be reachable
#             from here — so it carries no fee schedule and no endpoints. See
#             ADR-031.
#
# The distinction is not cosmetic. A *recorder* venue with no replay support is
# a configuration error worth failing on; a *vendor* venue with no raw capture
# is its normal, permanent state. Conflating the two is what made a routine
# `python -m data.validate --date <today>` abort before validating anything.
VenueKind = Literal["recorder", "vendor", "archive"]


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
    # Is the book feed a full-snapshot stream (each message replaces the book)
    # rather than incremental updates? Snapshot-stream venues are scored on
    # snapshot cadence instead of sequence/checksum integrity, and warm-start
    # replay is skipped because every message already carries the whole book.
    snapshot_stream: bool = False
    # See VenueKind above. Defaults to "recorder" on purpose: an undeclared
    # venue is one this project believes it is capturing live, so a missing
    # declaration surfaces as a loud configuration error rather than as a
    # silently skipped venue that nobody notices stopped being validated.
    kind: VenueKind = "recorder"

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


class BudgetSettings(BaseModel):
    """Hard spend ceiling for metered vendor data.

    Databento bills per request. ``vendor_usd_cap`` is a cumulative ceiling
    across a stage, enforced against an on-disk ledger so it survives a
    restart — a per-request check alone would let many small requests walk
    past the cap. ``refuse_without_estimate`` keeps the gate closed when a
    price cannot be obtained: an unpriceable request is never cheap by
    default.
    """

    vendor_usd_cap: float = Field(default=25.0, ge=0)
    refuse_without_estimate: bool = True


class SourceConfig(BaseModel):
    """A free public historical archive: bars downloaded once, never captured.

    Kept out of ``venues`` deliberately (ADR-031). A ``VenueConfig`` carries a
    matching-engine endpoint, a book depth, a snapshot protocol and a fee
    schedule — every one of which is either meaningless or actively misleading
    for an archive. Binance in particular is not legally reachable from British
    Columbia, so publishing a ``fee_tiers`` block for it would invite a future
    reader to model a strategy on fees no order of ours could ever pay.

    What an archive does share with a venue is its *kind*, so validation routes
    it the same way it routes vendor days: never replayed, always reported.
    """

    name: str
    # Always "archive" — declared rather than defaulted, so this can never be
    # mistaken for something the recorder is expected to be capturing.
    kind: VenueKind
    # The venue whose prints these bars are, for provenance. Not a promise that
    # the venue is reachable, tradeable, or configured under `venues`.
    venue: str
    base_url: str
    notes: str = ""

    @model_validator(mode="after")
    def _archive_only(self) -> SourceConfig:
        if self.kind != "archive":
            raise ValueError(
                f"source '{self.name}' declares kind={self.kind!r}; the sources block holds "
                "free historical archives only. A recorder or vendor stream belongs under "
                "'venues', where its endpoints and fee schedule are validated."
            )
        return self


class AppConfig(BaseSettings):
    """Full application configuration: YAML defaults overlaid by environment."""

    model_config = SettingsConfigDict(
        env_prefix="MLCE_",
        env_nested_delimiter="__",
        extra="forbid",
        # .env is gitignored and holds read-only vendor keys only (CLAUDE.md
        # rule 4). Loading it here means every entry point gets credentials
        # the same way, and a missing one fails at startup with a clear
        # message rather than deep inside a vendor client call.
        env_file=".env",
        env_file_encoding="utf-8",
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
    # Free public bar archives (ADR-031). Separate from `venues` because they
    # are history, not capture, and carry no tradeable fee schedule.
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    # Read-only market-data vendor key (CLAUDE.md rule 4). SecretStr so it
    # cannot leak through a repr, a log line, or a pydantic dump.
    databento_api_key: SecretStr | None = None
    # Read-only indexer key (CLAUDE.md rule 4): it can read chain history and
    # nothing else. SecretStr for the same no-leak reasons as Databento.
    helius_api_key: SecretStr | None = None
    # Credit cap for the Helius free tier, in request-weighted credits
    # (ADR-046). 2026-08-06: weights and the monthly quota are UNVERIFIED
    # against the dashboard — no usage endpoint is reachable keyless — so the
    # cap is set conservatively and every priced request is ledgered so the
    # operator can reconcile. Raising it is an operator edit, never code.
    helius_credit_cap: int = 30_000
    budget: BudgetSettings = BudgetSettings()

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

    def require_databento_key(self) -> str:
        """The Databento key, or a clear startup failure naming the variable.

        Read-only vendor credential (CLAUDE.md rule 4): it can buy and
        download market data and nothing else. Callers get the plain string
        only at the moment they construct the vendor client.
        """
        if self.databento_api_key is None or not self.databento_api_key.get_secret_value():
            raise MissingSecretError(["MLCE_DATABENTO_API_KEY"])
        return self.databento_api_key.get_secret_value()

    def require_helius_key(self) -> str:
        """The Helius key, or a clear startup failure naming the variable.

        Read-only indexer credential (CLAUDE.md rule 4): it can read chain
        history and nothing else. Callers get the plain string only at the
        moment they construct the client, and every priced request it enables
        passes through the credit gate (ADR-046) first.
        """
        if self.helius_api_key is None or not self.helius_api_key.get_secret_value():
            raise MissingSecretError(["MLCE_HELIUS_API_KEY"])
        return self.helius_api_key.get_secret_value()


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

    # Sources are optional: a checkout with no archive configured is valid, and
    # every consumer treats an empty mapping as "no free history available".
    sources = venues_doc.get("sources") or {}
    if not isinstance(sources, dict):
        raise ConfigError(f"{directory / 'venues.yaml'} 'sources' must be a mapping if present")

    config = AppConfig(**{**defaults, "venues": venues, "sources": sources})
    config.require_secrets()
    return config
