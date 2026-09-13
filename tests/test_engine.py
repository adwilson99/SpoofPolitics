"""Engine mechanic tests: actions, funds, sponsors, scandals, calendar, GE flow."""
from __future__ import annotations

import pytest

from backend.game.engine import GameEngine
from backend.game.models import Candidate, Phase


def make_engine(difficulty: str = "easy", seed: int = 42) -> GameEngine:
    candidate = Candidate(name="Rory Spatula", party_name="The Moderate Raving Sensible Party", slogan="A spatula in every drawer")
    return GameEngine("uk", difficulty, candidate, seed=seed)


def test_new_game_matches_difficulty_preset():
    engine = make_engine("easy")
    assert engine.state.funds == 2000
    assert engine.state.ap == 4
    assert engine.state.ge_turn == 16
    assert engine.state.deposit_forgiveness == 1
    assert engine.state.phase == Phase.BETWEEN


def test_opening_news_exists():
    engine = make_engine()
    assert len(engine.state.news) >= 1
    assert any("TO STAND" in n.headline for n in engine.state.news)


def test_action_spends_ap_and_resets_weekly():
    engine = make_engine()
    before_ap = engine.state.ap
    feedback = engine.apply_action("canvass")
    assert feedback
    assert engine.state.ap == before_ap - 1


def test_action_requires_funds():
    engine = make_engine()
    engine.state.funds = 10
    with pytest.raises(ValueError, match="not enough funds"):
        engine.apply_action("leaflets")  # costs 40


def test_action_requires_ap():
    engine = make_engine()
    engine.state.ap = 0
    with pytest.raises(ValueError, match="not enough action points"):
        engine.apply_action("canvass")


def test_head_start_banking_when_no_campaign():
    engine = make_engine()
    engine.apply_action("canvass")
    assert engine.state.campaign is None
    assert sum(engine.state.head_start_cp.values()) > 0


def test_head_start_cap():
    engine = make_engine()
    for _ in range(30):
        engine.state.ap = 4
        engine.apply_action("canvass")
    assert sum(engine.state.head_start_cp.values()) <= 46


def test_marketing_buys_cp_and_deducts_money():
    engine = make_engine()
    funds = engine.state.funds
    feedback = engine.apply_action("marketing", {"channel_id": "billboard"})
    assert "Billboard" in feedback
    assert engine.state.funds == funds - 400
    assert sum(engine.state.head_start_cp.values()) > 0
    assert engine.state.ap == engine.state.ap_per_week  # marketing costs no AP


def test_marketing_unknown_channel_rejected():
    engine = make_engine()
    with pytest.raises(ValueError, match="unknown marketing channel"):
        engine.apply_action("marketing", {"channel_id": "sky_writing"})


def test_sponsor_pays_and_risks():
    engine = make_engine()
    funds = engine.state.funds
    feedback = engine.apply_action("sponsor", {"tier_id": "shady_billionaire"})
    assert "Signed" in feedback
    assert engine.state.funds == funds + 5000
    assert len(engine.state.sponsors) == 1
    with pytest.raises(ValueError, match="already signed"):
        engine.apply_action("sponsor", {"tier_id": "shady_billionaire"})


def test_scandal_fires_with_risky_sponsors():
    engine = make_engine()
    engine.apply_action("sponsor", {"tier_id": "shady_billionaire"})
    engine.preset.scandal_magnitude = 10.0  # guarantee the press comes knocking
    engine.end_week()
    engine.end_week()
    assert engine.state.scandals >= 1


def test_scandal_removes_worst_sponsor():
    engine = make_engine()
    engine.apply_action("sponsor", {"tier_id": "pub_quiz"})
    engine.apply_action("sponsor", {"tier_id": "shady_billionaire"})
    engine.preset.scandal_magnitude = 10.0
    engine.end_week()
    engine.end_week()
    assert len(engine.state.sponsors) < 2


def test_calendar_starts_first_byelection():
    engine = make_engine()
    engine.end_week()  # week 1 -> 2: first campaign should be live
    assert engine.state.phase == Phase.BY_CAMPAIGN
    assert engine.state.campaign is not None
    assert engine.state.campaign.weeks_total == 3


def test_region_ownership_persists_after_byelection():
    engine = make_engine()
    engine.end_week()          # campaign called
    region_id = engine.state.campaign.region_id
    assert engine.state.region_owners == {}
    for _ in range(3):
        engine.end_week()      # fight to polling day
    assert region_id in engine.state.region_owners
    owner = engine.state.region_owners[region_id]
    result = engine.state.last_byresult
    if result.won:
        assert owner == "__player__"
    else:
        assert owner == result.standings[0][0]  # the actual winner, not the runner-up
    # it stays owned through subsequent quiet weeks
    engine.end_week()
    assert engine.state.region_owners[region_id] == owner
    assert engine.snapshot()["region_owners"] == engine.state.region_owners


def test_byelection_cycle_and_rest_week():
    engine = make_engine()
    for _ in range(4):
        engine.end_week()  # week 1 -> campaign weeks 2,3,4; resolved end of week 4
    assert engine.state.campaigns_fought == 1
    assert engine.state.phase == Phase.BETWEEN  # rest week
    engine.end_week()  # calendar rolls: second campaign starts
    assert engine.state.phase == Phase.BY_CAMPAIGN
    assert engine.state.campaigns_fought == 1  # not fought yet, just campaigning


def test_baby_kiss_earn_cp_and_sometimes_make_news():
    engine = make_engine(seed=7)
    for _ in range(25):
        engine.state.ap = 4
        engine.apply_action("baby_kiss")
    assert sum(engine.state.head_start_cp.values()) > 0
    headlines = " ".join(n.headline for n in engine.state.news)
    assert ("BABY-GATE" in headlines) or ("Heartwarming" in headlines)


def test_force_ge_requires_unlock():
    engine = make_engine()
    with pytest.raises(ValueError, match="momentum"):
        engine.apply_action("force_ge")


def test_force_ge_flow_to_game_over():
    engine = make_engine()
    engine.state.ge_unlocked = True
    engine.apply_action("force_ge")
    assert engine.state.ge_forced is True
    engine.end_week()  # GE campaign starts (1 week sprint)
    assert engine.state.phase == Phase.GE_CAMPAIGN
    engine.end_week()  # election night
    assert engine.state.game_over.over is True
    assert engine.state.ge_result is not None
    assert engine.state.phase == Phase.GAME_OVER


def test_end_week_after_game_over_rejected():
    engine = make_engine()
    engine.state.game_over.over = True
    with pytest.raises(ValueError, match="campaign is over"):
        engine.end_week()


def test_save_roundtrip_preserves_play():
    engine = make_engine()
    engine.apply_action("canvass")
    engine.end_week()
    data = engine.to_json()
    revived = GameEngine.from_json(data)
    assert revived.state.week == engine.state.week
    assert revived.state.funds == engine.state.funds
    assert revived.snapshot()["funds"] == engine.snapshot()["funds"]


def test_snapshot_shape():
    engine = make_engine()
    snap = engine.snapshot()
    for key in (
        "country", "funds", "ap", "momentum", "wins", "news", "polls",
        "actions", "sponsors", "sponsor_tiers", "marketing_channels", "game_over",
    ):
        assert key in snap
    action_ids = {a["id"] for a in snap["actions"]}
    assert {"canvass", "rally", "fundraise", "sponsor", "marketing"} <= action_ids
    assert "force_ge" not in action_ids  # locked at start
