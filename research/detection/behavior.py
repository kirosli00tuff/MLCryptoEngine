"""Post-launch behavioural features from signature metadata (C.24 Task 3).

C.23 closed the T0 question: launch-window state separates hard rugs but not
honest candidates from soft/slow rugs. C.20's lifetimes imply the divergence is
post-launch, so this module scores *early trading behaviour* after launch at a
cutoff ``T0 + X`` and asks the survivor-conditioned question: **given a pool
alive at the cutoff, does it rug afterward?**

**Signature-metadata only, by measurement.** C.24's cost probe found that
``getSignaturesForAddress`` returns ``{signature, slot, err, memo, blockTime,
confirmationStatus}`` and **no signer or account list** — so "unique signers" and
"share of activity from launch-window addresses" are *not* derivable from the
cheap signature class (they need enhanced detail at ~100x the cost, which the
14,029-credit budget cannot fund at scale). The features here are the ones the
cheap class actually supports: counts, arrival rate, decay, burst spread, gaps,
quiet-time at the cutoff, and the failed-transaction share. ``unique_active_minutes``
stands in for the unavailable unique-signer growth as a burstiness proxy.

**The cutoff leakage rule (registered before data, ADR in Task 6).** Every
feature reads strictly signatures with ``blockTime < cutoff``; the cutoff sits
strictly before the label event. :func:`cutoff_end` refuses a pool whose label
event falls at or before the cutoff — that pool already rugged, so it is not
"alive at X" and cannot be scored. ``tests/test_detection_behavior.py`` plants
activity after the cutoff and asserts no feature moves.
"""

from __future__ import annotations

from dataclasses import dataclass

MINUTE = 60.0


class CutoffLeakError(RuntimeError):
    """The label event falls at or before the cutoff: the pool is not alive at X."""


@dataclass(frozen=True)
class Sig:
    """One signature's cheap metadata: block time and whether the tx errored."""

    ts_s: float
    err: bool = False


def cutoff_end(t0_s: float, x_seconds: float, label_event_s: float | None) -> float:
    """``T0 + X``, or a refusal if the label event is not strictly after it.

    Survivor conditioning is enforced here, not downstream: a pool whose hard-rug
    event lands at or before the cutoff is excluded, never clamped in.
    """
    end = t0_s + x_seconds
    if label_event_s is not None and label_event_s <= end:
        raise CutoffLeakError(
            f"label event at {label_event_s:.0f}s is at or before the cutoff {end:.0f}s; "
            f"the pool is not alive at T0+{x_seconds:.0f}s and is EXCLUDED, never clamped"
        )
    return end


def behavioral_features(
    sigs: list[Sig], t0_s: float, x_seconds: float, label_event_s: float | None
) -> dict[str, float]:
    """Signature-metadata features over ``[T0, T0+X]``, read strictly before the cutoff."""
    end = cutoff_end(t0_s, x_seconds, label_event_s)
    # Strictly before the cutoff: a signature at exactly T0+X is at the cutoff,
    # not before it, so it is excluded (the registered "reads strictly before X").
    win = sorted((s for s in sigs if t0_s <= s.ts_s < end), key=lambda s: s.ts_s)
    n = len(win)
    minutes = x_seconds / MINUTE
    if n == 0:
        # No activity in the window: a real, informative state (a pool that went
        # silent), encoded explicitly rather than as missing.
        return {
            "n_tx": 0.0,
            "tx_per_min": 0.0,
            "rate_decay": 1.0,
            "unique_active_minutes": 0.0,
            "max_gap_s": x_seconds,
            "time_since_last_at_cutoff_s": x_seconds,
            "err_fraction": 0.0,
        }
    ts = [s.ts_s for s in win]
    third = x_seconds / 3.0
    first_third = sum(1 for t in ts if t <= t0_s + third)
    last_third = sum(1 for t in ts if t > t0_s + 2.0 * third)
    gaps = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    return {
        "n_tx": float(n),
        "tx_per_min": n / minutes,
        # >1 means activity grew across the window, <1 means it faded (a rug tell).
        "rate_decay": (last_third + 1) / (first_third + 1),
        "unique_active_minutes": float(len({int((t - t0_s) // MINUTE) for t in ts})),
        "max_gap_s": max(gaps) if gaps else x_seconds,
        "time_since_last_at_cutoff_s": end - ts[-1],
        "err_fraction": sum(1 for s in win if s.err) / n,
    }
