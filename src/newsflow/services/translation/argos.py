"""
Local Argos Translate provider.

Uses the Argos Translate models installed in the container. No external
translation API or API key is required.
"""

import asyncio
import logging

from newsflow.services.translation.base import TranslationProvider, TranslationResult

logger = logging.getLogger(__name__)

ARGOS_LANGUAGES = {
    "en", "de", "fr", "es", "it", "nl", "pt", "ru", "uk", "pl",
    "cs", "da", "sv", "fi", "el", "ja", "ko", "zh", "tr", "ar",
}


class ArgosProvider(TranslationProvider):
    """Offline/local translation provider backed by Argos Translate."""

    def __init__(self, default_source_language: str = "en") -> None:
        self.default_source_language = default_source_language.lower()
        self._loaded = False

    @property
    def name(self) -> str:
        return "argos"

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            import argostranslate.translate  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "argostranslate package is not installed. "
                "Install it with: pip install argostranslate"
            ) from e
        self._loaded = True

    def normalize_language_code(self, lang_code: str) -> str:
        code = lang_code.lower().strip()
        # Accept common Telegram/ISO variants.
        return code.split("-")[0]

    def supports_language(self, lang_code: str) -> bool:
        return self.normalize_language_code(lang_code) in ARGOS_LANGUAGES

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None = None,
    ) -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult(success=True, translated_text="")

        source = self.normalize_language_code(source_lang or self.default_source_language)
        target = self.normalize_language_code(target_lang)

        if source == target:
            return TranslationResult(
                success=True,
                translated_text=text,
                source_language=source,
            )

        if not self.supports_language(source):
            return TranslationResult(
                success=False,
                error=f"Argos source language is not supported: {source}",
                source_language=source,
            )

        if not self.supports_language(target):
            return TranslationResult(
                success=False,
                error=f"Argos target language is not supported: {target}",
                source_language=source,
            )

        try:
            self._ensure_loaded()
            import argostranslate.translate as argos_translate

            translated = await asyncio.to_thread(
                argos_translate.translate,
                text,
                source,
                target,
            )

            translated = (translated or "").strip()
            if not translated:
                return TranslationResult(
                    success=False,
                    error="Argos returned an empty translation",
                    source_language=source,
                )

            return TranslationResult(
                success=True,
                translated_text=translated,
                source_language=source,
            )

        except Exception as e:
            logger.exception(
                "Argos translation error (%s -> %s): %s",
                source,
                target,
                e,
            )
            return TranslationResult(
                success=False,
                error=str(e),
                source_language=source,
            )
