"""Tests for the webhook payload converters.

These are pure data-transform tests — no I/O, no DB. They guard the wire
contract with Slack / ntfy / Feishu / WeCom so a refactor doesn't silently
ship malformed payloads to third parties.
"""

import json
from datetime import UTC, datetime

from newsflow.adapters.base import Message
from newsflow.adapters.webhook.formats import (
    SUPPORTED_FORMATS,
    build_notification_payload,
    build_payload,
)


def _make_message(**overrides) -> Message:
    defaults = dict(
        title="Hello World",
        summary="A concise summary of what happened.",
        link="https://example.com/article?ref=rss&id=42",
        source="Example News",
        published_at=datetime(2026, 4, 23, 6, 0, tzinfo=UTC),
        image_url="https://example.com/cover.jpg",
        title_translated=None,
        summary_translated=None,
    )
    defaults.update(overrides)
    return Message(**defaults)


# ─── generic ─────────────────────────────────────────────────────────────────


def test_generic_entry_payload_has_required_shape():
    wire = build_payload("generic", _make_message())
    payload = json.loads(wire.body.decode("utf-8"))

    assert payload["event"] == "feed.entry.new"
    assert "timestamp" in payload
    entry = payload["entry"]
    assert entry["title"] == "Hello World"
    assert entry["link"] == "https://example.com/article?ref=rss&id=42"
    assert entry["source"] == "Example News"
    assert entry["published_at"] == "2026-04-23T06:00:00+00:00"
    assert entry["image_url"] == "https://example.com/cover.jpg"
    assert wire.headers["Content-Type"].startswith("application/json")


def test_generic_passes_translations_through():
    msg = _make_message(title_translated="你好世界", summary_translated="简短摘要")
    wire = build_payload("generic", msg)
    entry = json.loads(wire.body)["entry"]
    assert entry["title_translated"] == "你好世界"
    assert entry["summary_translated"] == "简短摘要"


def test_generic_utf8_not_escaped():
    """ensure_ascii=False keeps CJK readable in the wire payload."""
    wire = build_payload("generic", _make_message(title="你好"))
    assert "你好".encode() in wire.body


def test_unknown_format_falls_back_to_generic():
    wire = build_payload("unknown-format-xyz", _make_message())
    assert json.loads(wire.body)["event"] == "feed.entry.new"


def test_generic_notification_payload():
    wire = build_notification_payload("generic", "the feed was auto-disabled")
    payload = json.loads(wire.body)
    assert payload["event"] == "system.notification"
    assert payload["text"] == "the feed was auto-disabled"


# ─── slack ───────────────────────────────────────────────────────────────────


def test_slack_produces_block_kit():
    wire = build_payload("slack", _make_message())
    payload = json.loads(wire.body)
    assert "blocks" in payload
    assert payload["blocks"][0]["type"] == "header"
    assert payload["blocks"][0]["text"]["text"] == "Hello World"
    # fallback text for notification clients that don't render blocks
    assert "text" in payload


def test_slack_header_truncated_to_150_chars():
    long_title = "x" * 500
    wire = build_payload("slack", _make_message(title=long_title))
    payload = json.loads(wire.body)
    header_text = payload["blocks"][0]["text"]["text"]
    assert len(header_text) <= 150


def test_slack_empty_summary_has_placeholder():
    """Block-kit section text can't be empty; placeholder avoids API 400."""
    wire = build_payload("slack", _make_message(summary="", summary_translated=None))
    payload = json.loads(wire.body)
    section_text = payload["blocks"][1]["text"]["text"]
    assert section_text  # non-empty


# ─── ntfy ────────────────────────────────────────────────────────────────────


def test_ntfy_body_is_plaintext_summary():
    wire = build_payload("ntfy", _make_message())
    assert wire.body == b"A concise summary of what happened."
    assert wire.headers["Content-Type"].startswith("text/plain")


def test_ntfy_sets_click_and_tags_headers():
    wire = build_payload("ntfy", _make_message())
    assert wire.headers["Click"] == "https://example.com/article?ref=rss&id=42"
    assert "rss" in wire.headers["Tags"]


def test_ntfy_title_rfc2047_for_non_ascii():
    """ntfy.sh decodes =?UTF-8?B?…?= back to the original string."""
    wire = build_payload("ntfy", _make_message(title="你好世界"))
    # RFC-2047 encoded-word shape. Exact bytes are base64 but always have
    # the =?UTF-8?…?= envelope.
    assert wire.headers["Title"].startswith("=?utf-8?")


def test_ntfy_attach_set_when_image_present():
    wire = build_payload("ntfy", _make_message())
    assert wire.headers["Attach"] == "https://example.com/cover.jpg"


def test_ntfy_notification_sets_high_priority():
    wire = build_notification_payload("ntfy", "feed disabled")
    assert wire.headers.get("Priority") == "high"


def test_ntfy_drops_click_with_control_chars():
    """A feed link with CR/LF must not reach the Click header — aiohttp would
    raise ValueError on send, wedging delivery to this destination."""
    wire = build_payload("ntfy", _make_message(link="https://example.com/\r\nX-Evil: 1"))
    assert "Click" not in wire.headers
    # The notification itself is still well-formed.
    assert wire.headers["Title"]
    assert wire.body


def test_ntfy_drops_non_http_and_non_ascii_click():
    assert "Click" not in build_payload("ntfy", _make_message(link="javascript:alert(1)")).headers
    # Non-latin-1 unicode in the URL would raise on header encode.
    assert (
        "Click" not in build_payload("ntfy", _make_message(link="https://example.com/文章")).headers
    )


def test_ntfy_drops_bad_attach_but_keeps_clean_one():
    wire = build_payload("ntfy", _make_message(image_url="https://example.com/a.jpg\nInjected: y"))
    assert "Attach" not in wire.headers
    # A clean image URL is still attached.
    clean = build_payload("ntfy", _make_message())
    assert clean.headers["Attach"] == "https://example.com/cover.jpg"


# ─── lark / feishu ───────────────────────────────────────────────────────────


def test_lark_builds_post_card():
    wire = build_payload("lark", _make_message())
    payload = json.loads(wire.body)
    assert payload["msg_type"] == "post"
    post = payload["content"]["post"]["zh_cn"]
    assert post["title"] == "Hello World"
    # Second line contains the "Read more" link
    link_line = post["content"][1]
    hrefs = [el.get("href") for el in link_line if el.get("tag") == "a"]
    assert hrefs == ["https://example.com/article?ref=rss&id=42"]


def test_lark_text_notification_is_simple():
    wire = build_notification_payload("lark", "disabled")
    payload = json.loads(wire.body)
    assert payload == {"msg_type": "text", "content": {"text": "disabled"}}


# ─── wecom ───────────────────────────────────────────────────────────────────


def test_wecom_builds_markdown():
    wire = build_payload("wecom", _make_message())
    payload = json.loads(wire.body)
    assert payload["msgtype"] == "markdown"
    content = payload["markdown"]["content"]
    assert "Hello World" in content
    assert "Example News" in content
    assert "https://example.com/article?ref=rss&id=42" in content


def test_wecom_summary_truncated():
    long_summary = "x" * 5000
    wire = build_payload("wecom", _make_message(summary=long_summary))
    content = json.loads(wire.body)["markdown"]["content"]
    # 1500 chars cap + header + footer + some overhead
    assert len(content) < 2000


# ─── discord ─────────────────────────────────────────────────────────────────


def test_discord_builds_embed():
    wire = build_payload("discord", _make_message())
    payload = json.loads(wire.body)
    embed = payload["embeds"][0]

    assert embed["title"] == "Hello World"
    assert embed["url"] == "https://example.com/article?ref=rss&id=42"
    assert embed["fields"][0]["value"] == "A concise summary of what happened."
    assert embed["footer"]["text"] == "Source: Example News"
    assert embed["image"]["url"] == "https://example.com/cover.jpg"
    assert embed["timestamp"] == "2026-04-23T06:00:00+00:00"


def test_discord_suppresses_every_mention():
    """Feed text rides in the embed, where mentions don't notify. The explicit
    empty parse list keeps an @everyone in a title from ever pinging."""
    wire = build_payload("discord", _make_message(title="@everyone read this"))
    payload = json.loads(wire.body)
    assert payload["allowed_mentions"] == {"parse": []}
    assert "content" not in payload


def test_discord_notification_suppresses_mentions_too():
    wire = build_notification_payload("discord", "the feed was auto-disabled")
    payload = json.loads(wire.body)
    assert payload["content"] == "the feed was auto-disabled"
    assert payload["allowed_mentions"] == {"parse": []}


def test_discord_respects_embed_limits():
    msg = _make_message(title="x" * 500, summary="y" * 5000)
    embed = json.loads(build_payload("discord", msg).body)["embeds"][0]
    assert len(embed["title"]) == 256
    assert len(embed["fields"][0]["value"]) == 1024


def test_discord_omits_non_http_link_and_image():
    """Discord rejects the whole payload on a malformed embed url, which would
    cost the article rather than just its link."""
    msg = _make_message(link="javascript:alert(1)", image_url="data:image/png;base64,AAAA")
    embed = json.loads(build_payload("discord", msg).body)["embeds"][0]
    assert "url" not in embed
    assert "image" not in embed
    assert embed["title"] == "Hello World"


def test_discord_omits_fields_when_summary_empty():
    msg = _make_message(summary="", summary_translated=None)
    embed = json.loads(build_payload("discord", msg).body)["embeds"][0]
    assert "fields" not in embed


def test_discord_naive_timestamp_gets_utc_offset():
    """SQLite hands back naive datetimes even for tz-aware columns; Discord
    rejects a timestamp with no offset."""
    msg = _make_message(published_at=datetime(2026, 4, 23, 6, 0))
    embed = json.loads(build_payload("discord", msg).body)["embeds"][0]
    assert embed["timestamp"].endswith("+00:00")


def test_discord_untitled_placeholder():
    embed = json.loads(build_payload("discord", _make_message(title="")).body)["embeds"][0]
    assert embed["title"] == "(untitled)"


# ─── matrix ──────────────────────────────────────────────────────────────────


def test_matrix_sends_text_and_html():
    wire = build_payload("matrix", _make_message())
    payload = json.loads(wire.body)

    # hookshot ignores `html` without a `text` fallback.
    assert "Hello World" in payload["text"]
    assert "A concise summary of what happened." in payload["text"]
    assert 'href="https://example.com/article?ref=rss&amp;id=42"' in payload["html"]
    assert "<b>" in payload["html"]


def test_matrix_escapes_feed_html():
    """Feed text lands in a formatted body — escaping here rather than trusting
    the client's tag whitelist."""
    msg = _make_message(title="<script>alert(1)</script>", summary='" onload="x')
    payload = json.loads(build_payload("matrix", msg).body)
    assert "<script>" not in payload["html"]
    assert "&lt;script&gt;" in payload["html"]
    assert ' onload="x' not in payload["html"]
    # The text fallback stays literal — it is never parsed as markup.
    assert "<script>alert(1)</script>" in payload["text"]


def test_matrix_plain_title_when_link_not_http():
    payload = json.loads(build_payload("matrix", _make_message(link="ftp://x/y")).body)
    assert "<a href" not in payload["html"]
    assert "<b>Hello World</b>" in payload["html"]


def test_matrix_text_notification_is_simple():
    wire = build_notification_payload("matrix", "disabled")
    assert json.loads(wire.body) == {"text": "disabled"}


# ─── meta ────────────────────────────────────────────────────────────────────


def test_all_named_formats_produce_valid_bytes():
    """Smoke: every declared format returns non-empty body + content type."""
    msg = _make_message()
    for fmt in SUPPORTED_FORMATS:
        wire = build_payload(fmt, msg)
        assert wire.body, f"{fmt}: empty body"
        assert wire.headers, f"{fmt}: empty headers"
        text_wire = build_notification_payload(fmt, "note")
        assert text_wire.body, f"{fmt} text: empty body"
