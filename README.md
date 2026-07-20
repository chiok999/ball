# ⚽ Match Corna Live — Facebook Football Bot

Auto-posts live football updates to your Facebook page. **100% free** — no paid APIs. Present and future only — no historical "flashback" content.

## What gets posted
| Event | Example |
|-------|---------|
| 📋 Lineup | Starting XI ~1hr before KO (when available) for every game |
| ▶️ Kick-off | Stylish scoreboard card — team hex badges + KICK-OFF ribbon |
| ⚽ Goal | Scorer, minute, live score — name drawn under the scoring team's own crest |
| 🟥 Red card | Player + minute, posted the moment it's detected |
| ⏸️ Half time | Current score + scorers/assists so far |
| ⏱️ Extra time | Notifies when ET starts (knockout matches) |
| 🏁 Full time | Final score + all goals, each team's scorers under their own crest. AET/Penalties clearly labelled |
| 📅 Daily preview | Morning fixture list (9AM UTC) |
| 📰 Football news | Player transfers, manager sackings, manager transfers, deal done, gossip, World Cup news — see below |

**Not posted:** cancelled/postponed games, or anything historical (old transfers, past-season stats). Win-probability predictions have been removed — see "Removed features" below.

## Coverage
- **Club**: EPL, Bundesliga, La Liga, Serie A, Ligue 1, UCL, UEL, UECL, FA Cup + more
- **International**: **ALL** country vs country games detected automatically — WC Qualifiers, AFCON, Nations League, Copa America, Friendlies, any FIFA series

## Football news — 6 categories, all live/current
Polled from ESPN (per league + the World Cup slug), BBC Sport RSS, Sky Sports RSS, The Guardian RSS, and 90min RSS, deduped across sources. Every headline is checked against `TRANSFER_MAX_AGE_HOURS` (default 6h) before it's ever posted — nothing here is ever a repost of old news, independent of what `state.json` remembers.

| Category | Covers | Badge |
|----------|--------|-------|
| 🚨 Player Transfer News | Signings/loans/bids in progress, contract talk | TRANSFER NEWS |
| 🔴 Manager Sacking | Sackings, resignations, "parts ways" | MANAGER SACKING |
| 📋 Manager Transfer News | New appointments, unveilings, interim bosses | MANAGER NEWS |
| ✅ Deal Done | Confirmed/official signings and moves | DEAL DONE |
| 🗣️ Gossip | Speculation — linked with, interest, rumours | GOSSIP |
| 🌍 World Cup News | Retirements, knockouts/eliminations, upcoming fixtures, qualification | WORLD CUP NEWS |

Each caption now includes a short teaser pulled from the source's own RSS/ESPN `<description>` field (not just the headline repeated), falling back to a brief generic framing line if the source gave no usable teaser.

Rate-limited to **1 post per 30 minutes** (`TRANSFER_MAX_POSTS_PER_WINDOW` / `TRANSFER_WINDOW_MINUTES`) so a busy news day doesn't flood the page — each post includes an image (the real article photo when available, a generated card otherwise, with the headline vertically centered when there's no photo) since photo posts get more reach on Facebook.

**Quieting the page down:** set `TRANSFER_NEWS_CATEGORIES` to a comma-separated subset of `deal_done, deal_collapsed, manager_sacking, manager_transfer, injury, player_quote` to restrict which categories are allowed to post at all — e.g. `TRANSFER_NEWS_CATEGORIES=deal_done` posts confirmed signings only (useful right after a World Cup, when even the confirmed-only categories can read as noisy). Leave unset for all categories (today's default).

## Removed features
- **Win probability (ClubElo/Elo ratings)** has been removed entirely — `elo.py` is deleted, and every reference to it in `bot.py`, `poster.py`, `config.py`, and `worldcup.py` is gone. World Cup quiet-gap filler now posts top scorers only.
- **`article.py`** (fetching the linked article page and extracting fee/quote/contract facts) has been removed — captions now use the source feed's own `<description>` teaser instead.
- **Post-Match Reaction** and **Player Tracker** news categories have been removed completely.

## Card design
All cards are rendered with Pillow — no generative image model in the loop, so nothing can misspell a name or draw a wrong flag/crest.

- **Stadium backdrop**: floodlight beam fans from both top corners over a dark vignette + blurred pitch texture.
- **Hexagon team badges**: crests/flags sit in a light-bordered hex frame (falls back to a colored hex initials badge if a crest can't be fetched) instead of a plain circle.
- **Ribbon/chevron banners**: scorelines and status labels (`KICK-OFF`, `72' - LIVE`, `FULL TIME`) are drawn as pointed-end ribbon badges rather than flat rounded pills.
- **Side-anchored scorer/assist text**: goal and full-time scorer names are drawn under the *scoring team's own crest* rather than centered across the card, so it's immediately clear whose event it is.
- **Vertically centered fallback**: when a news item has no usable photo, the headline is centered (both vertically and horizontally) in the card instead of being top-anchored with empty space below it.

## Data source
ESPN free API + Sofascore (primary) — no API keys, no paid tiers, 100% free.

## Files
```
bot.py          ← Run this
scraper.py      ← Live scores (Sofascore primary, ESPN fallback)
sofascore.py    ← Sofascore reader
poster.py       ← Facebook API + message formatters
graphics.py     ← Branded card rendering (Pillow)
transfers.py    ← Football news: player transfers, manager sackings/transfers, deal done, gossip, World Cup
worldcup.py     ← World Cup top-scorers filler
config.py       ← All settings via env vars
requirements.txt
state.json      ← Auto-created, tracks posted events
```

## Local run
```bash
pip install -r requirements.txt
python bot.py
# Without FB_PAGE_ID set, posts print to console instead
```

| Variable | Value |
|----------|-------|
| `FB_PAGE_ID` | Your Facebook Page ID |
| `FB_PAGE_ACCESS_TOKEN` | Your long-lived Page Access Token |
| `POLL_INTERVAL` | `60` |
| `POST_LINEUPS` | `true` |
| `LINEUP_LEAD_MINUTES` | `65` |
| `POST_KICKOFF` | `true` |
| `POST_GOALS` | `true` |
| `POST_RED_CARDS` | `true` |
| `POST_HALFTIME` | `true` |
| `POST_FULLTIME` | `true` |
| `POST_DAILY_PREVIEW` | `true` |
| `DAILY_PREVIEW_HOUR` | `9` |
| `POST_TRANSFER_NEWS` | `true` |
| `TRANSFER_MAX_POSTS_PER_WINDOW` | `1` |
| `TRANSFER_WINDOW_MINUTES` | `30` |
| `TRANSFER_MAX_AGE_HOURS` | `6` |
| `MIN_POST_GAP` | `20` |
| `MAX_POSTS_PER_HOUR` | `25` |

4. Start command: `python bot.py`

The bot binds an HTTP server to Railway's `PORT` automatically — no sleep issues.

## Adding leagues
Edit `TRANSFER_LEAGUES` in `config.py` to add/remove leagues polled for football news, and `ESPN_CLUB_LEAGUES` in `scraper.py` for live scores. Find ESPN slugs at `site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard`.
International games need no changes — all country vs country is auto-included for live scores, and the World Cup slug is polled automatically for World Cup news.
