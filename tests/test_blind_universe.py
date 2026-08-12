"""D.1b blind universe rule: band edges, determinism, blindness, carryover."""

from __future__ import annotations

from typing import Any

import pytest

from research.microstructure.blind_universe import (
    BANDS,
    SEED,
    Asset,
    band_of,
    extract_assets,
    select_universe,
)


def _payload(rows: list[tuple[str, bool, float]]) -> list[Any]:
    """A metaAndAssetCtxs-shaped payload carrying price-like decoy fields."""
    universe = [{"name": n, "szDecimals": 0, "isDelisted": d} for n, d, _ in rows]
    ctxs = [
        {
            "dayNtlVlm": str(v),
            "impactPxs": ["1.0", "2.0"],
            "markPx": "1.5",
            "midPx": "1.5",
            "funding": "0.0000125",
        }
        for _, _, v in rows
    ]
    return [{"universe": universe}, ctxs]


class TestBands:
    def test_lower_bound_inclusive_upper_exclusive(self) -> None:
        b3 = band_of(100_000.0)
        b4 = band_of(99_999.99)
        b0 = band_of(100_000_000.0)
        assert b3 is not None and b3.name == "B3"
        assert b4 is not None and b4.name == "B4"
        assert b0 is not None and b0.name == "B0"

    def test_below_floor_excluded(self) -> None:
        assert band_of(9_999.99) is None

    def test_caps_are_the_registered_ones(self) -> None:
        assert [(b.name, b.cap) for b in BANDS] == [
            ("B0", 3),
            ("B1", 5),
            ("B2", 5),
            ("B3", 6),
            ("B4", 6),
        ]


class TestSelection:
    def test_takes_all_when_band_at_or_under_cap(self) -> None:
        rows = [(f"C{i}", False, 200_000.0) for i in range(6)]
        result = select_universe(extract_assets(_payload(rows)))
        assert result["selected_per_band"]["B3"] == sorted(f"C{i}" for i in range(6))

    def test_seeded_sample_is_deterministic_and_capped(self) -> None:
        rows = [(f"C{i:02d}", False, 200_000.0) for i in range(20)]
        first = select_universe(extract_assets(_payload(rows)))
        second = select_universe(extract_assets(_payload(rows)))
        assert first["selected_per_band"]["B3"] == second["selected_per_band"]["B3"]
        assert len(first["selected_per_band"]["B3"]) == 6

    def test_delisted_excluded(self) -> None:
        rows = [("LIVE", False, 200_000.0), ("DEAD", True, 200_000.0)]
        result = select_universe(extract_assets(_payload(rows)))
        assert result["blind_picks"] == ["LIVE"]

    def test_blind_to_every_price_like_field(self) -> None:
        # Arrange: same names/volumes, wildly different price-like decoys.
        rows = [(f"C{i:02d}", False, 200_000.0) for i in range(20)]
        payload_a = _payload(rows)
        payload_b = _payload(rows)
        for ctx in payload_b[1]:
            ctx["impactPxs"] = ["999.0", "9999.0"]
            ctx["markPx"] = "777.7"
            ctx["midPx"] = "888.8"
            ctx["funding"] = "-0.5"
        # Act / Assert: the selection cannot see any of it.
        assert select_universe(extract_assets(payload_a)) == select_universe(
            extract_assets(payload_b)
        )

    def test_carryover_subscribed_and_marked_not_blind(self) -> None:
        rows = [(f"C{i:02d}", False, 200_000.0) for i in range(20)]
        result = select_universe(extract_assets(_payload(rows)))
        assert "PUMP" not in result["blind_picks"]
        assert set(result["carried_over_not_blind"]) == {"PUMP", "MERL"}
        assert {"PUMP", "MERL"} <= set(result["subscribe"])

    def test_seed_is_the_registered_one(self) -> None:
        assert SEED == 20260812

    def test_misaligned_payload_raises(self) -> None:
        payload = _payload([("A", False, 200_000.0)])
        payload[1].append({"dayNtlVlm": "1.0"})
        with pytest.raises(ValueError):
            extract_assets(payload)

    def test_asset_reduction_carries_only_blind_fields(self) -> None:
        asset = extract_assets(_payload([("A", False, 123.0)]))[0]
        assert asset == Asset(name="A", is_delisted=False, day_ntl_vlm=123.0)
