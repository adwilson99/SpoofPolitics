"""Election simulation: from campaign points (CP) to votes.

Model (kept deliberately simple, tunable, and country-agnostic):

- Every party has a *base weight* in each region, derived from its demographic
  appeal (youth/middle/pensioner) blended with the region's sentiment axes
  (niche_joy, protest_mood, cost_of_living, change_hungry), scaled by a
  per-game national mood multiplier.
- The player starts with a tiny base weight (an unknown independent) that grows
  with accumulated campaign points (CP). Momentum gives a small multiplier.
- Rivals' weights grow with their own weekly CP (scaled by difficulty
  aggression) — they campaign too.
- Weights get multiplicative log-normal noise, are normalised into shares, then
  integerised into votes via largest-remainder. Turnout rises a little when a
  campaign is exciting (joke candidates boost turnout — canonically accurate).
- The £500 deposit rule: under `vote_threshold` votes and the deposit is gone.
"""
from __future__ import annotations

import math
import random

from backend.config.loader import CountryConfig, PartyCfg, RegionCfg
from backend.game.models import ByelectionResult, GEResult

PLAYER_ID = "__player__"

PLAYER_BASE_WEIGHT = 0.2          # an unknown independent (~1-2% when ignored)
PLAYER_CP_WEIGHT_SCALE = 7.0      # CP converts into weight with saturation
CP_HALF_SATURATION = 30.0         # CP at which a by-election campaign is "half effective"
MOMENTUM_WEIGHT_BONUS = 0.05      # per momentum star (capped at MOMENTUM_CAP stars)
MOMENTUM_CAP = 3.0                # more stars than this stop helping weight
RIVAL_CP_HALF_SATURATION = 36.0
GE_CP_HALF_SATURATION = 70.0      # national campaigns are harder to move
NOISE_SIGMA = 0.07                # multiplicative share noise
BASE_TURNOUT_BOOST = 0.04         # max turnout bump from campaign excitement
COALITION_BASE_CHANCE = 0.3


def eligible_parties(country: CountryConfig, region: RegionCfg) -> list[PartyCfg]:
    return [p for p in country.all_parties if p.regions is None or region.id in p.regions]


def ballot_for_region(country: CountryConfig, region: RegionCfg, rng: random.Random) -> list[PartyCfg]:
    """Pick who is on the ballot paper: player + majors + sampled spoofs, capped."""
    cap = country.election.max_candidates_on_ballot
    eligible = eligible_parties(country, region)
    majors = [p for p in eligible if p.id in {m.id for m in country.major_parties}]
    spoofs = [p for p in eligible if p.id in {s.id for s in country.spoof_parties}]
    slots = max(0, cap - 1 - len(majors))  # -1 for the player
    chosen_spoofs = rng.sample(spoofs, min(len(spoofs), slots))
    return majors + chosen_spoofs


def base_weight(party: PartyCfg, region: RegionCfg, mood: float) -> float:
    d = region.demographics
    demo = (
        party.appeal.youth * d.youth
        + party.appeal.middle * d.middle
        + party.appeal.pensioner * d.pensioner
    ) / 100.0
    ax = party.axis_fit
    axis = (
        0.4 * ax.niche_joy * d.niche_joy
        + 0.4 * ax.protest_mood * d.protest_mood
        + 0.4 * ax.cost_of_living * d.cost_of_living
        + 0.4 * ax.change_hungry * d.change_hungry
    )
    return (demo + 0.5 * axis) * mood


def _cp_multiplier(cp: float, half: float) -> float:
    return 1.0 + (2.2 * cp) / (cp + half)


def _player_weight(cp_total: float, momentum: float, half: float) -> float:
    """Player weight: tiny ignored base, saturating growth with campaign points."""
    w = PLAYER_BASE_WEIGHT + PLAYER_CP_WEIGHT_SCALE * cp_total / (cp_total + half)
    return w * (1.0 + MOMENTUM_WEIGHT_BONUS * min(momentum, MOMENTUM_CAP))


def _integerise(weights: dict[str, float], total_votes: int) -> dict[str, int]:
    """Largest remainder method so votes always sum exactly to total_votes."""
    weight_total = sum(weights.values())
    shares = {k: w / weight_total for k, w in weights.items()}
    raw = {k: s * total_votes for k, s in shares.items()}
    votes = {k: int(v) for k, v in raw.items()}
    remaining = total_votes - sum(votes.values())
    by_fraction = sorted(raw, key=lambda k: raw[k] - votes[k], reverse=True)
    for k in by_fraction[:remaining]:
        votes[k] += 1
    return votes


def _noisy(weights: dict[str, float], rng: random.Random, sigma: float = NOISE_SIGMA) -> dict[str, float]:
    out = {}
    for k, w in weights.items():
        if w <= 0:
            out[k] = 0.0
        else:
            out[k] = w * math.exp(rng.gauss(0.0, sigma))
    return out


def _votes_cast(region: RegionCfg, cp_total: float, rng: random.Random) -> tuple[int, float]:
    excitement = BASE_TURNOUT_BOOST * min(1.0, cp_total / 60.0)
    turnout = min(0.85, max(0.3, region.turnout_base + excitement + rng.gauss(0.0, 0.02)))
    return int(region.electorate * turnout), turnout


def run_byelection(
    country: CountryConfig,
    region: RegionCfg,
    mood: dict[str, float],
    player_cp: dict[str, float],
    momentum: float,
    rival_cp: dict[str, float],
    rng: random.Random,
) -> ByelectionResult:
    ballot = ballot_for_region(country, region, rng)
    cp_total = sum(player_cp.values())

    weights: dict[str, float] = {}
    for party in ballot:
        weights[party.id] = base_weight(party, region, mood.get(party.id, 1.0)) * _cp_multiplier(
            rival_cp.get(party.id, 0.0), RIVAL_CP_HALF_SATURATION
        )
    weights[PLAYER_ID] = _player_weight(cp_total, momentum, CP_HALF_SATURATION)

    votes_cast, turnout = _votes_cast(region, cp_total, rng)
    votes = _integerise(_noisy(weights, rng), votes_cast)

    standings = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
    names = {PLAYER_ID: country.offices.local_title + " candidate"}  # replaced by caller for display
    ranked: list[tuple[str, str, int]] = []
    player_rank = 0
    player_share = 0.0
    for rank, (pid, v) in enumerate(standings, start=1):
        share = v / votes_cast if votes_cast else 0.0
        if pid == PLAYER_ID:
            player_rank = rank
            player_share = share
            display = "?"  # engine substitutes candidate/party name
        else:
            display = country.party(pid).short
        ranked.append((pid, display, v))

    won = player_rank == 1
    player_votes = votes[PLAYER_ID]
    # The £500 rule, scaled: lose if you clear neither the absolute vote floor
    # nor the share-of-votes-cast bar (counties come in different sizes).
    deposit_lost = not won and (
        player_votes < country.deposit.vote_threshold
        or player_share < country.deposit.share_threshold
    )
    return ByelectionResult(
        region_id=region.id,
        region_name=region.name,
        votes_cast=votes_cast,
        turnout=turnout,
        standings=ranked,
        player_votes=player_votes,
        player_rank=player_rank,
        player_share=round(player_share, 4),
        deposit_lost=deposit_lost,
        won=won,
    )


def run_general_election(
    country: CountryConfig,
    mood: dict[str, float],
    player_cp: dict[str, float],
    momentum: float,
    rival_cp: dict[str, float],
    rng: random.Random,
) -> GEResult:
    cp_total = sum(player_cp.values())
    seats: dict[str, int] = {PLAYER_ID: 0}
    national: dict[str, int] = {PLAYER_ID: 0}
    region_winners: dict[str, str] = {}

    for region in country.regions:
        ballot = ballot_for_region(country, region, rng)
        weights: dict[str, float] = {}
        for party in ballot:
            weights[party.id] = base_weight(party, region, mood.get(party.id, 1.0)) * _cp_multiplier(
                rival_cp.get(party.id, 0.0), GE_CP_HALF_SATURATION
            )
        weights[PLAYER_ID] = _player_weight(cp_total, momentum, GE_CP_HALF_SATURATION)

        votes_cast, _ = _votes_cast(region, cp_total, rng)
        votes = _integerise(_noisy(weights, rng), votes_cast)
        winner = max(votes, key=lambda k: votes[k])
        region_winners[region.id] = winner
        seats[winner] = seats.get(winner, 0) + 1
        for pid, v in votes.items():
            national[pid] = national.get(pid, 0) + v

    def rank_of(pid: str, table: dict[str, int]) -> int:
        ordered = sorted(table.items(), key=lambda kv: kv[1], reverse=True)
        return [k for k, _ in ordered].index(pid) + 1

    seats_rank = rank_of(PLAYER_ID, seats)
    votes_rank = rank_of(PLAYER_ID, national)

    coalition_attempted = False
    coalition_success = False
    pm = seats_rank == 1
    if not pm and votes_rank == 1 and seats_rank == 2:
        # You won the country's hearts but not its counties: attempt coalition talks.
        coalition_attempted = True
        chance = COALITION_BASE_CHANCE + 0.1 * min(momentum, MOMENTUM_CAP)
        coalition_success = rng.random() < chance
        pm = coalition_success

    return GEResult(
        seats=seats,
        national_votes=national,
        player_rank_seats=seats_rank,
        player_rank_votes=votes_rank,
        coalition_attempted=coalition_attempted,
        coalition_success=coalition_success,
        region_winners=region_winners,
    )
