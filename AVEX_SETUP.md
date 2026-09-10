# AVEX News Autopilot — deployment

This build turns NewsFlow into an article-by-article AI autoposter for three Telegram channels.

## Channels

- German: `@avex_news` → `de`
- English: `@avex_exchange` → `en`
- French: `@avexmarkets` → `fr`

The bot must be an administrator with permission to post messages and photos in all three channels.

## AI behavior

For every new RSS article:

1. The article is deduplicated by the existing NewsFlow feed/guid history.
2. The AI creates a short original news brief in the subscription language.
3. The bot publishes one separate post to each subscribed channel.
4. The channel footer is appended automatically:
   - `AVEX | Kryptobörse` → `https://t.me/avex_news`
   - `AVEX | Crypto Exchange` → `https://t.me/avex_exchange`
   - `AVEX | Plateforme d'échange de cryptomonnaies` → `https://t.me/avexmarkets`
5. No source list, source link, Binance link or original article link is shown to readers.
6. About 40% of articles receive one generated editorial image. The same image is reused in DE/EN/FR for that article. The remaining ~60% are text-only.

The 40% decision is deterministic per article ID, so one article cannot get an image in one language and no image in another.

## Required environment

```env
TELEGRAM_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
OPENAI_API_KEY=YOUR_OPENAI_API_KEY

NEWS_AUTOPILOT_ENABLED=true
NEWS_MODEL=gpt-5.6-luna
NEWS_IMAGE_PERCENT=40
NEWS_IMAGE_MODEL=gpt-image-2
NEWS_IMAGE_SIZE=1536x1024
NEWS_IMAGE_QUALITY=medium
FETCH_INTERVAL_MINUTES=5

NEWS_FOOTER_DE_TEXT=AVEX | Kryptobörse
NEWS_FOOTER_DE_URL=https://t.me/avex_news
NEWS_FOOTER_EN_TEXT=AVEX | Crypto Exchange
NEWS_FOOTER_EN_URL=https://t.me/avex_exchange
NEWS_FOOTER_FR_TEXT=AVEX | Plateforme d'échange de cryptomonnaies
NEWS_FOOTER_FR_URL=https://t.me/avexmarkets
```

Do not put the real bot token or API key into GitHub. Put them only into Bothost environment variables.

## Configure the three channels

Open a private chat with the bot and set the language for each channel:

```text
/language @avex_news de
/language @avex_exchange en
/language @avexmarkets fr
```

Then add the same RSS sources to each channel. Example sources:

```text
/add @avex_news https://cointelegraph.com/rss
/add @avex_news https://www.coindesk.com/arc/outboundfeeds/rss/
/add @avex_news https://www.theblock.co/rss.xml
/add @avex_news https://cryptoslate.com/feed/
/add @avex_news https://decrypt.co/feed
```

Repeat the same five `/add` commands with `@avex_exchange` and `@avexmarkets`.

The first subscription to a feed may produce a preview. After that, the normal dispatcher sends new entries on the configured polling interval.

## Important

Do not configure `/digest` for these AVEX channels. The AVEX autopilot is the instant per-article pipeline; the old daily/weekly digest is a separate feature and is not needed for this workflow.

## Testing

For the first test, use only one feed in each channel:

```text
/add @avex_news https://cointelegraph.com/rss
/add @avex_exchange https://cointelegraph.com/rss
/add @avexmarkets https://cointelegraph.com/rss
```

Then wait for a new RSS item or temporarily lower `FETCH_INTERVAL_MINUTES` to `1` for testing.

Check the logs for:

- `Telegram bot started successfully`
- AI generation errors
- `Generated shared image for entry ...`
- successful dispatches

If image generation fails, the article is still posted as text. The bot deliberately degrades to text instead of losing the news item.


## v1.0.3

The AVEX footer is resolved from the actual Telegram destination channel username, not from the language. Therefore a German test channel does not receive the production @avex_news footer. News bodies target about 70-140 words when the source contains enough facts; short sources are not padded with invented information.
