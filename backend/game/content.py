"""Phase 3 content: manifesto policies, synergies, personas, weekly events.

All of it is config-driven: a country file can define any number of policies
(hidden demographic appeal + tags), synergies (manifesto combos), personas
(candidate archetypes with small perks) and weekly events (news headline
templates with funds/cp/momentum effects). Empty config = feature quietly off,
so mods and older configs keep working.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from backend.config.loader import CountryConfig, EventCfg, EventsCfg, PersonaCfg, PolicyCfg, SynergyCfg

BUCKETS = ("youth", "middle", "pensioner")
MANIFESTO_MAX = 3
MANIFESTO_CP_PER_POLICY = 4.0  # each manifesto policy seeds this much campaign CP

EFFECT_LIMITS = {"funds": 5000, "cp": 20.0, "momentum": 3.0}


# ------------------------------------------------------------------ manifesto

def policy_by_id(country: CountryConfig, policy_id: str) -> PolicyCfg:
    for p in country.policies:
        if p.id == policy_id:
            return p
    raise ValueError(f"unknown policy '{policy_id}'")


def persona_of(country: CountryConfig, persona_id: str) -> PersonaCfg | None:
    if not persona_id:
        return None
    for p in country.personas:
        if p.id == persona_id:
            return p
    raise ValueError(f"unknown persona '{persona_id}'")


def _normalise(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return {b: 1.0 / len(BUCKETS) for b in BUCKETS}
    return {b: weights.get(b, 0.0) / total for b in BUCKETS}


@dataclass
class ManifestoReport:
    policies: list[PolicyCfg]
    synergies: list[SynergyCfg]
    cp_by_bucket: dict[str, float]

    @property
    def cp_total(self) -> float:
        return sum(self.cp_by_bucket.values())


def build_manifesto(country: CountryConfig, policy_ids: list[str]) -> ManifestoReport:
    """Validate a manifesto and compute its hidden CP bonus + active synergies."""
    if len(policy_ids) > MANIFESTO_MAX:
        raise ValueError(f"a manifesto can hold at most {MANIFESTO_MAX} policies")
    if len(set(policy_ids)) != len(policy_ids):
        raise ValueError("duplicate policies in manifesto")
    policies = [policy_by_id(country, pid) for pid in policy_ids]

    cp: dict[str, float] = {b: 0.0 for b in BUCKETS}
    for policy in policies:
        for bucket, share in _normalise(policy.appeal).items():
            cp[bucket] += MANIFESTO_CP_PER_POLICY * share

    synergies = active_synergies(country, policy_ids)
    for syn in synergies:
        for bucket, share in _normalise(syn.bonus_bias).items():
            cp[bucket] += syn.bonus_cp * share

    return ManifestoReport(policies=policies, synergies=synergies, cp_by_bucket=cp)


def active_synergies(country: CountryConfig, policy_ids: list[str]) -> list[SynergyCfg]:
    """A synergy fires when its required tags (with multiplicity) and policies are met."""
    policies = [policy_by_id(country, pid) for pid in policy_ids]
    tags: list[str] = []
    for p in policies:
        tags.extend(p.tags)
    out: list[SynergyCfg] = []
    for syn in country.synergies:
        needed = list(syn.requires_tags)
        for tag in set(needed):
            if tags.count(tag) < needed.count(tag):
                break
        else:
            if all(pid in policy_ids for pid in syn.requires_policies):
                out.append(syn)
    return out


# -------------------------------------------------------------------- personas

def action_cp_multiplier(persona: PersonaCfg | None, action_id: str) -> float:
    if persona is None:
        return 1.0
    return persona.action_cp_multipliers.get(action_id, 1.0)


def fundraise_multiplier(persona: PersonaCfg | None) -> float:
    return persona.fundraise_multiplier if persona else 1.0


def scandal_resistance(persona: PersonaCfg | None) -> float:
    return persona.scandal_resistance if persona else 0.0


def baby_cry_immunity(persona: PersonaCfg | None) -> bool:
    return bool(persona and persona.baby_cry_immunity)


def debate_bonus(persona: PersonaCfg | None) -> float:
    return persona.debate_bonus if persona else 0.0


# ---------------------------------------------------------------------- events

def pick_event(events: EventsCfg, rng: random.Random, good_bias: float) -> tuple[EventCfg, bool] | None:
    """Choose a good or bad event (bias falls back to the other pool if one is empty)."""
    want_good = rng.random() < good_bias
    pool, is_good = (events.good, True) if want_good else (events.bad, False)
    if not pool:
        pool, is_good = (events.bad, False) if want_good else (events.good, True)
    if not pool:
        return None
    total = sum(e.weight for e in pool)
    roll = rng.uniform(0, total)
    for event in pool:
        roll -= event.weight
        if roll <= 0:
            return event, is_good
    return pool[-1], is_good


def quiet_headline(country: CountryConfig, rng: random.Random) -> str:
    """A filler headline for weeks where nothing happened. '' if unconfigured."""
    templates = country.flavour.quiet_week_templates
    if not templates:
        return ""
    return rng.choice(templates)
