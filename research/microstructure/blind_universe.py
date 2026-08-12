"""The D.1b blind universe rule: registered before retrieval, blind to spread.

D.1c found the C.9 instrument selection was a spread-motivated screen, so its
survivors are demoted to screened positives until an unbiased selection is
scored. This module *is* the unbiased rule, committed before the ranking it
applies to was retrieved (report.md §D.1b): volume bands from the venue's own
24-hour notional ranking, all-or-seeded-sample within each band, seed fixed
here.

Blindness is structural, not promised: :func:`extract_assets` reduces the
venue payload to exactly three fields per asset — ``name``, ``isDelisted``,
``dayNtlVlm`` — and :func:`select_universe` accepts only that reduction, so no
spread, impact, mid, mark, or funding field can reach the rule. A test
perturbs every price-like field in the raw payload and asserts the selection
is unchanged.

PUMP and MERL are carried over regardless of the draw — the existing series
stays continuous — and are marked as carried-over, never as blind picks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from random import Random
from typing import Any

import httpx

SEED = 20260812
CARRYOVER: tuple[str, ...] = ("PUMP", "MERL")
# Below $10k/day a book cannot meet the 150-trade/day capacity floor
# registered at C.18; measuring it answers nothing H6 asks.
MIN_BAND_USD = 10_000.0
INFO_URL = "https://api.hyperliquid.xyz/info"


@dataclass(frozen=True)
class Band:
    """One 24h-notional band: [lo_usd, hi_usd), sampled to at most cap names."""

    name: str
    lo_usd: float
    hi_usd: float
    cap: int


BANDS: tuple[Band, ...] = (
    Band("B0", 100_000_000.0, float("inf"), 3),
    Band("B1", 10_000_000.0, 100_000_000.0, 5),
    Band("B2", 1_000_000.0, 10_000_000.0, 5),
    Band("B3", 100_000.0, 1_000_000.0, 6),
    Band("B4", MIN_BAND_USD, 100_000.0, 6),
)


@dataclass(frozen=True)
class Asset:
    """The only three fields the rule is permitted to read."""

    name: str
    is_delisted: bool
    day_ntl_vlm: float


def extract_assets(meta_and_ctxs: list[Any]) -> list[Asset]:
    """Reduce the raw ``metaAndAssetCtxs`` payload to the blind fields only."""
    universe = meta_and_ctxs[0]["universe"]
    ctxs = meta_and_ctxs[1]
    if len(universe) != len(ctxs):
        raise ValueError(
            f"universe ({len(universe)}) and assetCtxs ({len(ctxs)}) lengths differ; "
            "the two arrays are index-aligned and must match"
        )
    return [
        Asset(
            name=str(entry["name"]),
            is_delisted=bool(entry.get("isDelisted", False)),
            day_ntl_vlm=float(ctx["dayNtlVlm"]),
        )
        for entry, ctx in zip(universe, ctxs, strict=True)
    ]


def band_of(volume_usd: float) -> Band | None:
    """The band holding ``volume_usd``, or None below the registered floor."""
    for band in BANDS:
        if band.lo_usd <= volume_usd < band.hi_usd:
            return band
    return None


def select_universe(assets: list[Asset], seed: int = SEED) -> dict[str, Any]:
    """Apply the registered rule. Deterministic for a given payload and seed.

    Per-band generators are seeded independently (``"{seed}:{band}"``) so one
    band's membership size cannot shift another band's draw.
    """
    members: dict[str, list[str]] = {band.name: [] for band in BANDS}
    for asset in assets:
        if asset.is_delisted:
            continue
        band = band_of(asset.day_ntl_vlm)
        if band is not None:
            members[band.name].append(asset.name)

    selected: dict[str, list[str]] = {}
    for band in BANDS:
        names = sorted(members[band.name])
        if len(names) <= band.cap:
            selected[band.name] = names
        else:
            selected[band.name] = sorted(Random(f"{seed}:{band.name}").sample(names, band.cap))

    picks = [name for band in BANDS for name in selected[band.name]]
    return {
        "seed": seed,
        "band_member_counts": {band.name: len(members[band.name]) for band in BANDS},
        "selected_per_band": selected,
        "blind_picks": picks,
        "carried_over_not_blind": [c for c in CARRYOVER if c not in picks],
        "subscribe": sorted(set(picks) | set(CARRYOVER)),
    }


def main() -> None:
    """Fetch the live ranking once and print the selection as JSON."""
    response = httpx.post(INFO_URL, json={"type": "metaAndAssetCtxs"}, timeout=10.0)
    response.raise_for_status()
    result = select_universe(extract_assets(response.json()))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
