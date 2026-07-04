# ⚽ Match Corna Live — Facebook Football Bot

Auto-posts live football updates to your Facebook page. **100% free** — no paid APIs. Present and future only — no historical "flashback" content.

## What gets posted
| Event | Example |
|-------|---------|
| 📋 Lineup | Starting XI ~1hr before KO (when available) |
| ▶️ Kick-off | Stylish scoreboard card — team hex badges + KICK-OFF ribbon |
| ⚽ Goal | Scorer, minute, live score at the moment of the goal |
| ⏱️ Extra time | Notifies when ET starts (knockout matches) |
| 🏁 Full time | Final score + all goals. AET/Penalties clearly labelled |
| 📅 Daily preview | Morning fixture list (7AM UTC) |
| 📰 Football news | Transfers, manager news, World Cup news, post-match reactions — see below |

**Not posted:** halftime scores, red cards, cancelled/postponed games, or anything historical (old transfers, past-season stats).

## Coverage
- **Club**: EPL, Bundesliga, La Liga, Serie A, Ligue 1, UCL, UEL, UECL, FA Cup + more
- **International**: **ALL** country vs country games detected automatically — WC Qualifiers, AFCON, Nations League, Copa America, Friendlies, any FIFA series

## Football news — 4 categories, all live/current
Polled from ESPN (per league + the World Cup slug), BBC Sport RSS, and Sky Sports RSS, deduped across sources. Every headline is checked against `TRANSFER_MAX_AGE_HOURS` (default 6h) before it's ever posted — nothing here is ever a repost of old news, independent of what `state.json` remembers.

| Category | Covers | Badge |
|----------|--------|-------|
| 🚨 Transfer News | Signings, loan moves, deals agreed | BREAKING NEWS |
| 📋 Manager News | Sackings, resignations, new appointments | MANAGER NEWS |
| 🌍 World Cup News | Retirements, knockouts/eliminations, upcoming fixtures, qualification | WORLD CUP |
| 🎙️ Post-Match Reaction | Interviews, press conferences, reactions to a result | REACTION |

Rate-limited to **2 posts per 30 minutes** (`TRANSFER_MAX_POSTS_PER_WINDOW` / `TRANSFER_WINDOW_MINUTES`) so a busy news day doesn't flood the page — each post includes an image (the real article photo when available, a generated card otherwise) since photo posts get more reach on Facebook.

There is no more "Transfer Flashback" (historical transfermarkt-dataset) content — that feature has been removed entirely, along with its config flags, formatter, and card renderer.

## Card design
All cards are rendered with Pillow — no generative image model in the loop, so nothing can misspell a name or draw a wrong flag/crest.

- **Stadium backdrop**: floodlight beam fans from both top corners over a dark vignette + blurred pitch texture.
- **Hexagon team badges**: crests/flags sit in a light-bordered hex frame (falls back to a colored hex initials badge if a crest can't be fetched) instead of a plain circle.
- **Ribbon/chevron banners**: scorelines and status labels (`KICK-OFF`, `72' • LIVE`, `FULL TIME`) are drawn as pointed-end ribbon badges rather than flat rounded pills.

## Data source
ESPN free API + Sofascore (primary) — no API keys, no paid tiers, 100% free.

## Files
```
bot.py          ← Run this
scraper.py      ← Live scores (Sofascore primary, ESPN fallback)
sofascore.py    ← Sofascore reader
poster.py       ← Facebook API + message formatters
graphics.py     ← Branded card rendering (Pillow)
transfers.py    ← Football news: transfers, manager, World Cup, reactions
worldcup.py     ← World Cup top-scorers filler
elo.py          ← ClubElo win-probability filler
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

## Facebook setup (free, one-time)
1. [developers.facebook.com](https://developers.facebook.com) → Create App → **Business**
2. Add product: **Facebook Login for Business**
3. **Graph API Explorer** → select your app → your page → Generate Token
4. Tick permissions: `pages_manage_posts`, `pages_read_engagement`
5. Extend the token: [developers.facebook.com/tools/accesstoken](https://developers.facebook.com/tools/accesstoken)
6. Your Page ID: found in your page URL or About section

## Railway deployment
1. Push this folder to GitHub
2. [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. Set these env vars in Railway → Variables:

| Variable | Value |
|----------|-------|
| `FB_PAGE_ID` | Your Facebook Page ID |
| `FB_PAGE_ACCESS_TOKEN` | Your long-lived Page Access Token |
| `POLL_INTERVAL` | `60` |
| `POST_LINEUPS` | `true` |
| `POST_KICKOFF` | `true` |
| `POST_GOALS` | `true` |
| `POST_FULLTIME` | `true` |
| `POST_DAILY_PREVIEW` | `true` |
| `DAILY_PREVIEW_HOUR` | `7` |
| `POST_TRANSFER_NEWS` | `true` |
| `TRANSFER_MAX_POSTS_PER_WINDOW` | `2` |
| `TRANSFER_WINDOW_MINUTES` | `30` |
| `TRANSFER_MAX_AGE_HOURS` | `6` |
| `MIN_POST_GAP` | `20` |
| `MAX_POSTS_PER_HOUR` | `25` |

4. Start command: `python bot.py`

The bot binds an HTTP server to Railway's `PORT` automatically — no sleep issues.

## Adding leagues
Edit `TRANSFER_LEAGUES` in `config.py` to add/remove leagues polled for football news, and `ESPN_CLUB_LEAGUES` in `scraper.py` for live scores. Find ESPN slugs at `site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard`.
International games need no changes — all country vs country is auto-included for live scores, and the World Cup slug is polled automatically for World Cup news.
