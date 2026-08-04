"""Which venue-days a validation run scores, and why it skips the rest.

Two venue kinds coexist in ``config/venues.yaml`` and they are validated by
different machinery:

- **recorder** venues are captured live into ``data/raw/venue=<venue>/`` and
  replayed by :mod:`data.validate.replay`;
- **vendor** venues have no recorder at all — their days are purchased and
  stored under ``data/vendor/`` and scored by :mod:`data.databento.validate`.

Before this module existed the CLI treated every configured venue as
replayable, so adding ``cme`` to the venue list made
``python -m data.validate --date <today>`` raise before validating *anything*.
The failure was maximally unhelpful: the run aborted on the one venue that was
never going to have raw capture, and took the three healthy venues with it.

Three outcomes, kept strictly apart:

1. **Replay it.** A recorder venue with recorded data for the date.
2. **Skip it, and say why.** A venue with nothing to score for that date. Normal
   and permanent for a vendor venue swept into a default run; ordinary for a
   recorder venue on a date before it was switched on. Never an error.
3. **Fail loudly.** A recorder venue with no replay parser behind it — see
   :class:`~data.validate.replay.VenueConfigurationError`. Something is
   misconfigured, and a run that quietly skipped it would let a venue stop being
   validated with nobody noticing.

Vendor venues are only scored when named explicitly with ``--venue``. A default
sweep skips them, because streaming stored DBN is a different and far more
expensive operation than replaying a day of raw capture — the stored range files
run to gigabytes each — and silently doing it on every ``make validate`` would
be a nasty surprise. Asking for it by name gets it.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.config import AppConfig, VenueKind
from data.databento.ingest import DATASET, vendor_dir
from data.recorder.reader import available_dates
from data.validate.replay import VenueConfigurationError, replay_supported

# The depth schema the research pipeline consumes, and so the one whose
# coverage and integrity a vendor day is scored on. Trade and bbo-1s files may
# sit beside it; they are not the book.
VENDOR_SCHEMA = "mbp-10"
_VENDOR_SUFFIX = f".{VENDOR_SCHEMA}.dbn.zst"


@dataclass(frozen=True)
class RecorderDay:
    """One recorder venue-day to replay from raw capture."""

    venue: str
    date: str


@dataclass(frozen=True)
class VendorDay:
    """One stored vendor contract-day to score from its DBN file."""

    venue: str
    symbol: str
    date: str
    schema: str = VENDOR_SCHEMA


@dataclass(frozen=True)
class Skipped:
    """A venue scope that produced nothing to score, and the reason."""

    venue: str
    kind: VenueKind
    reason: str


@dataclass(frozen=True)
class RunPlan:
    """Everything a validation run will do, decided before it does any of it."""

    recorder_days: list[RecorderDay]
    vendor_days: list[VendorDay]
    skipped: list[Skipped]

    @property
    def is_empty(self) -> bool:
        return not self.recorder_days and not self.vendor_days


def vendor_dates(cfg: AppConfig) -> list[str]:
    """UTC dates with at least one stored per-day vendor file, oldest first.

    Only ``date=`` directories are enumerated. Multi-day ``range=`` files are
    deliberately excluded: scoring one day out of a month-long file means
    streaming the whole file, which belongs to
    :func:`data.databento.validate.validate_vendor_range` and its own explicit
    invocation, not to a per-day loop.
    """
    root = vendor_dir(cfg) / DATASET
    if not root.is_dir():
        return []
    return sorted(
        path.name.removeprefix("date=")
        for path in root.iterdir()
        if path.is_dir() and path.name.startswith("date=")
    )


def vendor_symbols_on(cfg: AppConfig, date: str) -> list[str]:
    """Contract symbols with a stored depth file for ``date``, read off disk.

    Taken from the filenames rather than from configured symbols, so the plan
    describes what is actually there. ``vendor_path`` writes the symbol with
    dots replaced by underscores (``MBT.c.0`` -> ``MBT_c_0``); this reverses
    that, which is exact for CME continuous symbols since none contain a
    literal underscore.
    """
    day_dir = vendor_dir(cfg) / DATASET / f"date={date}"
    if not day_dir.is_dir():
        return []
    return sorted(
        path.name.removesuffix(_VENDOR_SUFFIX).replace("_", ".")
        for path in day_dir.iterdir()
        if path.is_file() and path.name.endswith(_VENDOR_SUFFIX)
    )


def _recorder_scope(
    cfg: AppConfig, venue: str, dates: list[str] | None
) -> tuple[list[RecorderDay], list[Skipped]]:
    if not replay_supported(venue):
        raise VenueConfigurationError(
            f"venue '{venue}' is declared kind='recorder' but nothing can replay it. "
            "Either register a parser in data.validate.replay.PARSE_FNS or declare it "
            "kind='vendor' in config/venues.yaml. Skipping it silently would let a "
            "venue drop out of validation unnoticed."
        )
    recorded = available_dates(cfg.raw_dir, venue)
    wanted = [d for d in dates if d in recorded] if dates is not None else recorded
    if wanted:
        return [RecorderDay(venue=venue, date=d) for d in wanted], []
    if dates is None:
        reason = f"no recorded data under {cfg.raw_dir}"
    else:
        reason = (
            f"no recorded data for {', '.join(dates)} "
            f"({len(recorded)} other recorded date(s) under {cfg.raw_dir})"
        )
    return [], [Skipped(venue=venue, kind="recorder", reason=reason)]


def _vendor_scope(
    cfg: AppConfig, venue: str, dates: list[str] | None, *, requested: bool
) -> tuple[list[VendorDay], list[Skipped]]:
    if not requested:
        return [], [
            Skipped(
                venue=venue,
                kind="vendor",
                reason=(
                    "vendor-backfill venue, not captured live — it has no raw data on any "
                    "date by design. Stored vendor days are scored on request: "
                    f"`python -m data.validate --venue {venue} --date YYYY-MM-DD`"
                ),
            )
        ]
    on_disk = vendor_dates(cfg)
    wanted = [d for d in dates if d in on_disk] if dates is not None else on_disk
    days = [
        VendorDay(venue=venue, symbol=symbol, date=date)
        for date in wanted
        for symbol in vendor_symbols_on(cfg, date)
    ]
    if days:
        return days, []
    scope = ", ".join(dates) if dates is not None else "any date"
    return [], [
        Skipped(
            venue=venue,
            kind="vendor",
            reason=(
                f"no stored {VENDOR_SCHEMA} vendor day file for {scope} under "
                f"{vendor_dir(cfg) / DATASET}. Multi-day range= files are not scored "
                "per day; use data.databento.validate.validate_vendor_range for those."
            ),
        )
    ]


def _archive_skips(cfg: AppConfig) -> list[Skipped]:
    """Report configured archives so a sweep never silently omits them.

    An archive is never replayed and never scored here — it is downloaded bars,
    not capture. But ADR-027's rule holds: a source invisible to the validator
    is a source nobody notices has stopped being refreshed. Listing them costs
    one line each and keeps the report's venue count honest.
    """
    return [
        Skipped(
            venue=key,
            kind=source.kind,
            reason=(
                f"free public bar archive for {source.venue} ({source.name}) — downloaded "
                "history, never captured and never traded, so there is nothing to replay. "
                "Integrity is checked at ingest by data.archive, not here."
            ),
        )
        for key, source in sorted(cfg.sources.items())
    ]


def plan_run(
    cfg: AppConfig,
    venues: list[str] | None = None,
    dates: list[str] | None = None,
) -> RunPlan:
    """Decide the whole run up front: what to replay, what to score, what to skip.

    ``venues=None`` means every configured venue (a default sweep); an explicit
    list means the operator named them, which is what unlocks vendor scoring.
    ``dates=None`` means every date each venue has data for.

    Raises :class:`~data.validate.replay.VenueConfigurationError` for an unknown
    venue key or a recorder venue with no parser. Everything else that produces
    no work lands in :attr:`RunPlan.skipped` with a reason.
    """
    requested = venues is not None
    selected = venues if venues is not None else sorted(cfg.venues)

    recorder_days: list[RecorderDay] = []
    vendor_days: list[VendorDay] = []
    # Archives are listed only on a default sweep: naming venues explicitly is
    # a request for those venues, and padding that answer with unrelated
    # archives would be noise.
    skipped: list[Skipped] = [] if requested else _archive_skips(cfg)
    for venue in selected:
        vcfg = cfg.venues.get(venue)
        if vcfg is None:
            raise VenueConfigurationError(
                f"unknown venue '{venue}' (configured: {', '.join(sorted(cfg.venues))})"
            )
        if vcfg.kind == "vendor":
            vendor, skips = _vendor_scope(cfg, venue, dates, requested=requested)
            vendor_days.extend(vendor)
        else:
            replays, skips = _recorder_scope(cfg, venue, dates)
            recorder_days.extend(replays)
        skipped.extend(skips)
    return RunPlan(recorder_days=recorder_days, vendor_days=vendor_days, skipped=skipped)
