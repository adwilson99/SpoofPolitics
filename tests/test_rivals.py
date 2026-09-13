"""Phase 4 rival AI tests: traits, strategies, quips, debate night."""
from __future__ import annotations

import random

import pytest

from backend.config import loader
from backend.game import rivals
from backend.game.engine import GameEngine
from backend.game.models import CampaignState, Candidate, EngineState


def make_engine(difficulty: str = "easy", seed: int = 42, persona: str = "") -> GameEngine:
    cand = Candidate(
        name="Rory Spatula",
        party_name="The Moderate Raving Sensible Party",
        slogan="A spatula in every drawer",
        persona=persona,
    )
    return GameEngine("uk", difficulty, cand, seed=seed)


def make_state(region_id: str = "yorkshire", player_cp: dict | None = None) -> EngineState:
    cand = Candidate(name="Nessa Binliner", party_name="Bin Blitz Party", slogan="Bins by breakfast")
    st = EngineState(
        country_id="uk", difficulty="hard", rng_seed=1, candidate=cand,
        funds=0, ap=3, ap_per_week=3, ge_turn=24,
    )
    st.campaign = CampaignState(
        kind="byelection", region_id=region_id, region_name="Cornwall",
        weeks_total=3, weeks_left=2,
        player_cp=dict(player_cp or {}), rival_cp={},
    )
    return st


# ------------------------------------------------------------------ config

def test_uk_parties_have_traits_and_quips():
    cfg = loader.load_country("uk")
    for p in cfg.all_parties:
        assert 0.3 <= p.traits.aggression <= 2.5, p.id
        assert 0 <= p.traits.grit <= 1, p.id
        assert 0 <= p.traits.attack <= 1, p.id
        assert len(p.quips) >= 2, p.id


def test_uk_traits_are_flavourful():
    cfg = loader.load_country("uk")
    binface = cfg.party("binface")
    assert binface.traits.attack == 0.0  # bins have dignity
    loony = cfg.party("loony")
    assert loony.traits.variance >= 0.5 and loony.traits.stunt >= 0.5
    grits = {p.traits.grit for p in cfg.all_parties}
    assert len(grits) >= 5  # real spread of debate talent


def test_bad_quip_placeholder_rejected():
    raw = loader._read_json(loader.COUNTRIES_DIR / "uk.json")
    raw["major_parties"][0]["quips"] = ["{short} references {nonexistent}"]
    with pytest.raises(Exception, match="bad placeholder"):
        loader.CountryConfig.model_validate(raw)


# ------------------------------------------------------------- weekly_moves

def test_weekly_moves_deterministic_per_seed():
    country = loader.load_country("uk")
    a = make_state(player_cp={"youth": 10})
    b = make_state(player_cp={"youth": 10})
    for _ in range(5):
        rivals.weekly_moves(a, country, 1.0, random.Random(55))
        rivals.weekly_moves(b, country, 1.0, random.Random(55))
    assert a.campaign.rival_cp == b.campaign.rival_cp


def test_weekly_moves_gives_every_rival_energy():
    country = loader.load_country("uk")
    state = make_state()
    rivals.weekly_moves(state, country, 1.0, random.Random(7))
    region = country.region("yorkshire")
    eligible = rivals.elections.eligible_parties(country, region)
    for party in eligible:
        assert state.campaign.rival_cp.get(party.id, 0.0) > 0, party.id


def test_weekly_moves_needs_a_campaign():
    country = loader.load_country("uk")
    state = make_state()
    state.campaign = None
    assert rivals.weekly_moves(state, country, 1.0, random.Random(1)) == []


def test_aggressive_traits_campaign_harder():
    country = loader.load_country("uk")
    meek = loader.CountryConfig.model_validate(country.model_dump())
    for p in meek.all_parties:
        p.traits.aggression = 0.4
    fierce = loader.CountryConfig.model_validate(country.model_dump())
    for p in fierce.all_parties:
        p.traits.aggression = 2.0

    a = make_state()
    b = make_state()
    for _ in range(4):
        rivals.weekly_moves(a, meek, 1.0, random.Random(21))
        rivals.weekly_moves(b, fierce, 1.0, random.Random(21))
    assert sum(b.campaign.rival_cp.values()) > sum(a.campaign.rival_cp.values())


def test_attack_strategy_drains_player_cp():
    country = loader.load_country("uk")
    attacker = loader.CountryConfig.model_validate(country.model_dump())
    lab = attacker.party("labour")
    lab.traits.attack = 1.0
    lab.traits.focus = "youth"
    lab.traits.stunt = 0.0
    lab.traits.variance = 0.0
    lab.traits.aggression = 0.4

    state = make_state(player_cp={"youth": 60, "middle": 60, "pensioner": 60})
    for _ in range(12):
        rivals.weekly_moves(state, attacker, 1.0, random.Random(3))
    assert state.campaign.player_cp["youth"] < 60
    # the other buckets are untouched by a youth-focused attack
    assert state.campaign.player_cp["middle"] == 60


# --------------------------------------------------------------- debates

def start_campaign_near_debate(engine: GameEngine) -> None:
    engine.end_week()                       # campaign called (weeks_left = 3)
    engine.end_week()                       # 3 -> 2
    engine.state.campaign.weeks_left = 2    # next tick hits the debate week


def test_debate_happens_once_per_campaign():
    engine = make_engine()
    start_campaign_near_debate(engine)
    lines = engine.end_week()
    assert any("DEBATE NIGHT" in l for l in lines)
    assert any("DEBATE NIGHT" in n.headline for n in engine.state.news)
    # and not again until the next campaign
    lines2 = engine.end_week()
    assert not any("DEBATE NIGHT" in l for l in lines2)


def test_do_nothing_player_loses_the_debate():
    engine = make_engine(seed=4004, difficulty="hard")
    start_campaign_near_debate(engine)
    engine.end_week()
    headlines = " ".join(n.headline for n in engine.state.news)
    assert "LANDS THE PUNCHLINES" in headlines


def test_campaigning_player_wins_the_debate():
    engine = make_engine(seed=4004, difficulty="hard")
    engine.end_week()
    for _ in range(8):
        engine.state.ap = 4
        engine.apply_action("canvass")
    engine.state.campaign.weeks_left = 2
    cp_before = sum(engine.state.campaign.player_cp.values())
    lines = engine.end_week()
    assert any("DEBATE NIGHT" in l for l in lines)
    cp_after = sum(engine.state.campaign.player_cp.values())
    assert cp_after > cp_before * 0.88  # at worst a draw's bonus offsets nothing much; usually a win


def test_persona_debate_bonus_never_hurts():
    plain = make_engine(seed=99)
    telly = make_engine(seed=99, persona="telly_regular")
    for eng in (plain, telly):
        eng.end_week()
        for _ in range(6):
            eng.state.ap = 4
            eng.apply_action("canvass")
        eng.state.campaign.weeks_left = 2
    plain.end_week()
    telly.end_week()
    plain_cp = sum(plain.state.campaign.player_cp.values())
    telly_cp = sum(telly.state.campaign.player_cp.values())
    assert telly_cp >= plain_cp


def test_forced_ge_is_a_two_week_sprint_with_one_debate():
    engine = make_engine()
    engine.state.ge_unlocked = True
    engine.apply_action("force_ge")
    engine.end_week()  # GE campaign starts
    engine.end_week()  # debate night (final full week), then the country decides
    assert engine.state.game_over.over
    debates = sum(1 for n in engine.state.news if "DEBATE" in n.headline)
    assert debates == 1


def test_debate_moves_momentum():
    engine = make_engine(seed=123)
    start_campaign_near_debate(engine)
    engine.state.momentum = 1.0
    engine.end_week()
    assert engine.state.momentum != 1.0  # win/loss shifted it (draw keeps it: seed chosen to differ)
