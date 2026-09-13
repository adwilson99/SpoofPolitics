"""Config system tests: loader validation, UK defaults, difficulty presets, API."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import loader
from backend.config.loader import COUNTRIES_DIR, CountryConfig
from backend.main import app

client = TestClient(app)


# ---------------- UK country config ----------------

def test_uk_config_loads():
    cfg = loader.load_country("uk")
    assert cfg.id == "uk"
    assert cfg.currency.symbol == "£"


def test_uk_deposit_rules_match_design():
    """The core game rule: £500 deposit, lost under 1,000 votes."""
    cfg = loader.load_country("uk")
    assert cfg.deposit.amount == 500
    assert cfg.deposit.vote_threshold == 1000


def test_uk_has_expected_roster():
    cfg = loader.load_country("uk")
    major_ids = {p.id for p in cfg.major_parties}
    spoof_ids = {p.id for p in cfg.spoof_parties}
    assert {"labour", "conservative", "reform", "libdem", "green"} <= major_ids
    assert {"binface", "buckethead", "loony", "darlik"} <= spoof_ids


def test_uk_regions_are_sane():
    cfg = loader.load_country("uk")
    assert len(cfg.regions) >= 16
    ids = [r.id for r in cfg.regions]
    assert len(set(ids)) == len(ids)
    for region in cfg.regions:
        d = region.demographics
        assert d.youth + d.middle + d.pensioner == 100
        assert region.local_issues, f"{region.id} has no local issues"


def test_snp_and_plaid_region_locking():
    cfg = loader.load_country("uk")
    snp = cfg.party("snp")
    plaid = cfg.party("plaid")
    assert snp.regions == ["scotland"]
    assert plaid.regions == ["wales"]
    assert cfg.party("binface").regions is None  # bins are everywhere
    # hard mode splits the nations and the parties follow
    split = loader.load_country("uk", split_counties=True)
    assert split.party("snp").regions == ["lowlands_scot", "highlands_scot"]
    assert split.party("plaid").regions == ["north_wales", "south_wales"]
    assert len(split.regions) == 32
    assert len(cfg.regions) == 16


def test_region_splits_validate():
    raw = loader._read_json(COUNTRIES_DIR / "uk.json")
    raw["regions"][0]["splits"][0]["electorate"] += 1000  # halves no longer sum
    with pytest.raises(ValidationError, match="must sum to the county electorate"):
        CountryConfig.model_validate(raw)
    raw = loader._read_json(COUNTRIES_DIR / "uk.json")
    raw["regions"][0]["splits"][1]["id"] = raw["regions"][0]["splits"][0]["id"]
    with pytest.raises(ValidationError, match="duplicate region split id"):
        CountryConfig.model_validate(raw)


def test_uk_marketing_and_sponsorship_present():
    cfg = loader.load_country("uk")
    channel_ids = [c.id for c in cfg.marketing_channels]
    assert {"billboard", "video_ads", "social_ads", "radio_spot", "newspaper_ad"} <= set(channel_ids)
    for channel in cfg.marketing_channels:
        assert channel.cost > 0 and channel.reach >= 1
    tiers = cfg.sponsorship.tiers
    amounts = [t.amount for t in tiers]
    risks = [t.scandal_risk for t in tiers]
    assert max(amounts) > min(amounts)  # escalation exists
    assert max(risks) <= 1.0
    assert any(t.scandal_risk >= 0.4 for t in tiers)  # a proper shady backer exists
    for template in cfg.sponsorship.scandal_headline_templates:
        assert "{party}" in template


def test_uk_disclaimer_present():
    cfg = loader.load_country("uk")
    assert "satire" in cfg.disclaimer.lower() or "satirical" in cfg.disclaimer.lower()
    assert "offend no one" in cfg.disclaimer


# ---------------- Template & validation ----------------

def test_template_config_is_valid():
    """The mod authoring template itself must pass validation."""
    raw = loader._read_json(COUNTRIES_DIR / "_template.json")
    cfg = CountryConfig.model_validate(raw)
    assert cfg.id == "example"


def test_duplicate_party_id_rejected():
    raw = loader._read_json(COUNTRIES_DIR / "uk.json")
    raw["spoof_parties"].append(copy.deepcopy(raw["major_parties"][0]))
    with pytest.raises(ValidationError, match="duplicate party id"):
        CountryConfig.model_validate(raw)


def test_duplicate_party_color_rejected():
    raw = loader._read_json(COUNTRIES_DIR / "uk.json")
    raw["spoof_parties"][0]["color"] = raw["major_parties"][0]["color"]
    with pytest.raises(ValidationError, match="duplicate party color"):
        CountryConfig.model_validate(raw)


def test_demographics_sum_rejected():
    raw = loader._read_json(COUNTRIES_DIR / "uk.json")
    raw["regions"][0]["demographics"]["youth"] += 5
    with pytest.raises(ValidationError, match="sum to 100"):
        CountryConfig.model_validate(raw)


def test_unknown_party_region_ref_rejected():
    raw = loader._read_json(COUNTRIES_DIR / "uk.json")
    raw["major_parties"][0]["regions"] = ["atlantis"]
    with pytest.raises(ValidationError, match="unknown region"):
        CountryConfig.model_validate(raw)


def test_missing_disclaimer_gets_default():
    raw = loader._read_json(COUNTRIES_DIR / "uk.json")
    del raw["disclaimer"]
    cfg = CountryConfig.model_validate(raw)
    assert "satirical" in cfg.disclaimer


# ---------------- Difficulty presets ----------------

def test_difficulty_presets_exist_and_escalate():
    presets = loader.load_difficulties()
    assert set(presets) == {"easy", "medium", "hard"}
    assert presets["easy"].wins_required == 2
    assert presets["medium"].wins_required == 3
    assert presets["hard"].wins_required == 5
    assert (
        presets["easy"].starting_funds
        > presets["medium"].starting_funds
        > presets["hard"].starting_funds
    )


def test_difficulty_marketing_and_scandal_knobs():
    presets = loader.load_difficulties()
    assert presets["easy"].marketing_efficiency > presets["hard"].marketing_efficiency
    assert presets["easy"].scandal_magnitude < presets["hard"].scandal_magnitude


# ---------------- API ----------------

def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_api_lists_countries():
    res = client.get("/api/countries")
    assert res.status_code == 200
    ids = [c["id"] for c in res.json()]
    assert "uk" in ids
    assert "example" not in ids  # template excluded


def test_api_country_detail():
    res = client.get("/api/countries/uk")
    assert res.status_code == 200
    body = res.json()
    assert body["deposit"]["amount"] == 500
    assert len(body["regions"]) >= 16
    assert body["sponsorship"] is not None


def test_api_unknown_country_404():
    assert client.get("/api/countries/atlantis").status_code == 404


def test_api_difficulties():
    res = client.get("/api/difficulties")
    assert res.status_code == 200
    assert set(res.json()) == {"easy", "medium", "hard"}


def test_frontend_served():
    res = client.get("/")
    assert res.status_code == 200
    assert "Loony to Westminster" in res.text
