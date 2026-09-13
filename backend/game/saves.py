"""Disk-backed save slots (Phase 6).

Each save is a JSON file under saves/ containing the full engine state plus
metadata for the title-screen "Continue campaign" list. Loading creates a fresh
in-memory game from the save; the save itself stays on disk until deleted.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.game.engine import GameEngine

SAVE_DIR = Path(__file__).resolve().parent.parent.parent / "saves"


def _ensure_dir() -> None:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)


def save_engine(engine: GameEngine) -> dict:
    """Write the engine to a new save slot; returns its metadata."""
    _ensure_dir()
    s = engine.state
    save_id = uuid.uuid4().hex[:12]
    payload = {
        "save_id": save_id,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "meta": {
            "week": s.week,
            "phase": s.phase.value,
            "name": s.candidate.name,
            "party_name": s.candidate.party_name,
            "emoji": s.candidate.emoji,
            "color": s.candidate.color,
            "difficulty": s.difficulty,
            "country_id": s.country_id,
            "wins": s.wins,
            "wins_required": engine.preset.wins_required,
            "momentum": round(s.momentum, 2),
            "funds": s.funds,
            "deposits_lost": s.deposits_lost,
            "game_over": s.game_over.over,
            "victory": s.game_over.victory,
        },
        "state": engine.to_json(),
    }
    path = SAVE_DIR / f"{save_id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic-ish write so a crash can't half-save
    return {"save_id": save_id, **payload["meta"], "saved_at": payload["saved_at"]}


def list_saves() -> list[dict]:
    """All valid saves, newest first. Corrupt files are skipped, not fatal."""
    if not SAVE_DIR.is_dir():
        return []
    out = []
    for path in SAVE_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            meta = payload["meta"]
            out.append({"save_id": payload["save_id"], **meta, "saved_at": payload["saved_at"]})
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    out.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return out


def load_save(save_id: str) -> GameEngine:
    """Rebuild a GameEngine from a save file (raises FileNotFoundError if unknown)."""
    path = SAVE_DIR / f"{save_id}.json"
    if not path.is_file() or "/" in save_id or save_id.startswith("."):
        raise FileNotFoundError(f"unknown save '{save_id}'")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return GameEngine.from_json(payload["state"])


def delete_save(save_id: str) -> None:
    path = SAVE_DIR / f"{save_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"unknown save '{save_id}'")
    path.unlink()
