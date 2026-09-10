"""AI editorial rewriting and optional image generation for AVEX channels."""

from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path
from typing import Any

from newsflow.config import get_settings

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {"en": "English", "fr": "French", "de": "German"}

SYSTEM_PROMPT = """You are the senior editor of a premium crypto-news Telegram channel.

Rewrite the supplied source article into a short, native-sounding Telegram news post.
Do NOT translate word-for-word. Write as a native editor in the requested language.

Required output, exactly:
TITLE: <concise headline, optionally starting with one relevant emoji>
BODY:
<2 to 4 substantive paragraphs>

Rules:
- The requested target language is absolute: write BOTH TITLE and BODY entirely in that language.
- Report facts only from the supplied source. Never invent facts, numbers, quotes, causes, background or implications.
- Preserve important numbers, percentages, token names, company names, dates and named institutions.
- Use the source article, not only its headline. Extract the key details that make the news useful.
- Prefer 2 to 4 paragraphs and normally 700-1400 characters in the BODY when the source contains enough information.
- Each paragraph should add a distinct fact or piece of context; do not repeat the headline.
- If the source is genuinely brief, stay factual rather than padding with generic commentary.
- The headline should state the main event clearly and naturally.
- Do not use markdown headings, bullet lists, hashtags, "Source", "Sources", URLs, or calls to action.
- Do not mention that you are an AI or that this is a rewrite.
- Avoid generic openings such as "According to reports" unless attribution itself is important.
- Avoid hype and price predictions unless explicitly present in the source.
- Use natural terminology used by professional crypto/financial journalists in the target language.
- Do not translate proper names, company names, exchange names or tickers unless there is a standard localized form.
- The BODY must contain only the finished post copy.
"""

IMAGE_PROMPT = """Create a clean editorial illustration for a professional cryptocurrency news Telegram channel.
The image should visually represent the news topic without reproducing logos or copyrighted artwork.
No text, no numbers, no captions, no watermarks, no UI screenshots.
Modern financial-news aesthetic, realistic or polished 3D editorial illustration, strong focal subject,
dark premium crypto atmosphere, square composition, suitable as a Telegram news image.
News headline: {title}
News summary: {summary}
"""


def _client() -> Any:
    from openai import AsyncOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for AVEX AI publishing")
    kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return AsyncOpenAI(**kwargs)


def _parse_rewrite(text: str) -> tuple[str, str] | None:
    text = text.strip()
    if "TITLE:" not in text or "BODY:" not in text:
        return None
    title_part, body = text.split("BODY:", 1)
    title = title_part.split("TITLE:", 1)[1].strip()
    body = body.strip()
    if not title or not body:
        return None
    return title[:1024], body[:3000]


async def rewrite_article(title: str, body: str, target_language: str) -> tuple[str, str] | None:
    """Return (title, body) rewritten natively for the target language."""
    settings = get_settings()
    if not settings.ai_rewrite_enabled or target_language.lower() not in LANGUAGE_NAMES:
        return None
    try:
        client = _client()
        language = LANGUAGE_NAMES[target_language.lower()]
        source = body.strip()[:7000]
        user = (
            f"Target language: {language}\n\n"
            f"Source title:\n{title[:2000]}\n\n"
            f"Source article:\n{source}"
        )
        from newsflow.services._openai_compat import chat_completions_create

        response = await chat_completions_create(
            client,
            model=settings.ai_rewrite_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.35,
            max_completion_tokens=1200,
        )
        parsed = _parse_rewrite(response.choices[0].message.content or "")
        if not parsed:
            logger.warning("AVEX rewrite returned an unparsable response")
        return parsed
    except Exception:
        logger.exception("AVEX AI rewrite failed")
        return None


async def generate_image(entry_id: int, title: str, summary: str) -> Path | None:
    """Generate one cached image per source entry. Returns a local PNG path."""
    settings = get_settings()
    if not settings.ai_image_enabled:
        return None
    path = settings.ai_image_dir / f"entry_{entry_id}.png"
    if path.is_file() and path.stat().st_size > 0:
        return path
    try:
        client = _client()
        settings.ai_image_dir.mkdir(parents=True, exist_ok=True)
        response = await client.images.generate(
            model=settings.ai_image_model,
            prompt=IMAGE_PROMPT.format(title=title[:1000], summary=summary[:2500]),
            size="1024x1024",
            response_format="b64_json",
        )
        encoded = response.data[0].b64_json
        if not encoded:
            return None
        path.write_bytes(base64.b64decode(encoded))
        return path
    except Exception:
        logger.exception("AVEX AI image generation failed")
        return None


def should_show_image(entry_id: int, probability: float) -> bool:
    """Stable per-entry choice so EN/FR/DE make the same image/no-image decision."""
    digest = hashlib.sha256(str(entry_id).encode()).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    return value < probability
