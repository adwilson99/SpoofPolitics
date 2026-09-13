"""Gameplay API: create games, act, end weeks."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import loader
from backend.game import content, saves, store
from backend.game.models import Candidate

router = APIRouter(prefix="/api/game")
saves_router = APIRouter(prefix="/api")


class NewGameRequest(BaseModel):
    country_id: str
    difficulty: str = "medium"
    name: str = Field(min_length=1, max_length=60)
    party_name: str = Field(min_length=1, max_length=60)
    slogan: str = Field(default="", max_length=120)
    emoji: str = Field(default="\U0001f3a9", min_length=1)
    color: str = Field(default="#D4A937", pattern=r"^#[0-9a-fA-F]{6}$")
    policies: list[str] = Field(default_factory=list)
    persona: str = Field(default="", max_length=32)
    seed: Optional[int] = None


class ActionRequest(BaseModel):
    action_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class CandidateUpdateRequest(BaseModel):
    """Partial candidate edits from the Settings tab; omitted fields unchanged."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    party_name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    slogan: Optional[str] = Field(default=None, max_length=120)
    emoji: Optional[str] = Field(default=None, min_length=1)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    persona: Optional[str] = Field(default=None, max_length=32)


def _snapshot_or_404(game_id: str) -> dict[str, Any]:
    try:
        engine = store.get(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown game '{game_id}'") from None
    return engine.snapshot()


@router.post("/new")
def new_game(req: NewGameRequest) -> dict[str, Any]:
    try:
        country = loader.load_country(req.country_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"unknown country '{req.country_id}'") from None
    try:
        content.persona_of(country, req.persona)
        content.build_manifesto(country, req.policies)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    candidate = Candidate(
        name=req.name,
        party_name=req.party_name,
        slogan=req.slogan,
        emoji=req.emoji,
        color=req.color,
        policies=req.policies,
        persona=req.persona,
    )
    try:
        game_id = store.create(req.country_id, req.difficulty, candidate, seed=req.seed)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"unknown country '{req.country_id}'") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"game_id": game_id, "state": _snapshot_or_404(game_id)}


@router.get("/{game_id}")
def get_game(game_id: str) -> dict[str, Any]:
    return _snapshot_or_404(game_id)


@router.post("/{game_id}/action")
def do_action(game_id: str, req: ActionRequest) -> dict[str, Any]:
    try:
        engine = store.get(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown game '{game_id}'") from None
    try:
        feedback = engine.apply_action(req.action_id, req.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"game_id": game_id, "feedback": feedback, "state": engine.snapshot()}


@router.post("/{game_id}/end_week")
def end_week(game_id: str) -> dict[str, Any]:
    try:
        engine = store.get(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown game '{game_id}'") from None
    try:
        lines = engine.end_week()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"game_id": game_id, "events": lines, "state": engine.snapshot()}


@router.patch("/{game_id}/candidate")
def update_candidate(game_id: str, req: CandidateUpdateRequest) -> dict[str, Any]:
    try:
        engine = store.get(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown game '{game_id}'") from None
    c = engine.state.candidate
    try:
        if req.name is not None:
            c.name = req.name
        if req.party_name is not None:
            c.party_name = req.party_name
        if req.slogan is not None:
            c.slogan = req.slogan
        if req.emoji is not None:
            c.emoji = req.emoji
        if req.color is not None:
            c.color = req.color
        if req.persona is not None:
            content.persona_of(engine.country, req.persona)  # validates
            c.persona = req.persona
            engine.persona = content.persona_of(engine.country, req.persona)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "feedback": "The press office has updated your image. The rosette is ironed.",
        "state": engine.snapshot(),
    }


@router.delete("/{game_id}")
def abandon(game_id: str) -> dict[str, str]:
    try:
        store.get(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown game '{game_id}'") from None
    store.delete(game_id)
    return {"status": "abandoned"}


# ------------------------------------------------------------- saves (Phase 6)

@router.post("/{game_id}/save")
def save_game(game_id: str) -> dict[str, Any]:
    try:
        engine = store.get(game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown game '{game_id}'") from None
    return saves.save_engine(engine)


@saves_router.get("/saves")
def list_saves() -> list[dict[str, Any]]:
    return saves.list_saves()


@saves_router.post("/saves/{save_id}/load")
def load_save(save_id: str) -> dict[str, Any]:
    try:
        engine = saves.load_save(save_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"unknown save '{save_id}'") from None
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"corrupt save: {exc}") from None
    game_id = store.put(engine)
    return {"game_id": game_id, "state": engine.snapshot()}


@saves_router.delete("/saves/{save_id}")
def delete_save(save_id: str) -> dict[str, str]:
    try:
        saves.delete_save(save_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"unknown save '{save_id}'") from None
    return {"status": "deleted"}
