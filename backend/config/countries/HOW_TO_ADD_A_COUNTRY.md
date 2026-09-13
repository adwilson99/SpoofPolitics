# Adding a Country to *Loony to Westminster*

The whole game — parties, regions, deposit rules, jokes — is driven by JSON config
files in this folder. The UK (`uk.json`) is the fully-fleshed default. To add your
own country, copy `_template.json` to `<your_country_id>.json` and fill it in.
The game picks it up automatically; no code changes needed.

> Keys starting with `_` (like `_how_to_use`) are ignored by the game, so you can
> leave notes in your config.

## Field guide

### Top level
| Field | What it does |
|---|---|
| `id` | Unique slug, e.g. `"uk"`, `"usa"`, `"australia"`. Used in the API and save files. |
| `name` | Display name shown on the title screen. |
| `flag_emoji` | Shown next to the country name. |
| `game_title` | The in-game title can be localised (e.g. *"Loony to Westminster"* → *"Loony to the White House"*). |
| `subtitle` | Tagline under the title. |
| `currency` | `symbol` and `code` — all money in the UI uses this. |
| `disclaimer` | Satire disclaimer shown to players. If you omit it, a generic English one is injected automatically. |

### `deposit` — the heart of the game
| Field | What it does |
|---|---|
| `amount` | Deposit per election (UK: £500). |
| `vote_threshold` | Get fewer votes than this and you lose the deposit (UK: 1000). |
| `loss_line` / `kept_line` | Flavour text shown on the results screen. `{symbol}` and `{amount}` placeholders may be used. |

### `offices`
What you're running *for*: `local_title` (what a win makes you, UK: "MP"),
`leader_title` (UK: "Prime Minister" — use "President" etc. for other countries),
`residence` (UK: "10 Downing Street"), `chamber`, and `coalition_talks` (used by
the endgame if nobody wins outright).

### `election`
| Field | What it does |
|---|---|
| `byelection_label` | e.g. "by-election" (UK), "special election" (US). |
| `generalelection_label` | e.g. "General Election". |
| `max_candidates_on_ballot` | How many candidates (player + rivals) appear per election. |
| `campaign_weeks_per_election` | Turn-length of each election campaign. |

### Parties
Two arrays: `major_parties` and `spoof_parties`. Same schema for both — the
difference is tone (and that spoof parties are slightly worse at fundraising).

| Field | What it does |
|---|---|
| `id` | Unique across **both** arrays. |
| `name` / `short` | Full and abbreviated names. |
| `color` | Hex colour used in charts and the map. Must be unique. |
| `emoji` | Little badge in the UI. |
| `leader` | `name` + `persona` (a one-line comedic character sketch — the rival AI leans on this). |
| `blurb` | One-liner shown in candidate lists. |
| `policies_hint` | *(spoof parties)* 2-4 signature joke policies for flavour text. |
| `regions` | `null` = contests everywhere; or a list of region `id`s (e.g. the SNP only campaigns in Scotland). |
| `traits` | *(optional)* Rival AI personality — see below. |
| `quips` | *(optional)* Signature one-liners ({short}, {player}, {region} placeholders) used for stunts, attacks and debate night. |

**`traits` — rival AI personality (all optional, sensible defaults):**
| Trait | What it does |
|---|---|
| `aggression` | 0.3–2.5 effort multiplier. Machines (1.2+) never stop; figures of fun (0.8) amble. |
| `focus` | Who they chase: `even`, `youth`, `middle` or `pensioner` — drives which of your campaign buckets their attacks hit. |
| `variance` | 0–1. Chaotic campaigns make news more (and coast less). |
| `stunt` | 0–1. Weekly chance of a headline stunt: a burst of extra energy. |
| `attack` | 0–1. Chance of going negative: drains *your* campaign energy. |
| `grit` | 0–1. Debate skill. The frontrunner brings it to the final-week debate. |

Each week each rival picks a strategy: **grind** (default), **surge** (final-week
push), **coast** (comfortable, low-variance leaders) or **attack** (negative
campaigning). Once per campaign, on the last full week, you meet the frontrunner
in a **debate** — your campaign energy and momentum versus their `grit`.

**On real parties/people:** party names are fine to use (they're real
organisations). For leaders, the tone should stay affectionate — caricature, not
cruelty. If in doubt, lightly fictionalise (`"Keir Starmer"` → works great,
but so does `"Keir Slowmo"`). The game ships with a prominent disclaimer
regardless.

### `regions`
Each region is one contestable area on the map (UK ships with 20 counties).

| Field | What it does |
|---|---|
| `id` | Unique slug. |
| `name` | Display name. |
| `electorate` | Rough voter pool — keeps results believable. |
| `turnout_base` | 0–1. Base turnout before campaign effects. |
| `demographics` | See below. |
| `local_issues` | 3 funny-but-real local gripes; these surface in events and debates. |

**`demographics`:**
- `youth`, `middle`, `pensioner` — integer percentages of the electorate.
  **Must sum to 100.**
- `niche_joy` (0–1) — how much the area loves joke candidates.
- `protest_mood` (0–1) — appetite to stick it to the big parties.
- `cost_of_living` (0–1) — price/bills pain; economic campaigns land harder here.
- `change_hungry` (0–1) — demand for anything-not-politics-as-usual.

### `marketing_channels`
Paid promotion options for the campaign screen (engine Phase 2).

| Field | What it does |
|---|---|
| `id` / `name` / `emoji` / `blurb` | Identity + UI flavour. |
| `cost` | Price in local currency per purchase. |
| `reach` | Base polling bump distributed across demographics. |
| `weeks` | How long the campaign runs once bought. |
| `appeal` | Multipliers keyed by `youth` / `middle` / `pensioner`. |

Difficulty presets scale these via `marketing_efficiency`.

### `sponsorship`
Investor tiers — extra budget at the cost of scandal risk.

| Field | What it does |
|---|---|
| `intro_line` / `scandal_note` | UI copy. |
| `scandal_headline_templates` | `{party}` is replaced with your party name when a scandal breaks. |
| `tiers[].id` | Unique slug. |
| `tiers[].name` / `emoji` / `blurb` | Identity + flavour. |
| `tiers[].amount` | Money injected on signing. |
| `tiers[].scandal_risk` | 0–1. Weekly chance this sponsor generates a scandal; more sponsors = compounding risk. |

Difficulty presets scale the fallout via `scandal_magnitude`.

### `flavour`
Localises the jokes: `newspapers`, `tv_shows`, `loading_lines`, `victory_lines`,
`defeat_lines`, `deposit_loss_lines`. Templates may use `{residence}` and
`{party}` placeholders.

`quiet_week_templates` (optional) are filler headlines for weeks where nothing
happened. See the placeholders section under `events` below.

### `policies` — the manifesto deck (optional)
Players pick up to **3** of these when creating their candidate. The appeal is
hidden; at each campaign launch the manifesto quietly seeds extra campaign
points in the regions that care.

| Field | What it does |
|---|---|
| `id` | Unique slug. |
| `name` / `emoji` / `blurb` | Shown on the manifesto card and in launch news. |
| `appeal` | Hidden demographic weights keyed by `youth` / `middle` / `pensioner` (0–1). Empty = spread evenly. |
| `tags` | Free-form labels that synergies match on. 8–18 policies is a good deck size. |

### `synergies` — manifesto combos (optional)
Fire when the player's manifesto satisfies the requirements.

| Field | What it does |
|---|---|
| `requires_tags` | Every entry needs at least one matching policy; **list a tag twice to require two policies carrying it** (e.g. `["cost_of_living", "cost_of_living"]`). |
| `requires_policies` | Alternatively/also, exact policy ids that must all be present. |
| `bonus_cp` | Extra campaign points granted at launch (must be > 0). |
| `bonus_bias` | Which age buckets the bonus lands in (`youth`/`middle`/`pensioner`). Empty = even split. |

A synergy must require at least one tag or policy.

### `personas` — candidate archetypes (optional)
Chosen at candidate creation (or none). Perks are small and stack with the
player's choices.

| Field | What it does |
|---|---|
| `action_cp_multipliers` | `{action_id: multiplier}` — boosts specific campaign actions (0.1–3.0). Action ids: `canvass`, `leaflets`, `social_post`, `baby_kiss`, `pub_visit`, `radio_phone_in`, `rally`, `press_stunt`, `fundraise`. |
| `fundraise_multiplier` | Scales fundraising take (0.5–3.0, default 1.0). |
| `scandal_resistance` | 0–1 — cuts the weekly scandal chance. |
| `baby_cry_immunity` | `true` and the babies simply will not cry. |
| `debate_bonus` | 0–1 — extra debate-night score. Telly Regulars do well. |

### `events` — weekly random news (optional)
Each week, with probability `event_frequency` from the difficulty preset, one
event fires. Good events help (funds/CP/momentum); bad events hurt. Effects are
*magnitudes* — the sign comes from which pool the event is in.

| Field | What it does |
|---|---|
| `id` | Unique across both pools. |
| `headline` | News template (see placeholders below). Must be valid — typos fail config validation. |
| `weight` | 1–10 relative likelihood within its pool. |
| `funds` | Money granted/charged (0–5000). |
| `cp` | Campaign points granted/removed (0–20). |
| `momentum` | Momentum stars granted/lost (0–3). |

Every event needs at least one effect. Difficulty presets control how often
events fire (`event_frequency`) and how often they're good (`good_event_bias`).

**Template placeholders** (valid in `events` and `quiet_week_templates`):
`{party}` (your party name, caps), `{region}`, `{issue}` (a local issue),
`{newspaper}`, `{show}`, `{rival}` (a major party's short name), `{symbol}`
(currency symbol), `{amount}` (deposit amount).

## Validation rules (the loader enforces these)
- All `id`s unique (parties across both arrays, regions, channels, tiers,
  policies, personas; events across both pools).
- Party `color`s unique.
- `demographics.youth + middle + pensioner == 100`.
- Party `regions` lists may only reference existing region ids.
- `deposit.amount` > 0, `vote_threshold` > 0, risks/probabilities in 0–1.
- Synergy `requires_policies` must reference existing policy ids; personas may
  only boost real action ids.
- Event/quiet-week headline templates must only use the placeholders listed
  above, and every event needs at least one effect.
- `disclaimer` optional (auto-injected if missing).

All the Phase 3 sections (`policies`, `synergies`, `personas`, `events`) are
optional — omit them and the game runs as before, just with less variety.

If your config fails validation the API returns a descriptive error listing
exactly what to fix.

## Localisation tips
- Steal the *structure* of `uk.json` but localise the *jokes*: potholes are
  universal, but Freddos might not be.
- Give spoof parties local mythos — every country has a Binface of its own.
- Keep `blurb`s under ~10 words; they appear in tight UI spaces.
- 12–20 regions is the sweet spot for a 30–45 minute game.
