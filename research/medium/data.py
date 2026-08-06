"""Free-source acquisition and the C.17 availability audit.

Every candidate source is probed before anything is designed around it, and
what lands on disk is immutable raw with source, URL, sha256 and retrieval
date in the C.10 manifest. Two properties differ from earlier archives and are
handled explicitly:

**These files are living snapshots, not closed months.** A Coin Metrics
community CSV is regenerated daily and past rows can be revised; DefiLlama's
stablecoin history is a reconstruction that revises too. A dated filename per
retrieval keeps each snapshot immutable while admitting that yesterday's
snapshot and today's may disagree about last year — which is exactly the
revision behaviour the audit records, and one of the two reasons every feature
carries a publication lag.

**License is part of availability.** Coin Metrics community data ships under
CC BY-NC 4.0 — fine for personal research, recorded so a future commercial use
trips over the note rather than the license.
"""

from __future__ import annotations

import csv
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from data.archive import manifest
from data.archive.http import fetch_to_file
from data.config import AppConfig

CM_SOURCE = "coinmetrics_community"
CM_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/{asset}.csv"
LLAMA_SOURCE = "defillama_stablecoins"
LLAMA_URL = "https://stablecoins.llama.fi/stablecoincharts/all"

MS_PER_DAY = 86_400_000


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _day_stamp(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _fetch_snapshot(
    cfg: AppConfig, source: str, dataset: str, symbol: str, url: str, target: Path
) -> Path:
    """One dated immutable snapshot + manifest line; today's file is reused."""
    if manifest.already_have(target):
        return target
    size, sha = fetch_to_file(url, target)
    manifest.append(
        cfg,
        manifest.ArchiveRecord(
            source=source,
            venue=source.split("_")[0],
            dataset=dataset,
            symbol=symbol,
            interval="1d",
            period=_today(),
            url=url,
            path=str(target.relative_to(cfg.data_root)),
            size_bytes=size,
            sha256=sha,
            retrieved_at=manifest.utc_stamp(),
        ),
    )
    return target


def fetch_coinmetrics_asset(cfg: AppConfig, asset: str) -> Path:
    target = (
        manifest.archive_dir(cfg) / "coinmetrics" / f"asset={asset}" / f"{asset}_{_today()}.csv"
    )
    return _fetch_snapshot(
        cfg, CM_SOURCE, "community/csv", asset, CM_URL.format(asset=asset), target
    )


def fetch_defillama_stablecoins(cfg: AppConfig) -> Path:
    target = manifest.archive_dir(cfg) / "defillama" / "stablecoins" / f"all_{_today()}.json"
    return _fetch_snapshot(cfg, LLAMA_SOURCE, "stablecoincharts/all", "ALL", LLAMA_URL, target)


def load_coinmetrics(path: Path) -> dict[str, dict[int, float]]:
    """Column -> {UTC-midnight epoch ms -> value}. Empty cells are absent, not 0."""
    out: dict[str, dict[int, float]] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            stamp = row.get("time") or ""
            try:
                day = datetime.strptime(stamp[:10], "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                continue
            day_ms = int(day.timestamp() * 1000)
            for key, value in row.items():
                if key == "time" or value in ("", None):
                    continue
                try:
                    out.setdefault(key, {})[day_ms] = float(value)
                except ValueError:
                    continue
    return out


def load_defillama(path: Path) -> dict[int, float]:
    """Total stablecoin circulating USD (peggedUSD) by UTC day, epoch ms."""
    out: dict[int, float] = {}
    for row in orjson.loads(path.read_bytes()):
        value = (row.get("totalCirculatingUSD") or {}).get("peggedUSD")
        if value is None:
            continue
        day_ms = (int(row["date"]) * 1000 // MS_PER_DAY) * MS_PER_DAY
        out[day_ms] = float(value)
    return out


def _probe_once(url: str) -> str:
    """Single-shot GET for the audit record. Never retried — the answer IS the probe."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "MLCryptoEngine/0.1 (personal quantitative research)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read(400)
            return f"HTTP {response.status}, {len(body)}B sample"
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}"
    except Exception as exc:
        return f"{type(exc).__name__}"


def _span(days: dict[int, float]) -> dict[str, Any]:
    if not days:
        return {"observations": 0}
    keys = sorted(days)
    return {"observations": len(keys), "first": _day_stamp(keys[0]), "last": _day_stamp(keys[-1])}


def audit(cfg: AppConfig) -> dict[str, Any]:
    """Task 2: what exists free, per source — before anything is designed around it."""
    out: dict[str, Any] = {}

    cm: dict[str, Any] = {
        "granularity": "daily",
        "license": "CC BY-NC 4.0 (community data) — personal research OK, non-commercial",
        "publication_lag": (
            "regenerated daily after UTC close; exact delay undocumented -> registered "
            "lag +1 day beyond metric date"
        ),
        "revision_behavior": "whole-file regeneration; past rows can and do revise",
    }
    for asset in ("btc", "eth"):
        path = fetch_coinmetrics_asset(cfg, asset)
        columns = load_coinmetrics(path)
        flow_columns = sorted(
            c for c in columns if c.startswith(("Flow", "SplyEx")) or "FlowEx" in c
        )
        cm[asset] = {
            "path": str(path),
            "metrics": len(columns),
            "exchange_flow_columns": flow_columns,
            "span": _span(next(iter(columns.values()), {})),
        }
    cm["exchange_netflow_available"] = bool(
        cm["btc"]["exchange_flow_columns"] and cm["eth"]["exchange_flow_columns"]
    )
    out["coinmetrics_community"] = cm

    llama_path = fetch_defillama_stablecoins(cfg)
    supply = load_defillama(llama_path)
    out["defillama_stablecoins"] = {
        "path": str(llama_path),
        "granularity": "daily",
        "license": "free public API, no key",
        "publication_lag": (
            "series reconstructed continuously; registered lag +1 day beyond metric date"
        ),
        "revision_behavior": "reconstructed history — past values revise with methodology",
        "span": _span(supply),
    }

    out["cryptoquant_free_tier"] = {
        "probe": _probe_once("https://api.cryptoquant.com/v1/btc/exchange-flows/netflow"),
        "verdict": "requires an account API key even at the free tier — not freely scriptable",
    }
    out["blockchain_com_charts"] = {
        "probe": _probe_once(
            "https://api.blockchain.info/charts/n-transactions?timespan=1year&format=json"
        ),
        "verdict": "BTC-only network metrics; no exchange-flow series exists on this API",
    }
    out["coingecko"] = {
        "probe": _probe_once(
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=30"
        ),
        "verdict": (
            "not needed: BTC/ETH daily price history already on disk from the C.10 Binance "
            "archive, which is also survivorship-audited"
        ),
    }
    out["exchange_published_flow_data"] = {
        "verdict": "no reachable exchange publishes wallet-flow history as a free feed"
    }
    return out
