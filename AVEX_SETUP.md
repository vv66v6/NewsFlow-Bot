# AVEX publishing v1

This fork adds an AVEX-oriented publishing layer:

- native AI rewrite for English, French and German;
- one queued post per channel per dispatch cycle;
- default 90-minute fetch/publish cadence;
- no source URL in the normal Telegram footer;
- localized AVEX channel footer;
- stable image/no-image choice per article;
- optional OpenAI image generation when an RSS image is missing;
- generated images are cached in `data/generated_images/`.

## 1. Environment

Copy `.env.example` to `.env` and set:

```env
TELEGRAM_TOKEN=...
OPENAI_API_KEY=...

AI_REWRITE_ENABLED=true
AI_REWRITE_MODEL=gpt-5.6-luna

FETCH_INTERVAL_MINUTES=90
MAX_POSTS_PER_CHANNEL_PER_CYCLE=1

POST_IMAGE_PROBABILITY=0.65
AI_IMAGE_ENABLED=false
AI_IMAGE_MODEL=gpt-image-2
AI_IMAGE_PROBABILITY=0.35

AVEX_EN_CHANNEL_URL=https://t.me/...
AVEX_FR_CHANNEL_URL=https://t.me/...
AVEX_DE_CHANNEL_URL=https://t.me/...
```

The three URLs are the public links of the three AVEX channels. The names are already set to:

- AVEX | Crypto Exchange
- AVEX | Plateforme d'échange de cryptomonnaies
- AVEX | Kryptobörse

## 2. Subscribe the three channels

In each Telegram channel/chat, add the bot as an administrator with permission to post.

For each channel, subscribe the same RSS feeds and set its language:

```text
/add <RSS_URL>
/setlang <RSS_URL> en
/settrans <RSS_URL> on
```

French channel:

```text
/add <RSS_URL>
/setlang <RSS_URL> fr
/settrans <RSS_URL> on
```

German channel:

```text
/add <RSS_URL>
/setlang <RSS_URL> de
/settrans <RSS_URL> on
```

If an existing subscription has a custom `/template`, run:

```text
/template <RSS_URL> reset
```

The AVEX footer is then automatically appended by the default Telegram formatter.

## 3. Publishing behavior

The dispatcher fetches feeds every 90 minutes by default and sends at most one queued article per subscription per cycle. This means a channel with a healthy backlog receives roughly one article every 90 minutes.

The AI receives the source title and article body and returns:

```text
TITLE: ...
BODY:
...
```

The generated text is not a literal translation. EN/FR/DE are rewritten as separate native editorial versions.

The source URL remains stored in NewsFlow for deduplication and internal processing, but it is not shown in the normal AVEX post.

## 4. Images

`POST_IMAGE_PROBABILITY` controls whether an article should have an image.

If selected:
1. an RSS image is preferred;
2. if no RSS image exists and `AI_IMAGE_ENABLED=true`, an AI image can be generated according to `AI_IMAGE_PROBABILITY`;
3. the generated image is cached by source entry id and reused by EN/FR/DE.

Start with:

```env
POST_IMAGE_PROBABILITY=0.65
AI_IMAGE_ENABLED=false
```

After the text style is approved, enable:

```env
AI_IMAGE_ENABLED=true
```

This intentionally keeps image generation off during the first test so you can validate the editorial pipeline without image API costs.

## 5. First test

For the first live test, keep:

```env
FETCH_INTERVAL_MINUTES=90
AI_IMAGE_ENABLED=false
```

and use one RSS feed only.

Confirm that the first post has:

- a concise emoji headline;
- 1–3 short paragraphs;
- no `[Source]`;
- no original article URL;
- no Binance CTA;
- the correct AVEX channel footer;
- the correct language.

After that, enable AI images and add the rest of the feeds.

## Notes

The AI publishing layer is intentionally separate from the existing digest system. `DIGEST_SYSTEM_PROMPT` still controls `/digest`; `AI_REWRITE_*` controls normal per-article Telegram posts.
