"""Rival parties' weekly campaign behaviour: personality-driven Phase 4 AI.

Every rival has config traits (aggression, focus, variance, stunt, attack, grit)
plus optional signature quips. Each week each rival picks a strategy:

- grind: standard campaigning (default)
- surge: final-week push — extra effort, extra chance of a headline stunt
- coast: comfortable leaders with low variance take their foot off the gas
- attack: go negative — drains the player's campaign energy, angry news

Debates: once per campaign, on the last full week (weeks_left == DEBATE_WEEK),
the player goes head-to-head with the rival frontrunner. Outcome depends on
campaign energy, momentum and the player persona's debate bonus.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from backend.config.loader import CountryConfig, PartyCfg
from backend.game import elections
from backend.game.models import CampaignState, EngineState, NewsItem

DEBATE_WEEK = 1  # fire the debate when the campaign clock reaches this many weeks left

_GENERIC_NEWS = [
    "{short} flood the local Facebook groups with graphics nobody asked for.",
    "{short} hold a photo op next to something vaguely photogenic.",
    "{short} activists descend on the high street in matching rosettes.",
    "A {short} leaflet arrives claiming credit for the weather.",
    "{short} release an attack advert; fact-checkers release a sigh.",
]

_SPOOF_NEWS = [
    "{short} arrive by unconventional vehicle. The crowd is delighted.",
    "{short} promise to fix everything, immediately, using nonsense.",
    "{short} out-poll several serious people, somehow.",
    "A {short} candidate is heckled; the heckler becomes a supporter.",
]

_STUNT_NEWS = [
    "{short} unveil a vehicle wrapped in their own logo. Traffic chaos. Brand awareness: total.",
    "{short} stage a stunt involving a barge, a brass band and mild legal jeopardy.",
    "{short} abseil down the town hall 'for the Baileywick of local democracy'. Nobody asked.",
    "{short} deliver a manifesto by treasure hunt. The first clue is underwater.",
]

_ATTACK_NEWS = [
    "{short} launch a attack ad quoting your manifesto selectively. Very selectively.",
    "{short} demand to know who *really* wrote your leaflets. You wrote them. Mostly.",
    "{short} hand out flyers titled 'Questions {player} Can't Answer'. There are forty.",
]

_DEBATE_WIN_FALLBACK = ["Even {short} manages a grudging nod. The nod makes the evening news."]
_DEBATE_LOSE_FALLBACK = ["{short} asks who costed your manifesto. The costing, it turns out, is a napkin."]


def _ctx(state: EngineState, country: CountryConfig, region_name: str) -> dict[str, str]:
    return {
        "short": "",  # filled per-party
        "player": state.candidate.party_name,
        "party": state.candidate.party_name.upper(),
        "region": region_name,
        "issue": "",
        "newspaper": country.flavour.newspapers[0],
        "show": country.flavour.tv_shows[0],
        "rival": country.major_parties[0].short,
        "symbol": country.currency.symbol,
        "amount": str(country.deposit.amount),
    }


def _quip(party: PartyCfg, rng: random.Random, ctx: dict[str, str], fallback: list[str]) -> str:
    if party.quips and rng.random() < 0.65:
        line = rng.choice(party.quips)
    else:
        line = rng.choice(fallback)
    ctx["short"] = party.short
    return line.format(**ctx)


def _drain_bucket(traits, campaign: CampaignState) -> str:
    if traits.focus != "even":
        return traits.focus
    buckets = {b: campaign.player_cp.get(b, 0.0) for b in ("youth", "middle", "pensioner")}
    return max(buckets, key=lambda b: buckets[b])


def weekly_moves(
    state: EngineState,
    country: CountryConfig,
    aggression: float,
    rng: random.Random,
) -> list[NewsItem]:
    """Rivals earn CP in the active campaign using their traits and strategies."""
    news: list[NewsItem] = []
    campaign = state.campaign
    if campaign is None:
        return news

    region = country.region(campaign.region_id) if campaign.region_id else None
    if campaign.kind == "general":
        eligible = country.all_parties
    elif region is not None:
        eligible = elections.eligible_parties(country, region)
    else:
        return news

    spoof_ids = {s.id for s in country.spoof_parties}
    max_cp = max((campaign.rival_cp.get(p.id, 0.0) for p in eligible), default=0.0)
    final_week = campaign.weeks_left <= DEBATE_WEEK + 1
    ctx = _ctx(state, country, region.name if region else country.election.generalelection_label)

    for party in eligible:
        traits = party.traits
        base_effort = rng.uniform(1.2, 3.2) * (1.0 + 0.03 * state.week)
        effort = base_effort * aggression * traits.aggression
        if campaign.kind == "general":
            # Rivals defend their national turf, hard.
            effort *= 0.9

        # --- pick a strategy ------------------------------------------------
        strategy = "grind"
        roll = rng.random()
        if final_week and roll < 0.2 + 0.25 * traits.aggression - 0.1 * traits.variance:
            strategy = "surge"
        elif max_cp > 8.0 and campaign.rival_cp.get(party.id, 0.0) >= max_cp - 1e-9 and rng.random() < 0.3 - 0.5 * traits.variance:
            strategy = "coast"
        elif rng.random() < traits.attack:
            strategy = "attack"

        if strategy == "surge":
            effort *= 1.6
        elif strategy == "coast":
            effort *= 0.55

        # --- stunts: CP spike + news ----------------------------------------
        made_news = False
        if rng.random() < traits.stunt + (0.25 if strategy == "surge" else 0.0):
            effort += base_effort * 0.8
            headline = _quip(party, rng, ctx, _STUNT_NEWS)
            news.append(NewsItem(week=state.week, headline=headline, tone="neutral"))
            made_news = True

        campaign.rival_cp[party.id] = campaign.rival_cp.get(party.id, 0.0) + round(effort, 2)

        # --- attacks: drain the player's campaign energy ---------------------
        if strategy == "attack":
            bucket = _drain_bucket(traits, campaign)
            drain = min(campaign.player_cp.get(bucket, 0.0) * (0.06 + 0.06 * traits.attack), 2.5)
            if drain > 0:
                campaign.player_cp[bucket] = max(0.0, campaign.player_cp[bucket] - drain)
            if not made_news:
                headline = _quip(party, rng, ctx, _ATTACK_NEWS)
                news.append(NewsItem(week=state.week, headline=headline, tone="bad"))
            made_news = True

        # --- ambient news ----------------------------------------------------
        if not made_news and rng.random() < 0.08 + 0.08 * traits.variance:
            pool = _SPOOF_NEWS if party.id in spoof_ids else _GENERIC_NEWS
            ctx["short"] = party.short
            news.append(
                NewsItem(
                    week=state.week,
                    headline=rng.choice(pool).format(**ctx),
                    tone="neutral",
                )
            )
    return news


# --------------------------------------------------------------------- debates

@dataclass
class DebateOutcome:
    headline: str
    tone: str
    lines: list[str] = field(default_factory=list)
    cp_factor: float = 1.0            # multiplies existing player CP
    cp_bonus: dict[str, float] = field(default_factory=dict)  # flat even-ish bonus
    momentum_delta: float = 0.0


def debate_night(
    state: EngineState,
    country: CountryConfig,
    rng: random.Random,
    debate_bonus: float = 0.0,
) -> DebateOutcome | None:
    """Player vs the rival frontrunner, live from a leisure centre near you."""
    campaign = state.campaign
    if campaign is None:
        return None
    region = country.region(campaign.region_id) if campaign.region_id else None
    if campaign.kind == "general":
        eligible = country.all_parties
    elif region is not None:
        eligible = elections.eligible_parties(country, region)
    else:
        return None
    if not eligible:
        return None

    frontrunner = max(eligible, key=lambda p: campaign.rival_cp.get(p.id, 0.0))
    player_total = sum(campaign.player_cp.values())
    rival_total = sum(campaign.rival_cp.values())
    # An unearned stage gets no applause: campaign energy is the whole story.
    cp_share = player_total / (player_total + rival_total) if (player_total + rival_total) > 0 else 0.0

    player_score = 0.15 + 1.1 * cp_share + 0.05 * state.momentum + debate_bonus + rng.gauss(0.0, 0.12)
    rival_score = frontrunner.traits.grit * 1.15 + rng.gauss(0.0, 0.12)

    ctx = _ctx(state, country, region.name if region else country.election.generalelection_label)
    ctx["short"] = frontrunner.short

    if player_score > rival_score + 0.05:
        bonus = 6.0 / 3.0
        return DebateOutcome(
            headline=f"DEBATE NIGHT: {ctx['party']} WINS THE ARGUMENT (TECHNICALLY)",
            tone="good",
            lines=[
                "DEBATE NIGHT: you were composed, quotable, and only slightly evasive.",
                _quip(frontrunner, rng, ctx, _DEBATE_WIN_FALLBACK),
            ],
            cp_bonus={"youth": bonus, "middle": bonus, "pensioner": bonus},
            momentum_delta=0.25,
        )
    if player_score < rival_score - 0.05:
        return DebateOutcome(
            headline=f"DEBATE NIGHT: {frontrunner.short.upper()} LANDS THE PUNCHLINES",
            tone="bad",
            lines=[
                "DEBATE NIGHT: you said 'the real question is' nine times. It became a drinking game.",
                _quip(frontrunner, rng, ctx, _DEBATE_LOSE_FALLBACK),
            ],
            cp_factor=0.88,
            momentum_delta=-0.25,
        )
    return DebateOutcome(
        headline="DEBATE NIGHT: DIGNIFIED, COMPETENT, IMMEDIATELY FORGOTTEN",
        tone="neutral",
        lines=["DEBATE NIGHT: a draw. The pundits call it 'spiky but pleasant'. Nobody clips it."],
        cp_bonus={"youth": 1.0, "middle": 1.0, "pensioner": 1.0},
    )
