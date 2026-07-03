# ⚽ ScoreLine Live — Facebook Football Bot

Auto-posts live football updates to your Facebook page. **100% free** — no paid APIs.

## What gets posted
| Event | Example |
|-------|---------|
| 📋 Lineup | Starting XI ~1hr before KO (when available) |
| ▶️ Kick-off | `Live: 🇩🇪 Germany 0-0 🇬🇭 Ghana — Kickoff!` |
| ⚽ Goal | Scorer, minute, live score at moment of goal |
| ⏱️ Extra time | Notifies when ET starts (knockout matches) |
| 🏁 Full time | Final score + all goals. AET/Penalties clearly labelled |
| 📅 Daily preview | Morning fixture list (7AM UTC) |

**Not posted:** halftime scores, red cards, cancelled/postponed games.

## Coverage
- **Club**: EPL, Bundesliga, La Liga, Serie A, Ligue 1, UCL, UEL, UECL, FA Cup + more
- **International**: **ALL** country vs country games detected automatically — WC Qualifiers, AFCON, Nations League, Copa America, Friendlies, any FIFA series

## Data source
ESPN free API only — no API keys, no paid tiers, 100% free.

## Files
```
bot.py          ← Run this
scraper.py      ← ESPN data (scores, goals, status)
poster.py       ← Facebook API + message formatters
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
| `MIN_POST_GAP` | `20` |
| `MAX_POSTS_PER_HOUR` | `25` |

4. Start command: `python bot.py`

The bot binds an HTTP server to Railway's `PORT` automatically — no sleep issues.

## Adding leagues
Edit `ESPN_CLUB_LEAGUES` in `scraper.py`. Find ESPN slugs at `site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard`.
International games need no changes — all country vs country is auto-included.
