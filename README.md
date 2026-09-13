# 🗳️ Loony to Westminster

*From counting bins to counting votes.*

A satirical turn-based campaign game: create an Independent joke candidate, fight
UK by-elections (mind that £500 deposit!), build a movement, and take on the
major parties — and the great spoof institutions of British politics (Count
Binface, the Monster Raving Loony Party, Lord Buckethead, the Darliks…) — all
the way to 10 Downing Street.

Python backend (FastAPI) + web frontend (vanilla JS, hand-rolled SVG map & charts).
Fully configurable: swap the config files and run the same game in any country.

---

## ⚠️ Disclaimer — please read

> **This is a satirical comedy game.** It is not affiliated with, endorsed by, or
> connected to any real political party, politician, or person — living, dead,
> robotic, or bin-based. All characters and events are affectionate caricature in
> the grand British tradition of taking the mickey. It is intended purely for
> humour and is meant to offend no one. **Please vote responsibly in real life.**

The game shows this disclaimer in-app too (title screen banner).

---

## Quick start

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python run.py        # starts server on http://127.0.0.1:2026 and opens your browser
```

### Playing on a phone (PWA)

The game is an installable Progressive Web App: on your phone's browser, open
the server's address and choose **Add to Home Screen** — it launches full-screen
with its own rosette icon, and the app shell is cached for flaky connections
(game state is always live from the server). Installation requires HTTPS, which
all hosts below provide automatically.

Run the tests:

```bash
venv/bin/python -m pytest tests/ -q
```

## Publishing the game (free hosting)

The game needs its Python server running (sessions live in memory), so static
hosts like GitHub Pages won't work. Recommended free hosts for a long-running
FastAPI app, all with automatic HTTPS:

| Host | Free tier | Notes |
|---|---|---|
| [Render](https://render.com) | ✅ web service, sleeps after ~15 min idle | Easiest: one-click blueprint below. First visit after a nap takes ~30–60s to wake. |
| [Koyeb](https://www.koyeb.com) | ✅ one free service | Uses the included `Dockerfile`. |
| [PythonAnywhere](https://www.pythonanywhere.com) | ✅ always-on | No cold starts, but ASGI setup is fiddlier. |
| Railway / Fly.io | ~small credits / pay-as-you-go | Great runners, no longer fully free. |

**Deploy to Render in one click:**

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/adwilson99/SpoofPolitics)

Or manually: create a **Web Service** from your repo, build command
`pip install -r requirements.txt`, start command
`uvicorn backend.main:app --host 0.0.0.0 --port $PORT` (a `render.yaml`
blueprint and a `Dockerfile` are both included). Then:

1. Open your `https://<app>.onrender.com` on the phone.
2. Browser menu → **Add to Home Screen** / **Install app**.
3. Launch it from the home screen like any other app. 🎩

Tips for the free tier:
- Sleepy instance? A free uptime pinger (e.g. UptimeRobot) hitting `/api/health`
  every 10 minutes keeps it warm.
- Saves live on the instance's disk, which free tiers wipe on redeploy — tell
  players campaigns are session-length, or attach persistent storage.

## How to play (design summary)

1. **Create your candidate** — name, party, slogan, a **persona** (six archetypes,
   from Pub Oracle to Suspiciously Sensible), and a manifesto of three joke
   policies (they have hidden demographic appeal; combos give synergies).
2. **By-elections** — weekly turns, limited action points: canvass, rally, kiss
   babies (rng: baby cries), post on social media. Rivals have personalities
   (they surge, coast, and go negative) and will debate you in the final week.
   **Get under 5% of the vote and you lose your £500 deposit.** Lose too many
   and you're financially ruined.
3. **Build the movement** — wins earn Momentum ★ and donations. Spend money on
   **marketing** (billboards, video ads, radio spots) or take **sponsorship**
   from investors — more budget, but every sponsor raises your **scandal risk**.
4. **General Election** — win enough by-elections (difficulty-dependent) to
   unlock it. Region-by-region results, popular-vote contest, coalition talks if
   needed — win and you're PM. Your first act: filling potholes with cheese.

Difficulty presets (Easy / Medium / Hard) control wins required, starting funds,
rival aggression, marketing efficiency, scandal severity, event frequency and
General Election defence. They also set the map granularity: Easy and Medium
fight **16 counties**, while Hard splits every county in half for a **32-seat**
map (each half inherits its parent's voters and gripes). Counties render onto a
real open-source SVG of the UK, coloured by whichever party holds them.

## Project structure

```
run.py                     # entrypoint: server on :2026 + browser
backend/
  main.py                  # FastAPI app, serves API + frontend
  api/routes.py            # /api/health /api/countries /api/difficulties
  api/game_routes.py       # /api/game/* — new game, action, end_week
  game/engine.py           # the weekly turn loop, actions, scandals
  game/elections.py        # CP → votes simulation, deposit rule, GE night
  game/content.py          # manifesto/synergies, personas, weekly events
  game/rivals.py           # rival AI: traits, strategies, debates, quips
  config/
    loader.py              # pydantic validation of all configs
    difficulty.json        # easy/medium/hard knobs
    countries/uk.json      # UK default: parties, regions, deposit, humour,
                           #   policies, synergies, personas, events
    countries/_template.json + HOW_TO_ADD_A_COUNTRY.md
frontend/                  # vanilla JS + CSS (no build step): candidate creation,
                           #   campaign screen, SVG UK map, debate night, election night
tests/                     # pytest: config validation + API + engine + content + frontend
```

## Adding a country

Copy `backend/config/countries/_template.json` to `mymarket.json`, fill it in
with local parties, regions, currency, deposit rules and jokes, restart — it
appears on the title screen automatically. Full field-by-field guide:
[`backend/config/countries/HOW_TO_ADD_A_COUNTRY.md`](backend/config/countries/HOW_TO_ADD_A_COUNTRY.md).

## Status / roadmap

- [x] **Phase 1** — skeleton: config system (UK + difficulty + marketing/sponsorship), FastAPI, title screen
- [x] **Phase 2** — engine core: turn loop, actions, elections, deposit rule, economy
- [x] **Phase 3** — content: policies, events, headlines, personas
- [x] **Phase 4** — rival AI: personality traits, strategies, debates, quips
- [x] **Phase 5** — full frontend: campaign map, polls, election night, debates
- [x] **Phase 6** — polish: save/load, victory/defeat scenes, balance

Difficulty presets now include `ge_defense` — how hard the established parties
defend the General Election on that mode (the main difficulty lever at the
ballot box). Campaigns can be saved to disk slots at any time (💾 on the
campaign screen) and resumed from the title screen.

## License

Released under the [MIT License](LICENSE).

## Credits

- **UK map** (`frontend/map/united-kingdom.svg`): from [MapSVG](https://mapsvg.com/maps/united-kingdom), released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (public domain dedication) — free to use, adapt and redistribute. Credited here with thanks.
- Built with [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/) and [Pydantic](https://docs.pydantic.dev/) — all BSD/MIT-licensed.
- The rosette app icons are generated by this repository's own tooling and ship under the same MIT license as the rest of the project.
