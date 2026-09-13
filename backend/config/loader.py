"""Config loading & validation for Loony to Westminster.

Everything the game knows about a country lives in a JSON file under
config/countries/. This module parses and validates those files with pydantic,
so a typo in a country mod produces a clear error instead of weird game states.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import json
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_DIR = Path(__file__).resolve().parent
COUNTRIES_DIR = CONFIG_DIR / "countries"
DIFFICULTY_FILE = CONFIG_DIR / "difficulty.json"

DEFAULT_DISCLAIMER = (
    "This is a satirical comedy game. It is not affiliated with, endorsed by, or "
    "connected to any real political party, politician, or person. All characters "
    "and events are affectionate caricature. Intended purely for humour; meant to "
    "offend no one. Please vote responsibly in real life."
)


class _Forgiving(BaseModel):
    """Base model: unknown keys are ignored (allows `_hint` style keys in mods)."""

    model_config = ConfigDict(extra="ignore")


class Currency(_Forgiving):
    symbol: str = Field(min_length=1, max_length=4)
    code: str = Field(min_length=2, max_length=8)


class Deposit(_Forgiving):
    amount: int = Field(gt=0)
    vote_threshold: int = Field(gt=0)
    share_threshold: float = Field(default=0.05, ge=0.01, le=0.5)  # real UK rule: 5% of votes cast
    loss_line: str
    kept_line: str


class Offices(_Forgiving):
    local_title: str
    local_title_long: str
    leader_title: str
    residence: str
    chamber: str
    coalition_talks: str


class ElectionCfg(_Forgiving):
    byelection_label: str
    generalelection_label: str
    max_candidates_on_ballot: int = Field(default=8, ge=2, le=20)
    campaign_weeks_per_election: int = Field(default=3, ge=1, le=10)


class LeaderPersona(_Forgiving):
    name: str
    persona: str


class AppealVec(_Forgiving):
    """How strongly a party's message lands with each age bucket (multipliers)."""

    youth: float = Field(default=1.0, ge=0, le=3)
    middle: float = Field(default=1.0, ge=0, le=3)
    pensioner: float = Field(default=1.0, ge=0, le=3)


class AxisFit(_Forgiving):
    """How well a party fits each regional sentiment axis (0 = terrible, 1 = average, 2 = perfect)."""

    niche_joy: float = Field(default=0.5, ge=0, le=2)
    protest_mood: float = Field(default=0.5, ge=0, le=2)
    cost_of_living: float = Field(default=0.5, ge=0, le=2)
    change_hungry: float = Field(default=0.5, ge=0, le=2)


class RivalTraits(_Forgiving):
    """Phase 4 rival personality. Defaults keep trait-less mods behaving like before."""

    aggression: float = Field(default=1.0, ge=0.3, le=2.5)
    focus: str = Field(default="even", pattern=r"^(even|youth|middle|pensioner)$")
    variance: float = Field(default=0.2, ge=0.0, le=1.0)
    stunt: float = Field(default=0.15, ge=0.0, le=1.0)
    attack: float = Field(default=0.1, ge=0.0, le=1.0)
    grit: float = Field(default=0.5, ge=0.0, le=1.0)


class PartyCfg(_Forgiving):
    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    short: str
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    emoji: str = Field(min_length=1)
    leader: LeaderPersona
    blurb: str
    policies_hint: list[str] = Field(default_factory=list)
    regions: list[str] | None = None  # None = contests everywhere
    appeal: AppealVec = Field(default_factory=AppealVec)
    axis_fit: AxisFit = Field(default_factory=AxisFit)
    traits: RivalTraits = Field(default_factory=RivalTraits)
    quips: list[str] = Field(default_factory=list)

    @field_validator("quips")
    @classmethod
    def _quips_ok(cls, v: list[str]) -> list[str]:
        return [_validate_template("quip", q) for q in v]


class Demographics(_Forgiving):
    youth: int = Field(ge=0, le=100)
    middle: int = Field(ge=0, le=100)
    pensioner: int = Field(ge=0, le=100)
    niche_joy: float = Field(ge=0, le=1)
    protest_mood: float = Field(ge=0, le=1)
    cost_of_living: float = Field(ge=0, le=1)
    change_hungry: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ages_sum_to_100(self) -> "Demographics":
        total = self.youth + self.middle + self.pensioner
        if total != 100:
            raise ValueError(
                f"age percentages must sum to 100, got {total} "
                f"(youth={self.youth}, middle={self.middle}, pensioner={self.pensioner})"
            )
        return self


class RegionSplit(_Forgiving):
    """A hard-mode half of a county: same voters, finer map."""

    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    electorate: int = Field(ge=1000, le=10_000_000)
    demographics: Demographics | None = None  # inherited from parent when omitted
    turnout_base: float | None = Field(default=None, ge=0.1, le=1.0)
    local_issues: list[str] | None = Field(default=None, min_length=1, max_length=10)


class RegionCfg(_Forgiving):
    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    electorate: int = Field(ge=1000, le=10_000_000)
    turnout_base: float = Field(ge=0.1, le=1.0)
    demographics: Demographics
    local_issues: list[str] = Field(min_length=1, max_length=10)
    splits: list[RegionSplit] = Field(default_factory=list)  # used on difficulties with split_counties


class MarketingChannel(_Forgiving):
    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    emoji: str = Field(min_length=1)
    cost: int = Field(gt=0)
    reach: int = Field(ge=1, le=100)
    weeks: int = Field(ge=1, le=10)
    appeal: dict[str, float] = Field(default_factory=dict)
    blurb: str = ""

    @field_validator("appeal")
    @classmethod
    def _appeal_keys(cls, v: dict[str, float]) -> dict[str, float]:
        allowed = {"youth", "middle", "pensioner"}
        for key, value in v.items():
            if key not in allowed:
                raise ValueError(f"appeal keys must be one of {sorted(allowed)}, got '{key}'")
            if not 0 <= value <= 1:
                raise ValueError(f"appeal['{key}'] must be within 0-1, got {value}")
        return v


class SponsorTier(_Forgiving):
    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    emoji: str = Field(min_length=1)
    amount: int = Field(gt=0)
    scandal_risk: float = Field(ge=0, le=1)
    blurb: str = ""


class SponsorshipCfg(_Forgiving):
    intro_line: str = ""
    scandal_note: str = ""
    scandal_headline_templates: list[str] = Field(min_length=1, max_length=20)
    tiers: list[SponsorTier] = Field(min_length=1)

    @field_validator("scandal_headline_templates")
    @classmethod
    def _has_party_placeholder(cls, v: list[str]) -> list[str]:
        for t in v:
            if "{party}" not in t:
                raise ValueError(f"scandal headline template must contain '{{party}}': {t!r}")
        return v


class FlavourCfg(_Forgiving):
    newspapers: list[str] = Field(min_length=1)
    tv_shows: list[str] = Field(min_length=1)
    loading_lines: list[str] = Field(min_length=1)
    victory_lines: list[str] = Field(min_length=1)
    defeat_lines: list[str] = Field(min_length=1)
    deposit_loss_lines: list[str] = Field(min_length=1)
    quiet_week_templates: list[str] = Field(default_factory=list)

    @field_validator("quiet_week_templates")
    @classmethod
    def _quiet_templates_ok(cls, v: list[str]) -> list[str]:
        return [_validate_template("quiet_week_template", t) for t in v]


# ---------------------------------------------------------------- Phase 3 content

# Sample context used to validate every event/quiet-week template at load time.
# A typo'd placeholder (e.g. {paerty}) should fail config validation, not the game.
TEMPLATE_CONTEXT_SAMPLE: dict[str, str] = {
    "party": "The Sensible Party",
    "region": "Greater Muddle",
    "issue": "potholes",
    "newspaper": "The Daily Blab",
    "show": "Question Tyme",
    "rival": "Tories",
    "short": "Tories",
    "player": "The Sensible Party",
    "symbol": "£",
    "amount": "500",
}


def _validate_template(place: str, template: str) -> str:
    try:
        template.format(**TEMPLATE_CONTEXT_SAMPLE)
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(f"{place}: bad placeholder in template {template!r} ({exc})") from None
    return template


class PolicyCfg(_Forgiving):
    """A manifesto policy. Appeal = hidden demographic weights; tags drive synergies."""

    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    emoji: str = Field(min_length=1)
    blurb: str = ""
    appeal: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("appeal")
    @classmethod
    def _appeal_keys(cls, v: dict[str, float]) -> dict[str, float]:
        allowed = {"youth", "middle", "pensioner"}
        for key, value in v.items():
            if key not in allowed:
                raise ValueError(f"appeal keys must be one of {sorted(allowed)}, got '{key}'")
            if not 0 <= value <= 1:
                raise ValueError(f"appeal['{key}'] must be within 0-1, got {value}")
        return v


class SynergyCfg(_Forgiving):
    """Bonus for manifesto combos. A tag may be listed twice to require 2 matching policies."""

    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    emoji: str = Field(min_length=1)
    blurb: str = ""
    requires_tags: list[str] = Field(default_factory=list)
    requires_policies: list[str] = Field(default_factory=list)
    bonus_cp: float = Field(gt=0, le=30)
    bonus_bias: dict[str, float] = Field(default_factory=dict)

    @field_validator("bonus_bias")
    @classmethod
    def _bias_keys(cls, v: dict[str, float]) -> dict[str, float]:
        allowed = {"youth", "middle", "pensioner"}
        for key, value in v.items():
            if key not in allowed:
                raise ValueError(f"bonus_bias keys must be one of {sorted(allowed)}, got '{key}'")
            if not 0 <= value <= 1:
                raise ValueError(f"bonus_bias['{key}'] must be within 0-1, got {value}")
        return v


class PersonaCfg(_Forgiving):
    """A candidate archetype with small, engine-understood perks."""

    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    emoji: str = Field(min_length=1)
    blurb: str = ""
    action_cp_multipliers: dict[str, float] = Field(default_factory=dict)
    fundraise_multiplier: float = Field(default=1.0, ge=0.5, le=3.0)
    scandal_resistance: float = Field(default=0.0, ge=0.0, le=1.0)
    baby_cry_immunity: bool = False
    debate_bonus: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("action_cp_multipliers")
    @classmethod
    def _multiplier_range(cls, v: dict[str, float]) -> dict[str, float]:
        for action_id, mult in v.items():
            if not 0.1 <= mult <= 3.0:
                raise ValueError(f"action_cp_multipliers['{action_id}'] must be within 0.1-3.0, got {mult}")
        return v


class EventCfg(_Forgiving):
    """A weekly random event. Effects are magnitudes; the sign comes from good/bad."""

    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    headline: str
    weight: int = Field(default=1, ge=1, le=10)
    funds: int = Field(default=0, ge=0, le=5000)
    cp: float = Field(default=0.0, ge=0, le=20)
    momentum: float = Field(default=0.0, ge=0.0, le=3)

    @field_validator("headline")
    @classmethod
    def _placeholders_ok(cls, v: str) -> str:
        return _validate_template("event", v)

    @model_validator(mode="after")
    def _has_effect(self) -> "EventCfg":
        if not (self.funds or self.cp or self.momentum):
            raise ValueError(f"event '{self.id}' must have at least one effect (funds/cp/momentum)")
        return self


class EventsCfg(_Forgiving):
    good: list[EventCfg] = Field(default_factory=list)
    bad: list[EventCfg] = Field(default_factory=list)


class CountryConfig(_Forgiving):
    id: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    name: str
    flag_emoji: str = Field(min_length=1)
    game_title: str
    subtitle: str = ""
    currency: Currency
    deposit: Deposit
    offices: Offices
    election: ElectionCfg
    voter_axes: dict[str, str] = Field(default_factory=dict)
    marketing_channels: list[MarketingChannel] = Field(default_factory=list)
    sponsorship: SponsorshipCfg | None = None
    policies: list[PolicyCfg] = Field(default_factory=list)
    synergies: list[SynergyCfg] = Field(default_factory=list)
    personas: list[PersonaCfg] = Field(default_factory=list)
    events: EventsCfg = Field(default_factory=EventsCfg)
    major_parties: list[PartyCfg] = Field(min_length=2)
    spoof_parties: list[PartyCfg] = Field(default_factory=list)
    regions: list[RegionCfg] = Field(min_length=3)
    flavour: FlavourCfg
    disclaimer: str = DEFAULT_DISCLAIMER

    @model_validator(mode="after")
    def _cross_field_rules(self) -> "CountryConfig":
        # Unique party ids across both rosters + unique colors.
        all_parties = self.major_parties + self.spoof_parties
        party_ids = [p.id for p in all_parties]
        if len(set(party_ids)) != len(party_ids):
            dupes = {i for i in party_ids if party_ids.count(i) > 1}
            raise ValueError(f"duplicate party id(s): {sorted(dupes)}")
        colors = [p.color.lower() for p in all_parties]
        if len(set(colors)) != len(colors):
            dupes = {c for c in colors if colors.count(c) > 1}
            raise ValueError(f"duplicate party color(s): {sorted(dupes)}")

        # Region ids unique; party region refs must exist (splits count too:
        # mods may reference either the whole county or its hard-mode halves).
        region_ids = [r.id for r in self.regions]
        if len(set(region_ids)) != len(region_ids):
            dupes = {i for i in region_ids if region_ids.count(i) > 1}
            raise ValueError(f"duplicate region id(s): {sorted(dupes)}")
        split_ids = [s.id for r in self.regions for s in r.splits]
        if len(set(split_ids)) != len(split_ids):
            dupes = {i for i in split_ids if split_ids.count(i) > 1}
            raise ValueError(f"duplicate region split id(s): {sorted(dupes)}")
        if set(split_ids) & set(region_ids):
            raise ValueError(f"region split id(s) collide with county id(s): {sorted(set(split_ids) & set(region_ids))}")
        for r in self.regions:
            if r.splits and sum(s.electorate for s in r.splits) != r.electorate:
                raise ValueError(
                    f"region '{r.id}': split electorates ({sum(s.electorate for s in r.splits)}) "
                    f"must sum to the county electorate ({r.electorate})"
                )
        known_regions = set(region_ids) | set(split_ids)
        for p in self.major_parties + self.spoof_parties:
            if p.regions is not None:
                unknown = set(p.regions) - known_regions
                if unknown:
                    raise ValueError(f"party '{p.id}' references unknown region(s): {sorted(unknown)}")

        # Marketing channel ids unique.
        channel_ids = [c.id for c in self.marketing_channels]
        if len(set(channel_ids)) != len(channel_ids):
            dupes = {i for i in channel_ids if channel_ids.count(i) > 1}
            raise ValueError(f"duplicate marketing channel id(s): {sorted(dupes)}")

        # Sponsor tier ids unique.
        if self.sponsorship is not None:
            tier_ids = [t.id for t in self.sponsorship.tiers]
            if len(set(tier_ids)) != len(tier_ids):
                dupes = {i for i in tier_ids if tier_ids.count(i) > 1}
                raise ValueError(f"duplicate sponsor tier id(s): {sorted(dupes)}")

        # Phase 3 content: policies, synergies, personas, events.
        policy_ids = [p.id for p in self.policies]
        if len(set(policy_ids)) != len(policy_ids):
            dupes = {i for i in policy_ids if policy_ids.count(i) > 1}
            raise ValueError(f"duplicate policy id(s): {sorted(dupes)}")
        policy_set = set(policy_ids)
        for syn in self.synergies:
            if not syn.requires_tags and not syn.requires_policies:
                raise ValueError(f"synergy '{syn.id}' must require at least one tag or policy")
            unknown = set(syn.requires_policies) - policy_set
            if unknown:
                raise ValueError(f"synergy '{syn.id}' references unknown policy id(s): {sorted(unknown)}")
        persona_ids = [p.id for p in self.personas]
        if len(set(persona_ids)) != len(persona_ids):
            dupes = {i for i in persona_ids if persona_ids.count(i) > 1}
            raise ValueError(f"duplicate persona id(s): {sorted(dupes)}")
        known_actions = {"canvass", "leaflets", "social_post", "baby_kiss", "pub_visit",
                         "radio_phone_in", "rally", "press_stunt", "fundraise"}
        for persona in self.personas:
            unknown = set(persona.action_cp_multipliers) - known_actions
            if unknown:
                raise ValueError(f"persona '{persona.id}' boosts unknown action(s): {sorted(unknown)}")
        event_ids = [e.id for e in self.events.good + self.events.bad]
        if len(set(event_ids)) != len(event_ids):
            dupes = {i for i in event_ids if event_ids.count(i) > 1}
            raise ValueError(f"duplicate event id(s): {sorted(dupes)}")

        return self

    @property
    def all_parties(self) -> list[PartyCfg]:
        return self.major_parties + self.spoof_parties

    def party(self, party_id: str) -> PartyCfg:
        for p in self.all_parties:
            if p.id == party_id:
                return p
        raise KeyError(f"unknown party id: {party_id}")

    def region(self, region_id: str) -> RegionCfg:
        for r in self.regions:
            if r.id == region_id:
                return r
        raise KeyError(f"unknown region id: {region_id}")


class DifficultyPreset(_Forgiving):
    label: str
    description: str
    wins_required: int = Field(ge=1, le=10)
    starting_funds: int = Field(gt=0)
    ap_per_week: int = Field(ge=1, le=10)
    rival_aggression: float = Field(gt=0)
    good_event_bias: float = Field(ge=0, le=1)
    deposit_forgiveness: int = Field(ge=0, le=5)
    ge_turn: int = Field(ge=8, le=100)
    byelection_interval_turns: int = Field(ge=1, le=10)
    marketing_efficiency: float = Field(gt=0)
    scandal_magnitude: float = Field(gt=0)
    event_frequency: float = Field(default=0.35, ge=0, le=1)
    ge_defense: float = Field(default=1.0, ge=0.3, le=4)  # how hard rivals defend the GE
    split_counties: bool = Field(default=False)  # hard mode: fight the halves of every county


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def list_countries() -> list[dict[str, str]]:
    """Summaries of every valid country config (template file excluded)."""
    out = []
    for path in sorted(COUNTRIES_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        cfg = load_country(path.stem)  # raises if a mod author broke their JSON
        out.append(
            {
                "id": cfg.id,
                "name": cfg.name,
                "flag_emoji": cfg.flag_emoji,
                "game_title": cfg.game_title,
                "subtitle": cfg.subtitle,
            }
        )
    return out


def _expanded_country(base: CountryConfig) -> CountryConfig:
    """Resolve a country into its split-county form (hard mode): every county
    with `splits` becomes two half-counties; parties remap onto the halves."""
    parent_to_splits = {r.id: [s.id for s in r.splits] for r in base.regions}
    regions = []
    for r in base.regions:
        if not r.splits:
            regions.append(r)
            continue
        for sp in r.splits:
            regions.append(
                RegionCfg(
                    id=sp.id,
                    name=sp.name,
                    electorate=sp.electorate,
                    turnout_base=sp.turnout_base if sp.turnout_base is not None else r.turnout_base,
                    demographics=(
                        sp.demographics.model_copy(deep=True)
                        if sp.demographics is not None
                        else r.demographics.model_copy(deep=True)
                    ),
                    local_issues=list(sp.local_issues) if sp.local_issues is not None else list(r.local_issues),
                )
            )

    def remap_party(p: PartyCfg) -> PartyCfg:
        if p.regions is None:
            return p
        mapped: list[str] = []
        for rid in p.regions:
            mapped.extend(parent_to_splits.get(rid, [rid]))
        return p.model_copy(update={"regions": mapped})

    data = base.model_dump()
    data["regions"] = [r.model_dump() for r in regions]
    data["major_parties"] = [remap_party(p).model_dump() for p in base.major_parties]
    data["spoof_parties"] = [remap_party(p).model_dump() for p in base.spoof_parties]
    return CountryConfig.model_validate(data)


@lru_cache(maxsize=None)
def load_country(country_id: str, split_counties: bool = False) -> CountryConfig:
    path = COUNTRIES_DIR / f"{country_id}.json"
    if not path.is_file() or path.name.startswith("_"):
        raise FileNotFoundError(f"no country config for id '{country_id}'")
    base = CountryConfig.model_validate(_read_json(path))
    if split_counties:
        return _expanded_country(base)
    return base


@lru_cache(maxsize=None)
def load_difficulties() -> dict[str, DifficultyPreset]:
    raw = _read_json(DIFFICULTY_FILE)
    return {key: DifficultyPreset.model_validate(value) for key, value in raw.items()}
