"""REST API routes: health, country configs, difficulty presets."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import loader

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "game": "Loony to Westminster"}


@router.get("/countries")
def countries() -> list[dict[str, str]]:
    return loader.list_countries()


@router.get("/countries/{country_id}")
def country_detail(country_id: str) -> dict:
    try:
        cfg = loader.load_country(country_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"unknown country '{country_id}'")
    except Exception as exc:  # invalid mod JSON -> readable message
        raise HTTPException(status_code=500, detail=f"invalid country config: {exc}")
    return cfg.model_dump()


@router.get("/difficulties")
def difficulties() -> dict[str, dict]:
    return {key: preset.model_dump() for key, preset in loader.load_difficulties().items()}
