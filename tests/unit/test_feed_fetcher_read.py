"""Tests for read_body_capped — the size-capped streaming body read.

Bodies arrive in several chunks, and aiohttp's StreamReader.read(n) returns
only what is already buffered. Capping that way truncated real feeds without
raising anything: BBC News parsed as 4 of its 37 entries, the Guardian as 8 of
45, while smaller feeds that fit one chunk were unaffected — so every offline
fixture passed.
"""

from newsflow.core.feed_fetcher import read_body_capped


class _ChunkedStream:
    """Minimal StreamReader stand-in that hands back a fixed chunk list."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def iter_chunked(self, size: int):
        for chunk in self.chunks:
            yield chunk


async def test_joins_every_chunk():
    stream = _ChunkedStream([b"<rss>", b"<item>one</item>", b"<item>two</item>", b"</rss>"])
    assert await read_body_capped(stream) == b"<rss><item>one</item><item>two</item></rss>"


async def test_empty_body_is_not_an_error():
    assert await read_body_capped(_ChunkedStream([])) == b""


async def test_over_the_cap_returns_none():
    stream = _ChunkedStream([b"x" * 100, b"y" * 100])
    assert await read_body_capped(stream, cap=150) is None


async def test_exactly_at_the_cap_is_kept():
    """The cap is a ceiling, not an exclusive bound — a body of exactly cap
    bytes is a legal feed, not an oversize one."""
    stream = _ChunkedStream([b"x" * 100, b"y" * 50])
    assert await read_body_capped(stream, cap=150) == b"x" * 100 + b"y" * 50


async def test_stops_reading_once_over_the_cap():
    """The point of the cap is bounded memory: a server streaming forever must
    not be drained into the buffer first and rejected after."""
    stream = _ChunkedStream([b"x" * 100, b"y" * 100, b"z" * 100])
    consumed = []

    async def counting_iter(size: int):
        for chunk in stream.chunks:
            consumed.append(chunk)
            yield chunk

    stream.iter_chunked = counting_iter  # type: ignore[assignment]
    assert await read_body_capped(stream, cap=150) is None
    assert len(consumed) == 2  # third chunk never requested
