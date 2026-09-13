"""Campaign action catalog.

Actions cost Action Points (weekly) and money, and generate campaign points (CP)
distributed across voter age buckets. CP is the raw material of election results.
Paid marketing and sponsor sign-ups are handled by the engine but exposed through
this catalog for the UI.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ActionDef(BaseModel):
    id: str
    name: str
    emoji: str
    desc: str
    ap: int = Field(ge=0, le=4)
    cost: int = Field(ge=0)
    cp: float = Field(default=0.0, ge=0)
    bias: dict[str, float] = Field(default_factory=dict)  # bucket -> weight (normalised)
    variance: float = Field(default=0.0, ge=0)  # CP randomness: roll ~ N(1, variance)
    needs_campaign: bool = True
    special: str = ""  # engine-handled: fundraise | sponsor | marketing | force_ge | social_post | baby_kiss | press_stunt


BUCKETS = ("youth", "middle", "pensioner")


def _bias(youth: float, middle: float, pensioner: float) -> dict[str, float]:
    total = youth + middle + pensioner
    return {"youth": youth / total, "middle": middle / total, "pensioner": pensioner / total}


CATALOG: list[ActionDef] = [
    ActionDef(
        id="canvass",
        name="Canvass the High Street",
        emoji="\U0001f9f8",
        desc="Press the flesh, dodge the awkward questions, collect a few converts.",
        ap=1, cost=0, cp=6, bias=_bias(0.3, 0.4, 0.3),
    ),
    ActionDef(
        id="leaflets",
        name="Deliver Leaflets",
        emoji="\U0001f4c4",
        desc="Straight into the recycling bin of democracy. Pensioners read every word.",
        ap=1, cost=40, cp=5, bias=_bias(0.2, 0.3, 0.5),
    ),
    ActionDef(
        id="social_post",
        name="Post on Social Media",
        emoji="\U0001f4f1",
        desc="High risk, high reward. Could go viral; could go 'who is this man'.",
        ap=1, cost=0, cp=5, bias=_bias(0.7, 0.25, 0.05), variance=0.8, special="social_post",
    ),
    ActionDef(
        id="baby_kiss",
        name="Kiss a Baby",
        emoji="\U0001f476",
        desc="Timeless. Roughly one baby in five screams directly into the camera.",
        ap=1, cost=0, cp=6, bias=_bias(0.1, 0.4, 0.5), special="baby_kiss",
    ),
    ActionDef(
        id="pub_visit",
        name="Buy a Round at the Pub",
        emoji="\U0001f37a",
        desc="Cheap votes and free advice. Everybody in the pub is an expert.",
        ap=1, cost=30, cp=5, bias=_bias(0.4, 0.5, 0.1),
    ),
    ActionDef(
        id="radio_phone_in",
        name="Local Radio Phone-in",
        emoji="\U0001f4fb",
        desc="Defend your policies against a caller named Terry about parking.",
        ap=1, cost=20, cp=5, bias=_bias(0.1, 0.3, 0.6),
    ),
    ActionDef(
        id="rally",
        name="Hold a Rally",
        emoji="\U0001f3a4",
        desc="Flags, foghorns, fainting. Expensive but it moves numbers.",
        ap=2, cost=150, cp=12, bias=_bias(0.34, 0.33, 0.33),
    ),
    ActionDef(
        id="press_stunt",
        name="Stage a Press Stunt",
        emoji="\U0001f4f8",
        desc="Giant prop, bigger risk. Front page or laughing stock — sometimes both.",
        ap=2, cost=60, cp=10, bias=_bias(0.4, 0.35, 0.25), variance=0.6, special="press_stunt",
    ),
    ActionDef(
        id="fundraise",
        name="Fundraising Drive",
        emoji="\U0001f4b0",
        desc="Rattle the tin: crowdfunder push, jumble sale, sponsored silence.",
        ap=1, cost=0, special="fundraise",
    ),
    ActionDef(
        id="sponsor",
        name="Sign a Sponsor",
        emoji="\U0001f91d",
        desc="Take investor money. Bigger war chest, bigger scandal risk. Costs money-time, not AP.",
        ap=0, cost=0, special="sponsor",
    ),
    ActionDef(
        id="marketing",
        name="Buy Marketing",
        emoji="\U0001f4e3",
        desc="Paid promotion: billboards, video ads, radio spots. Costs money, not AP.",
        ap=0, cost=0, special="marketing",
    ),
    ActionDef(
        id="force_ge",
        name="Force a General Election",
        emoji="\U0001f3b0",
        desc="You've built momentum — dare the country to settle it now.",
        ap=0, cost=0, needs_campaign=False, special="force_ge",
    ),
]

BY_ID = {a.id: a for a in CATALOG}


def get(action_id: str) -> ActionDef:
    return BY_ID[action_id]
