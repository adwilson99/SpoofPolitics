"""Election simulation tests: maths sanity, the £500 deposit rule, winning, GE."""
from __future__ import annotations

import random

import pytest

from backend.config import loader
from backend.game import elections
from backend.game.engine import GameEngine
from backend.game.models import Candidate, Phase


def make_engine(difficulty: str = "medium", seed: int = 42) -> GameEngine:
    candidate = Candidate(name="Nessa Binliner", party_name="Bin Blitz Party", slogan="Bins by breakfast")
    return GameEngine("uk", difficulty, candidate, seed=seed)


# ------------------------------------------------------------ sim internals

def test_votes_always_sum_to_votes_cast():
    country = loader.load_country("uk")
    rng = random.Random(123)
    for seed_shift in range(10):
        region = country.regions[seed_shift % len(country.regions)]
        mood = {p.id: rng.uniform(0.8, 1.2) for p in country.all_parties}
        result = elections.run_byelection(
            country=country, region=region, mood=mood,
            player_cp={"youth": 10, "middle": 5, "pensioner": 2},
            momentum=0.5, rival_cp={}, rng=rng,
        )
        total = sum(v for _, _, v in result.standings)
        assert total == result.votes_cast > 0


def test_strong_campaign_wins_the_seat():
    country = loader.load_country("uk")
    region = country.regions[0]
    mood = {p.id: 1.0 for p in country.all_parties}
    result = elections.run_byelection(
        country=country, region=region, mood=mood,
        player_cp={"youth": 60, "middle": 60, "pensioner": 60},
        momentum=2.0, rival_cp={"labour": 8}, rng=random.Random(5),
    )
    assert result.won is True
    assert result.player_rank == 1
    assert result.player_share > 0.2


def test_neglected_campaign_loses_deposit():
    country = loader.load_country("uk")
    region = country.regions[0]
    mood = {p.id: 1.0 for p in country.all_parties}
    result = elections.run_byelection(
        country=country, region=region, mood=mood,
        player_cp={}, momentum=0.0, rival_cp={}, rng=random.Random(9),
    )
    assert result.won is False
    # the £500 rule scales: neither the vote floor nor the 5% share bar is met
    assert result.player_share < country.deposit.share_threshold
    assert result.deposit_lost is True


def test_simulation_is_deterministic_per_seed():
    country = loader.load_country("uk")
    region = country.regions[3]
    mood = {p.id: 1.05 for p in country.all_parties}

    def run(seed: int):
        return elections.run_byelection(
            country=country, region=region, mood=mood,
            player_cp={"youth": 20, "middle": 10, "pensioner": 10},
            momentum=1.0, rival_cp={"reform": 5}, rng=random.Random(seed),
        )

    a, b = run(777), run(777)
    assert a.standings == b.standings
    assert a.player_votes == b.player_votes


def test_momentum_helps():
    country = loader.load_country("uk")
    region = country.regions[1]
    mood = {p.id: 1.0 for p in country.all_parties}

    def run(momentum: float):
        rng = random.Random(31337)
        return elections.run_byelection(
            country=country, region=region, mood=mood,
            player_cp={"youth": 25, "middle": 25, "pensioner": 25},
            momentum=momentum, rival_cp={}, rng=rng,
        )

    assert run(3.0).player_share > run(0.0).player_share


def test_region_locked_parties_absent_elsewhere():
    country = loader.load_country("uk")
    region = country.regions[0]  # Cornwall: no SNP, no Plaid
    ballot = elections.ballot_for_region(country, region, random.Random(1))
    ids = {p.id for p in ballot}
    assert "snp" not in ids and "plaid" not in ids


def test_ballot_respects_max_candidates():
    country = loader.load_country("uk")
    for region in country.regions[:5]:
        ballot = elections.ballot_for_region(country, region, random.Random(2))
        assert len(ballot) <= country.election.max_candidates_on_ballot - 1  # + player


# ------------------------------------------------------------ full-game flow

def grind_to_victory(engine: GameEngine, target_wins: int, max_weeks: int = 60) -> None:
    """Campaign hard every week; guarantees wins given enough weeks."""
    simple = {"canvass", "leaflets", "social_post", "baby_kiss", "pub_visit",
              "radio_phone_in", "rally", "press_stunt", "fundraise"}
    for _ in range(max_weeks):
        if engine.state.game_over.over:
            return
        # keep funds topped up
        while engine.state.funds < 400 and engine.state.ap > 0:
            engine.apply_action("fundraise")
        while engine.state.ap > 0:
            affordable = [
                a["id"] for a in engine.snapshot()["actions"]
                if a["id"] in simple and a["affordable"]
            ]
            if not affordable:
                break
            engine.apply_action(engine.rng.choice(sorted(affordable)))
        engine.end_week()
        if engine.state.wins >= target_wins:
            return
    pytest.fail(f"bot failed to reach {target_wins} wins in {max_weeks} weeks")


def test_easy_bot_wins_two_byelections_then_ge_unlocks():
    engine = make_engine("easy", seed=1001)
    grind_to_victory(engine, target_wins=2)
    assert engine.state.wins >= 2
    assert engine.state.ge_unlocked is True
    assert engine.state.last_byresult is not None


def test_full_campaign_to_general_election():
    engine = make_engine("easy", seed=2002)
    grind_to_victory(engine, target_wins=2)
    engine.apply_action("force_ge")
    engine.end_week()  # GE campaign week
    engine.end_week()  # election night
    assert engine.state.game_over.over is True
    ge = engine.state.ge_result
    assert ge is not None
    assert sum(ge.seats.values()) == len(loader.load_country("uk").regions)
    assert sum(ge.national_votes.values()) > 0
    assert 1 <= ge.player_rank_seats <= len(ge.seats)


def test_deposit_rule_enforced_in_real_game():
    engine = make_engine("medium", seed=3003)
    engine.preset.event_frequency = 0  # keep funds exact: no random windfalls
    # coast through the first by-election without lifting a finger
    for _ in range(5):
        engine.end_week()
    assert engine.state.last_byresult is not None
    result = engine.state.last_byresult
    if result.deposit_lost:
        assert engine.state.funds == 1200 - 500
        assert engine.state.deposits_lost == 1
    else:
        assert engine.state.funds >= 1200  # lucked into a strong showing


def test_bankruptcy_game_over():
    engine = make_engine("hard", seed=4004)
    engine.state.funds = 0
    engine.state.deposit_forgiveness = 0
    engine.state.ge_turn = 99  # keep the GE clock out of it; we want the deposit kill
    engine.preset.scandal_magnitude = 0  # silence scandals; we want the deposit kill
    engine.preset.event_frequency = 0  # and random windfalls; we want the deposit kill
    # keep losing deposits until funds go negative
    for _ in range(40):
        if engine.state.game_over.over:
            break
        engine.end_week()
    assert engine.state.game_over.over is True
    assert engine.state.game_over.victory is False
    assert "Bankrupt" in engine.state.game_over.reason or "bankrupt" in engine.state.game_over.reason.lower()
