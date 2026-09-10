# AVEX v2

## What changed
- AI editorial posts now use the full available RSS article body (up to 7000 chars) instead of the short 1024-char display summary.
- AI prompt requires native EN/FR/DE output, 2–4 substantive paragraphs, normally 700–1400 body characters, and factual source grounding.
- Default Telegram AVEX footer is rendered as a real clickable HTML link instead of leaking Markdown syntax.
- Added `/avex_test [@channel] [en|fr|de]` to send the newest stored article through the real AVEX pipeline without consuming it from the normal queue.
- `/avex_test @avex_exchange` defaults to English, `@avexmarkets` to French, and `@avex_news` to German.
- `/avex_test` ignores an old custom template so the AVEX default format can be tested directly.
- Normal dispatch now treats Telegram channel as the publication destination: at most one article is sent to a channel per dispatch cycle, even if that channel has multiple feed subscriptions.

## Main-channel smoke tests
From a Telegram private chat where the bot can manage the three channels:

```
/avex_test @avex_exchange
/avex_test @avexmarkets
/avex_test @avex_news
```

The command does not mark the article as sent, so it is safe to repeat while tuning the format.

To force the language explicitly:

```
/avex_test @avex_exchange en
/avex_test @avexmarkets fr
/avex_test @avex_news de
```

## Production cadence
Use `FETCH_INTERVAL_MINUTES=90` after testing. With the channel-level one-post-per-cycle guard, this yields approximately one post per channel every 90 minutes when there is queued news.

For faster smoke tests only, `FETCH_INTERVAL_MINUTES=1` is acceptable.
