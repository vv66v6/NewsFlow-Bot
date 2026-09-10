"""AI news-post generation and optional image generation for AVEX-style channels."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from newsflow.config import get_settings
from newsflow.core.content_processor import clean_html, truncate_text
from newsflow.services._openai_compat import chat_completions_create

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "de": "German",
    "en": "English",
    "fr": "French",
}

DEFAULT_SYSTEM_PROMPT = """You are the editor of a professional crypto news channel.
Rewrite the supplied RSS news item into a concise, factual Telegram news post.

Rules:
- Write ONLY in {language}. The headline and body MUST be fully written in {language}; do not leave the English source text unchanged.
- Translate proper explanatory wording into {language}, while keeping names, ticker symbols, company names, and official product names when appropriate.
- Return valid JSON with exactly these keys: headline, body, image_prompt.
- headline: one short, news-style headline. Do not add an emoji.
- body: usually 2 short paragraphs and about 70-140 words when the source provides enough factual material. Make the body meaningfully informative, not just one sentence. Do not pad or invent facts when the source is brief.
- Preserve every important fact, number, date, percentage, company, token, person and legal qualification present in the source.
- Never invent facts, motives, quotes, numbers or conclusions.
- Do not copy long passages verbatim. Produce an original concise news brief.
- For allegations, lawsuits, investigations and accusations, clearly attribute claims and do not state allegations as established facts.
- Do not include source links, the original article URL, citations, hashtags, advertising, Binance links or a source list.
- Do not mention that you are an AI and do not explain your editing.
- image_prompt: a concise English prompt for a professional editorial crypto-news illustration of this story. No text, no headline, no watermark, no logo recreation requirement.
"""


@dataclass(frozen=True)
class NewsDraft:
    headline: str
    body: str
    image_prompt: str


class NewsPublisher:
    """Generate localized AVEX posts and one shared optional image per article."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None
        self._draft_cache: dict[tuple[int, str], NewsDraft] = {}
        self._image_cache: dict[int, Path | None] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.news_autopilot_enabled and bool(self.settings.openai_api_key)

    def _client_instance(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            kwargs: dict[str, Any] = {"api_key": self.settings.openai_api_key}
            if self.settings.openai_base_url:
                kwargs["base_url"] = self.settings.openai_base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _clean_source(self, title: str, summary: str | None, content: str | None) -> str:
        raw = content or summary or ""
        text, _ = clean_html(raw)
        text = text.strip()
        if not text:
            return title.strip()
        # Keep enough context for useful rewrites without sending entire scraped articles.
        return truncate_text(text, self.settings.news_max_source_chars)

    @staticmethod
    def _language_quality_ok(text: str, target_language: str) -> bool:
        """Reject obvious English pass-throughs for German/French output.

        This is deliberately conservative: it is not a full language detector,
        but it must reliably reject an unchanged English crypto-news paragraph.
        """
        import re

        primary = target_language.replace("_", "-").split("-")[0].lower()
        if primary == "en":
            return True
        if primary not in {"de", "fr"}:
            return True

        words = [w.lower() for w in re.findall(r"[A-Za-zÄÖÜäöüßÀ-ÿ]+", text)]
        if len(words) < 8:
            return False
        wordset = set(words)

        english = {
            "the", "and", "of", "to", "in", "for", "on", "with", "from", "after",
            "before", "as", "is", "are", "was", "were", "will", "would", "has",
            "have", "had", "not", "its", "their", "this", "that", "these", "those",
            "said", "says", "new", "more", "than", "into", "over", "under", "about",
            "following", "according", "denies", "profit", "profiting", "crashes",
            "found", "announced", "flagged", "fresh", "holders",
        }
        if primary == "de":
            target = {
                "der", "die", "das", "und", "von", "für", "nach", "mit", "auf", "ist",
                "sind", "wird", "wurden", "hat", "haben", "einer", "einen", "eine",
                "nicht", "sich", "den", "dem", "des", "als", "auch", "bei", "aus",
                "über", "durch", "gegen", "zum", "zur", "noch", "bereits", "dass",
            }
        else:
            target = {
                "le", "la", "les", "des", "et", "de", "pour", "avec", "dans", "est",
                "sont", "sera", "ont", "une", "un", "pas", "sur", "du", "au", "aux",
                "que", "qui", "dans", "avec", "mais", "comme", "plus", "selon",
            }

        english_hits = sum(1 for w in words if w in english)
        target_hits = sum(1 for w in words if w in target)
        # Any dense English signal is a hard reject. A short headline/body must
        # also contain multiple target-language function words.
        if english_hits >= 3 and english_hits >= target_hits:
            return False
        if target_hits < 2:
            return False
        if english_hits / max(len(words), 1) > 0.12:
            return False
        return True

    async def generate_draft(
        self,
        entry_id: int,
        title: str,
        summary: str | None,
        content: str | None,
        link: str,
        target_language: str,
        published_at: str = "",
    ) -> NewsDraft:
        key = (entry_id, target_language.lower())
        cached = self._draft_cache.get(key)
        if cached:
            return cached

        language = LANGUAGE_NAMES.get(target_language.lower(), target_language)
        source = self._clean_source(title, summary, content)
        domain = urlparse(link).netloc.lower()
        prompt = (
            f"SOURCE DOMAIN: {domain}\n"
            f"PUBLISHED: {published_at}\n"
            f"ORIGINAL TITLE: {title.strip()}\n"
            f"SOURCE TEXT:\n{source}"
        )
        system = self.settings.news_system_prompt or DEFAULT_SYSTEM_PROMPT
        try:
            system = system.format(language=language, lang=target_language)
        except (KeyError, IndexError):
            system = DEFAULT_SYSTEM_PROMPT.format(language=language)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        data: dict[str, Any] | None = None
        headline = body = image_prompt = ""
        accepted = False
        for attempt in range(3):
            response = await chat_completions_create(
                self._client_instance(),
                model=self.settings.news_model,
                messages=messages,
                max_completion_tokens=self.settings.news_max_completion_tokens,
                response_format={"type": "json_object"},
            )
            raw = (response.choices[0].message.content or "").strip()
            data = json.loads(raw)
            headline = str(data.get("headline", "")).strip()
            body = str(data.get("body", "")).strip()
            image_prompt = str(data.get("image_prompt", "")).strip()
            accepted = bool(headline and body and self._language_quality_ok(f"{headline} {body}", target_language))
            if accepted:
                break
            messages.append({
                "role": "user",
                "content": (
                    f"STOP. The previous answer was rejected because it was not fully in {language}. "
                    f"Translate/rewrite BOTH the headline and body into natural {language}. "
                    "Do not leave ANY English sentence or headline. Keep proper names, tickers and company names only where they are official names. "
                    "Return JSON with the same three keys and nothing else."
                ),
            })

        if not accepted:
            raise ValueError(f"AI failed language validation for target language {target_language}")
        draft = NewsDraft(headline=headline, body=body, image_prompt=image_prompt)
        self._draft_cache[key] = draft
        return draft

    def should_generate_image(self, entry_id: int) -> bool:
        """Deterministic ~40% choice so all three language posts share the same decision."""
        digest = hashlib.sha256(f"avex-image:{entry_id}".encode()).digest()
        return int.from_bytes(digest[:4], "big") % 100 < self.settings.news_image_percent

    async def get_shared_image(self, entry_id: int, image_prompt: str) -> Path | None:
        if entry_id in self._image_cache:
            return self._image_cache[entry_id]
        if not self.should_generate_image(entry_id):
            self._image_cache[entry_id] = None
            return None
        if not image_prompt:
            self._image_cache[entry_id] = None
            return None

        out_dir = self.settings.data_dir / "generated_images"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"entry_{entry_id}.png"
        if path.is_file() and path.stat().st_size > 0:
            self._image_cache[entry_id] = path
            return path

        try:
            client = self._client_instance()
            response = await client.images.generate(
                model=self.settings.news_image_model,
                prompt=image_prompt,
                size=self.settings.news_image_size,
                quality=self.settings.news_image_quality,
                n=1,
            )
            item = response.data[0]
            b64 = getattr(item, "b64_json", None)
            if b64:
                path.write_bytes(base64.b64decode(b64))
            else:
                # URL responses are supported as a fallback by downloading them through aiohttp.
                image_url = getattr(item, "url", None)
                if not image_url:
                    raise ValueError("Image API returned neither b64_json nor url")
                import aiohttp

                async with aiohttp.ClientSession() as http:
                    async with http.get(image_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        resp.raise_for_status()
                        path.write_bytes(await resp.read())
            self._image_cache[entry_id] = path
            logger.info("Generated shared image for entry %s", entry_id)
            return path
        except Exception:
            logger.exception("Image generation failed for entry %s; posting text only", entry_id)
            self._image_cache[entry_id] = None
            return None


_news_publisher: NewsPublisher | None = None


def get_news_publisher() -> NewsPublisher:
    global _news_publisher
    if _news_publisher is None:
        _news_publisher = NewsPublisher()
    return _news_publisher
