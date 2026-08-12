"""Retired venue kind (Stage D.1b): no process, no heartbeat, still replayable."""

from __future__ import annotations

from data.config import FeeTier, SnapshotBehaviour, VenueConfig, load_config
from data.recorder.service import default_venue_keys
from data.validate.scope import plan_run


def _venue(kind: str) -> VenueConfig:
    return VenueConfig(
        name="X",
        ws_url="wss://x.test",
        rest_status_url="https://x.test",
        symbols=["A"],
        book_depth=10,
        snapshot=SnapshotBehaviour(on_subscribe=True, checksum=False, notes="t"),
        aws_region="eu-west-2",
        fee_tiers=[FeeTier(volume_usd_30d=0, maker_bps=1.0, taker_bps=2.0)],
        kind=kind,  # type: ignore[arg-type]
    )


class TestDefaultVenueKeys:
    def test_retired_venue_not_started_by_default(self) -> None:
        venues = {
            "kraken": _venue("retired"),
            "coinbase": _venue("retired"),
            "hyperliquid": _venue("recorder"),
        }
        assert default_venue_keys(venues) == ["hyperliquid"]

    def test_repo_config_records_hyperliquid_only(self) -> None:
        cfg = load_config()
        assert default_venue_keys(cfg.venues) == ["hyperliquid"]
        assert cfg.venues["kraken"].kind == "retired"
        assert cfg.venues["coinbase"].kind == "retired"

    def test_carryover_and_blind_universe_subscribed(self) -> None:
        cfg = load_config()
        symbols = set(cfg.venues["hyperliquid"].symbols)
        # Carried-over survivors keep their series; NOT re-entered as a blind pick.
        assert {"PUMP", "MERL", "NOT", "BTC", "ETH"} <= symbols
        assert len(symbols) == 27


class TestRetiredStaysValidatable:
    def test_scope_plans_retired_days_as_replays_never_vendor_skips(self) -> None:
        # A retired venue named explicitly must route to the recorder replay
        # path (or a no-data skip) — never the vendor branch and never an
        # abort. This is the C.9.1 distinction extended to retirement.
        cfg = load_config()
        plan = plan_run(cfg, venues=["kraken"], dates=["2026-07-31"])
        planned = [d for d in plan.recorder_days if d.venue == "kraken"]
        skipped = [s for s in plan.skipped if s.venue == "kraken"]
        assert planned or skipped
        assert not plan.vendor_days
        for skip in skipped:
            assert "vendor" not in skip.reason
