"""Engine state models for Loony to Westminster (pure data, no I/O)."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Phase(str, Enum):
    BETWEEN = "between"          # no active campaign; plan, fundraise, sign sponsors
    BY_CAMPAIGN = "by_campaign"  # fighting a by-election
    GE_CAMPAIGN = "ge_campaign"  # final weeks before the General Election
    GAME_OVER = "game_over"


class Candidate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    party_name: str = Field(min_length=1, max_length=60)
    slogan: str = Field(default="", max_length=120)
    emoji: str = Field(default="\U0001f3a9", min_length=1)
    color: str = Field(default="#D4A937", pattern=r"^#[0-9a-fA-F]{6}$")
    policies: list[str] = Field(default_factory=list)  # manifesto: up to 3 policy ids
    persona: str = Field(default="", max_length=32)  # persona id ("" = no persona)


class Sponsor(BaseModel):
    tier_id: str
    name: str
    emoji: str
    amount: int
    scandal_risk: float


class ActiveMarketing(BaseModel):
    channel_id: str
    name: str
    emoji: str
    weeks_left: int


class NewsItem(BaseModel):
    week: int
    headline: str
    tone: str = "neutral"  # good / bad / neutral


class CampaignState(BaseModel):
    kind: str  # "byelection" | "general"
    region_id: Optional[str] = None  # None for the national GE campaign
    region_name: str = ""
    weeks_total: int
    weeks_left: int
    player_cp: dict[str, float] = Field(default_factory=dict)  # bucket -> campaign points
    rival_cp: dict[str, float] = Field(default_factory=dict)   # party_id -> campaign points


class ByelectionResult(BaseModel):
    region_id: str
    region_name: str
    votes_cast: int
    turnout: float
    standings: list[tuple[str, str, int]]  # (party_id, display_name, votes) descending
    player_votes: int
    player_rank: int
    player_share: float
    deposit_lost: bool
    won: bool


class GEResult(BaseModel):
    seats: dict[str, int]                 # party_id -> regions won
    national_votes: dict[str, int]
    player_rank_seats: int
    player_rank_votes: int
    coalition_attempted: bool = False
    coalition_success: bool = False
    region_winners: dict[str, str] = Field(default_factory=dict)  # region_id -> party_id


class GameOver(BaseModel):
    over: bool = False
    victory: bool = False
    reason: str = ""


class EngineState(BaseModel):
    """Everything that is saved/loaded; the GameEngine class operates on this."""

    country_id: str
    difficulty: str
    rng_seed: int

    week: int = 1
    phase: Phase = Phase.BETWEEN
    candidate: Candidate
    funds: int
    ap: int
    ap_per_week: int
    momentum: float = 0.0
    wins: int = 0
    deposit_forgiveness: int = 0
    deposits_lost: int = 0
    scandals: int = 0

    ge_turn: int
    ge_unlocked: bool = False
    ge_forced: bool = False
    next_byelection_week: int = 2
    campaigns_fought: int = 0
    region_owners: dict[str, str] = Field(default_factory=dict)  # region_id -> party_id (persistent control)

    campaign: Optional[CampaignState] = None
    head_start_cp: dict[str, float] = Field(default_factory=dict)

    sponsors: list[Sponsor] = Field(default_factory=list)
    marketing: list[ActiveMarketing] = Field(default_factory=list)

    mood: dict[str, float] = Field(default_factory=dict)  # party_id -> national mood multiplier
    polls: dict[str, float] = Field(default_factory=dict)  # party_id -> estimated national share

    news: list[NewsItem] = Field(default_factory=list)
    last_byresult: Optional[ByelectionResult] = None
    ge_result: Optional[GEResult] = None
    game_over: GameOver = Field(default_factory=GameOver)
