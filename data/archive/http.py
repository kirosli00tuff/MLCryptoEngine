"""Polite HTTP for public archives: streamed to disk, retried, rate limited.

Three properties this module exists to guarantee, each learned somewhere else
in this project:

- **Stream to a file, never into memory.** A download buffered in RAM is what
  OOM-killed the June vendor purchase after the charge had already committed
  (ADR-022). The same shape here would be cheaper but no less wrong.
- **Write to ``.partial``, rename on success.** A half-written file that keeps
  its final name is indistinguishable from a complete one on the next run.
- **Do not hammer a free endpoint.** These archives cost nothing and are
  offered as a courtesy. A fixed inter-request delay and a small concurrency
  cap keep this a well-behaved client; three live recorders share this host's
  network and matter more than a backfill finishing sooner.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_DELAY_S = 0.05
MAX_CONCURRENCY = 6
RETRIES = 3
RETRY_BACKOFF_S = 2.0
# A weight-based limiter (Hyperliquid allows ~1200 weight/minute per IP, and a
# fundingHistory call costs 20) needs a slower cadence and a longer, more
# patient backoff than an ordinary transport error does.
RATE_LIMIT_RETRIES = 6
RATE_LIMIT_BACKOFF_S = 10.0
POLITE_API_DELAY_S = 1.2
TIMEOUT_S = 60
CHUNK_BYTES = 1 << 16
USER_AGENT = "MLCryptoEngine/0.1 (personal quantitative research)"


class ArchiveFetchError(RuntimeError):
    """A download failed after retries, or returned something unusable."""


class RateLimited(ArchiveFetchError):
    """The endpoint asked us to slow down and we ran out of patience.

    Separate from a transport failure because the remedy is different: a slower
    request cadence, not a retry. Raised only after the backoff below has been
    exhausted, so seeing it means the configured delay is genuinely too fast
    for the endpoint rather than that one request was unlucky.
    """


class NotFound(ArchiveFetchError):
    """The archive has no file at this URL.

    Distinct from a transport failure on purpose. For a monthly bar file a 404
    is *information* — the symbol was not trading that month — and is how the
    universe learns when an asset was listed and when it died. Retrying it, or
    conflating it with a network error, would erase exactly the signal that
    makes a survivorship-free universe constructible.
    """


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def post_bytes(url: str, payload: bytes, *, delay_s: float = DEFAULT_DELAY_S) -> bytes:
    """POST a JSON body and return the response, retried like a GET.

    Hyperliquid's info endpoint is a POST-only JSON API rather than a file
    archive, so it needs its own verb. A 404 keeps the same meaning it has for
    a monthly file — the archive has nothing here — and is still not retried.
    """
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    last: Exception | None = None
    throttled = False
    for attempt in range(RATE_LIMIT_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                body: bytes = response.read()
            time.sleep(delay_s)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFound(url) from exc
            if exc.code == 429:
                throttled = True
                # Honour Retry-After when the server sends one; otherwise back
                # off geometrically. A weight-based limiter needs real seconds,
                # not the two-second nudge an ordinary transport error gets.
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                wait = float(retry_after) if retry_after and retry_after.isdigit() else 0.0
                time.sleep(max(wait, RATE_LIMIT_BACKOFF_S * (attempt + 1)))
                last = exc
                continue
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        else:
            return body
        time.sleep(RETRY_BACKOFF_S * (attempt + 1))
    if throttled:
        raise RateLimited(
            f"POST {url} still rate limited after {RATE_LIMIT_RETRIES} attempts. "
            f"Increase delay_s (currently {delay_s}s) rather than retrying harder."
        )
    raise ArchiveFetchError(f"POST {url} failed after {RATE_LIMIT_RETRIES} attempts: {last}")


def fetch_bytes(url: str, *, delay_s: float = DEFAULT_DELAY_S) -> bytes:
    """Fetch a small response into memory (directory listings, JSON APIs).

    For anything that could be large, use :func:`fetch_to_file` instead.
    """
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(_request(url), timeout=TIMEOUT_S) as response:
                body: bytes = response.read()
            time.sleep(delay_s)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFound(url) from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        else:
            return body
        time.sleep(RETRY_BACKOFF_S * (attempt + 1))
    raise ArchiveFetchError(f"{url} failed after {RETRIES} attempts: {last}")


def fetch_to_file(url: str, target: Path, *, delay_s: float = DEFAULT_DELAY_S) -> tuple[int, str]:
    """Stream ``url`` to ``target``; return ``(bytes_written, sha256)``.

    The checksum is computed over the stream as it is written, so it describes
    the bytes that actually landed rather than a re-read of them.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.parent / (target.name + ".partial")
    last: Exception | None = None
    for attempt in range(RETRIES):
        digest = hashlib.sha256()
        size = 0
        partial.unlink(missing_ok=True)
        try:
            with (
                urllib.request.urlopen(_request(url), timeout=TIMEOUT_S) as response,
                partial.open("wb") as fh,
            ):
                while chunk := response.read(CHUNK_BYTES):
                    digest.update(chunk)
                    size += len(chunk)
                    fh.write(chunk)
            time.sleep(delay_s)
        except urllib.error.HTTPError as exc:
            partial.unlink(missing_ok=True)
            if exc.code == 404:
                raise NotFound(url) from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            partial.unlink(missing_ok=True)
            last = exc
        else:
            if size == 0:
                partial.unlink(missing_ok=True)
                raise ArchiveFetchError(f"{url} returned an empty body")
            partial.replace(target)
            return size, digest.hexdigest()
        time.sleep(RETRY_BACKOFF_S * (attempt + 1))
    raise ArchiveFetchError(f"{url} failed after {RETRIES} attempts: {last}")
