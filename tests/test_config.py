"""Config layer: loading, env overlay, and the missing-secret failure path."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.config import (
    AppConfig,
    ConfigError,
    MissingSecretError,
    load_config,
)


def test_real_config_loads_both_venues() -> None:
    cfg = load_config()

    assert set(cfg.venues) == {"kraken", "coinbase", "hyperliquid", "cme"}
    assert cfg.venues["hyperliquid"].snapshot_stream is True
    assert cfg.venues["kraken"].snapshot_stream is False
    kraken = cfg.venues["kraken"]
    assert kraken.ws_url.startswith("wss://")
    assert kraken.book_depth == 100
    assert kraken.snapshot.checksum is True
    assert "BTC/USD" in kraken.instruments
    coinbase = cfg.venues["coinbase"]
    assert coinbase.snapshot.checksum is False
    assert coinbase.symbols == ["BTC-USD", "ETH-USD"]


def test_environment_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLCE_TELEMETRY__INTERVAL_S", "7.5")
    monkeypatch.setenv("MLCE_LOG_LEVEL", "DEBUG")

    cfg = load_config()

    assert cfg.telemetry.interval_s == 7.5
    assert cfg.log_level == "DEBUG"


def test_missing_required_secret_raises_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLCE_REQUIRED_SECRETS", '["MLCE_TEST_ONLY_CREDENTIAL"]')
    monkeypatch.delenv("MLCE_TEST_ONLY_CREDENTIAL", raising=False)

    with pytest.raises(MissingSecretError) as excinfo:
        load_config()
    assert excinfo.value.missing == ["MLCE_TEST_ONLY_CREDENTIAL"]

    # Present-and-non-empty satisfies the requirement.
    monkeypatch.setenv("MLCE_TEST_ONLY_CREDENTIAL", "value")
    assert load_config().required_secrets == ["MLCE_TEST_ONLY_CREDENTIAL"]

    # Empty string still counts as missing: fail at boot, not mid-session.
    monkeypatch.setenv("MLCE_TEST_ONLY_CREDENTIAL", "")
    with pytest.raises(MissingSecretError):
        load_config()


def test_missing_config_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path)


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    (tmp_path / "default.yaml").write_text("data_root: [unclosed", encoding="utf-8")
    (tmp_path / "venues.yaml").write_text("venues: {}", encoding="utf-8")

    with pytest.raises(ConfigError, match="Malformed YAML"):
        load_config(tmp_path)


def test_empty_venues_rejected(tmp_path: Path) -> None:
    (tmp_path / "default.yaml").write_text("data_root: data", encoding="utf-8")
    (tmp_path / "venues.yaml").write_text("venues: {}", encoding="utf-8")

    with pytest.raises(ConfigError, match="non-empty 'venues' mapping"):
        load_config(tmp_path)


def test_fee_tier_lookup_uses_highest_matching_tier() -> None:
    cfg = load_config()
    kraken = cfg.venues["kraken"]

    # Base tier per the 2026-07-09 Kraken restructure (see venues.yaml comment).
    assert kraken.fees_for_volume(0).taker_bps == 40  # base tier reconciled C.27 (ADR-055)
    assert kraken.fees_for_volume(0).maker_bps == 25
    assert kraken.fees_for_volume(60_000).maker_bps == 14
    assert kraken.fees_for_volume(999_999_999).maker_bps == 0


def test_fee_tiers_must_start_at_zero() -> None:
    from data.config import VenueConfig

    base = load_config().venues["kraken"].model_dump()
    base["fee_tiers"] = [{"volume_usd_30d": 100, "maker_bps": 1, "taker_bps": 2}]

    with pytest.raises(ValueError, match="start at volume 0"):
        VenueConfig.model_validate(base)


def test_appconfig_defaults_are_valid() -> None:
    cfg = AppConfig(venues={})
    assert cfg.raw_dir == Path("data") / "raw"
    assert cfg.processed_dir == Path("data") / "processed"
