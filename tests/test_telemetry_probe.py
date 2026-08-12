"""probe_once: method/body plumbing and failure accounting (Stage D.1b)."""

from __future__ import annotations

import asyncio

import httpx

from ops.telemetry.probe import probe_once


def _probe(handler: httpx.MockTransport, **kwargs: object) -> tuple[float, bool, str | None]:
    async def go() -> tuple[float, bool, str | None]:
        async with httpx.AsyncClient(transport=handler) as client:
            return await probe_once(client, "https://venue.test/info", 1.0, **kwargs)  # type: ignore[arg-type]

    return asyncio.run(go())


def test_post_probe_sends_json_body_and_succeeds() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["body"] = request.content
        return httpx.Response(200, json={"levels": []})

    rtt_ms, ok, error = _probe(
        httpx.MockTransport(handler),
        method="POST",
        json_body={"type": "l2Book", "coin": "BTC"},
    )
    assert ok and error is None and rtt_ms >= 0.0
    assert seen["method"] == "POST"
    assert b"l2Book" in seen["body"]  # type: ignore[operator]


def test_default_method_stays_get() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        return httpx.Response(200, text="ok")

    _, ok, _ = _probe(httpx.MockTransport(handler))
    assert ok and seen["method"] == "GET"


def test_http_4xx_counts_as_failed_sample_not_dropped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(405)

    rtt_ms, ok, error = _probe(httpx.MockTransport(handler))
    assert not ok and error == "HTTP 405" and rtt_ms >= 0.0
