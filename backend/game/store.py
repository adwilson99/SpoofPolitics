"""In-memory session store for running games (single-player, local server).

Games persist across play sessions via backend/game/saves.py (Phase 6); this
store holds the live session only.
"""
from __future__ import annotations

import uuid
from threading import Lock

from backend.game.engine import GameEngine
from backend.game.models import Candidate

_games: dict[str, GameEngine] = {}
_lock = Lock()


def create(country_id: str, difficulty: str, candidate: Candidate, seed: int | None = None) -> str:
    engine = GameEngine(country_id, difficulty, candidate, seed=seed)
    return put(engine)


def put(engine: GameEngine) -> str:
    """Register a pre-built engine (used by save loading); returns its game id."""
    game_id = uuid.uuid4().hex[:12]
    with _lock:
        _games[game_id] = engine
    return game_id


def get(game_id: str) -> GameEngine:
    with _lock:
        if game_id not in _games:
            raise KeyError(game_id)
        return _games[game_id]


def delete(game_id: str) -> None:
    with _lock:
        _games.pop(game_id, None)
