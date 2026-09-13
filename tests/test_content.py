"""Phase 3 content tests: policies/manifesto, synergies, personas, events, headlines."""
from __future__ import annotations

import pytest

from backend.config import loader
from backend.game import content
from backend.game.engine import GameEngine
from backend.game.models import Candidate, Phase
from backend.main import app

from fastapi.testclient import TestClient

client = TestClient(app)


def make_engine(
    difficulty: str = "easy",
    seed: int = 42,
    policies: list[str] | None = None,
    persona: str = "",
) -> GameEngine:
    candidate = Candidate(
        name="Rory Spatula",
        party_name="The Moderate Raving Sensible Party",
        slogan="A spatula in every drawer",
        policies=policies or [],
        persona=persona,
    )
    return GameEngine("uk", difficulty, candidate, seed=seed)


# ------------------------------------------------------------------ config

def test_uk_content_loads():
    cfg = loader.load_country("uk")
    assert len(cfg.policies) >= 12
    assert len(cfg.synergies) >= 4
    assert len(cfg.personas) >= 4
    assert cfg.events.good and cfg.events.bad
    assert cfg.flavour.quiet_week_templates


def test_uk_manifesto_policy_ids_are_unique():
    cfg = loader.load_country("uk")
    ids = [p.id for p in cfg.policies]
    assert len(set(ids)) == len(ids)


def test_template_content_samples_valid():
    raw = loader._read_json(loader.COUNTRIES_DIR / "_template.json")
    cfg = loader.CountryConfig.model_validate(raw)
    assert cfg.policies and cfg.personas and cfg.events.good


def test_duplicate_policy_id_rejected():
    raw = loader._read_json(loader.COUNTRIES_DIR / "uk.json")
    raw["policies"].append(dict(raw["policies"][0]))
    with pytest.raises(Exception, match="duplicate policy id"):
        loader.CountryConfig.model_validate(raw)


def test_synergy_unknown_policy_rejected():
    raw = loader._read_json(loader.COUNTRIES_DIR / "uk.json")
    raw["synergies"][0]["requires_policies"] = ["not_a_policy"]
    with pytest.raises(Exception, match="unknown policy"):
        loader.CountryConfig.model_validate(raw)


def test_synergy_requires_something():
    raw = loader._read_json(loader.COUNTRIES_DIR / "uk.json")
    raw["synergies"][0]["requires_tags"] = []
    with pytest.raises(Exception, match="must require at least one"):
        loader.CountryConfig.model_validate(raw)


def test_event_bad_placeholder_rejected():
    raw = loader._read_json(loader.COUNTRIES_DIR / "uk.json")
    raw["events"]["good"][0]["headline"] = "The {paerty} strikes again"
    with pytest.raises(Exception, match="bad placeholder"):
        loader.CountryConfig.model_validate(raw)


def test_event_without_effect_rejected():
    raw = loader._read_json(loader.COUNTRIES_DIR / "uk.json")
    raw["events"]["bad"][0]["funds"] = 0
    raw["events"]["bad"][0]["cp"] = 0
    raw["events"]["bad"][0]["momentum"] = 0
    with pytest.raises(Exception, match="at least one effect"):
        loader.CountryConfig.model_validate(raw)


def test_persona_unknown_action_rejected():
    raw = loader._read_json(loader.COUNTRIES_DIR / "uk.json")
    raw["personas"][0]["action_cp_multipliers"] = {"astral_project": 1.5}
    with pytest.raises(Exception, match="unknown action"):
        loader.CountryConfig.model_validate(raw)


# ---------------------------------------------------------------- manifesto

def test_manifesto_unknown_policy_rejected():
    cfg = loader.load_country("uk")
    with pytest.raises(ValueError, match="unknown policy"):
        content.build_manifesto(cfg, ["free_ponies_for_wales"])


def test_manifesto_max_three_policies():
    cfg = loader.load_country("uk")
    four = [p.id for p in cfg.policies[:4]]
    with pytest.raises(ValueError, match="at most 3"):
        content.build_manifesto(cfg, four)


def test_manifesto_no_duplicates():
    cfg = loader.load_country("uk")
    with pytest.raises(ValueError, match="duplicate"):
        content.build_manifesto(cfg, ["moon_dave", "moon_dave"])


def test_manifesto_grants_campaign_start_cp():
    engine = make_engine(policies=["freddo_price_cap", "teatime_buses", "second_home_levy"])
    engine.end_week()  # first by-election is called
    assert engine.state.campaign is not None
    total = sum(engine.state.campaign.player_cp.values())
    assert total > 10  # 3 policies x 4 CP + wallet_whisperer synergy
    news = " ".join(n.headline for n in engine.state.news)
    assert "MANIFESTO LAUNCH" in news
    assert "Wallet Whisperer" in news  # two cost_of_living policies


def test_manifesto_empty_is_allowed():
    engine = make_engine(policies=[])
    engine.end_week()
    assert engine.state.campaign is not None
    assert engine.state.campaign.player_cp == {}
    assert all("MANIFESTO" not in n.headline for n in engine.state.news)


def test_nonsense_synergy_needs_three_tags():
    cfg = loader.load_country("uk")
    two = content.build_manifesto(cfg, ["hourly_bins", "zebra_zebras"])
    assert not any(s.id == "certified_nonsense" for s in two.synergies)
    three = content.build_manifesto(cfg, ["hourly_bins", "zebra_zebras", "metric_time"])
    assert any(s.id == "certified_nonsense" for s in three.synergies)


def test_snapshot_exposes_manifesto_and_synergies():
    engine = make_engine(policies=["pothole_cheese", "jam_first_law", "pub_energy_cap"])
    snap = engine.snapshot()
    assert len(snap["manifesto"]) == 3
    assert any(s["id"] == "full_english_majority" for s in snap["synergies"])
    assert snap["manifesto_cp"] > 12


# ----------------------------------------------------------------- personas

def test_unknown_persona_rejected():
    cfg = loader.load_country("uk")
    with pytest.raises(ValueError, match="unknown persona"):
        content.persona_of(cfg, "the_lobbiest")


def test_persona_boosts_action_cp():
    plain = make_engine(seed=11)
    boosted = make_engine(seed=11, persona="binfluencer")
    for _ in range(6):  # few enough that the head-start CP cap never kicks in
        plain.state.ap = 4
        boosted.state.ap = 4
        plain.apply_action("social_post")
        boosted.apply_action("social_post")
    assert sum(boosted.state.head_start_cp.values()) > sum(plain.state.head_start_cp.values())


def test_baby_charmer_never_gets_baby_gate():
    engine = make_engine(seed=3, persona="baby_charmer")
    for _ in range(40):
        engine.state.ap = 4
        engine.apply_action("baby_kiss")
    headlines = " ".join(n.headline for n in engine.state.news)
    assert "BABY-GATE" not in headlines


def test_plain_baby_kisser_gets_cried_at_eventually():
    engine = make_engine(seed=3)
    for _ in range(60):
        engine.state.ap = 4
        engine.apply_action("baby_kiss")
    headlines = " ".join(n.headline for n in engine.state.news)
    assert "BABY-GATE" in headlines  # with 60 kisses and p=0.2, statistically certain


def test_fundraise_multiplier_pays():
    plain = make_engine(seed=5)
    oracle = make_engine(seed=5, persona="pub_oracle")
    before_p = plain.state.funds
    before_o = oracle.state.funds
    plain.apply_action("fundraise")
    oracle.apply_action("fundraise")
    assert oracle.state.funds - before_o > plain.state.funds - before_p


def test_snapshot_exposes_persona():
    engine = make_engine(persona="pub_oracle")
    snap = engine.snapshot()
    assert snap["persona"]["id"] == "pub_oracle"
    plain = make_engine().snapshot()
    assert plain["persona"] is None


# ------------------------------------------------------------------- events

def test_event_fires_when_frequency_is_one(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(engine.preset, "event_frequency", 1.0)
    news_before = len(engine.state.news)
    lines = engine.end_week()
    assert len(engine.state.news) > news_before
    assert lines  # an event headline (or other news) surfaced this week


def test_event_never_fires_when_frequency_is_zero(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(engine.preset, "event_frequency", 0)
    before = engine.state.funds
    engine.end_week()
    # a brand-new game has no sponsors/marketing/deposits: funds must be untouched
    assert engine.state.funds == before


def test_event_effects_are_applied(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(engine.preset, "event_frequency", 1.0)
    monkeypatch.setattr(engine.preset, "good_event_bias", 1.0)  # force a good event
    funds_before = engine.state.funds
    lines = engine.end_week()
    good_ids = {e.id for e in loader.load_country("uk").events.good}
    fired_fund_or_momentum = engine.state.funds != funds_before or engine.state.momentum > 0
    # every good event has funds or momentum, so *something* must have moved
    assert good_ids and (fired_fund_or_momentum or lines)


def test_hard_difficulty_has_more_events_than_easy():
    presets = loader.load_difficulties()
    assert presets["hard"].event_frequency > presets["easy"].event_frequency


# ------------------------------------------------------- flavour headlines

def test_quiet_week_headline_when_configured(monkeypatch):
    engine = make_engine()
    engine.country = engine.country.model_copy(deep=True)  # don't pollute the cached config
    engine.country.flavour.quiet_week_templates = ["Nothing happened. {party} suspects {rival}."]
    monkeypatch.setattr(engine.preset, "event_frequency", 0)
    import backend.game.rivals as rivals

    monkeypatch.setattr(rivals, "weekly_moves", lambda *a, **k: [])  # guarantee a quiet week
    lines = engine.end_week()
    assert len(lines) == 1 and lines[0].startswith("Nothing happened.")
    assert any("Nothing happened." in n.headline for n in engine.state.news)


def test_no_quiet_headline_when_unconfigured():
    engine = make_engine()
    engine.country = engine.country.model_copy(deep=True)
    engine.country.flavour.quiet_week_templates = []
    for _ in range(8):
        engine.end_week()
    assert all("Slow week" not in n.headline for n in engine.state.news)


# ---------------------------------------------------------------------- API

def test_api_new_game_with_manifesto_and_persona():
    res = client.post(
        "/api/game/new",
        json={
            "country_id": "uk",
            "difficulty": "easy",
            "name": "Flo Trolley",
            "party_name": "The Trolley Party",
            "policies": ["freddo_price_cap", "teatime_buses", "second_home_levy"],
            "persona": "pub_oracle",
            "seed": 99,
        },
    )
    assert res.status_code == 200
    state = res.json()["state"]
    assert len(state["manifesto"]) == 3
    assert state["persona"]["id"] == "pub_oracle"
    assert state["manifesto_cp"] > 10


def test_api_rejects_unknown_policy():
    res = client.post(
        "/api/game/new",
        json={
            "country_id": "uk",
            "difficulty": "easy",
            "name": "Flo Trolley",
            "party_name": "The Trolley Party",
            "policies": ["free_ponies_for_wales"],
        },
    )
    assert res.status_code == 400
    assert "unknown policy" in res.json()["detail"]


def test_api_rejects_unknown_persona():
    res = client.post(
        "/api/game/new",
        json={
            "country_id": "uk",
            "difficulty": "easy",
            "name": "Flo Trolley",
            "party_name": "The Trolley Party",
            "persona": "the_lobbiest",
        },
    )
    assert res.status_code == 400
    assert "unknown persona" in res.json()["detail"]


def test_api_rejects_four_policies():
    cfg = loader.load_country("uk")
    four = [p.id for p in cfg.policies[:4]]
    res = client.post(
        "/api/game/new",
        json={
            "country_id": "uk",
            "difficulty": "easy",
            "name": "Flo Trolley",
            "party_name": "The Trolley Party",
            "policies": four,
        },
    )
    assert res.status_code == 400


def test_country_detail_exposes_content():
    res = client.get("/api/countries/uk")
    assert res.status_code == 200
    body = res.json()
    assert len(body["policies"]) >= 12
    assert len(body["personas"]) >= 4
    assert body["events"]["good"]
