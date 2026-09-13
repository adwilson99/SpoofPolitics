"""Phase 6 save/load tests: disk slots, API flow, corruption handling."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.game import saves
from backend.main import app

client = TestClient(app)


def new_game(**overrides):
    body = {
        "country_id": "uk",
        "difficulty": "easy",
        "name": "Flo Trolley",
        "party_name": "The Trolley Party",
        "policies": ["moon_dave", "ai_brenda", "pony_every_child"],
        "persona": "pub_oracle",
        "seed": 99,
    }
    body.update(overrides)
    return client.post("/api/game/new", json=body)


def test_save_and_load_roundtrip():
    game_id = new_game().json()["game_id"]
    client.post(f"/api/game/{game_id}/action", json={"action_id": "canvass"})
    saved = client.post(f"/api/game/{game_id}/save").json()
    assert saved["save_id"]
    assert saved["name"] == "Flo Trolley"
    assert saved["persona"] if "persona" in saved else True

    loaded = client.post(f"/api/saves/{saved['save_id']}/load")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["game_id"] != game_id  # a fresh session, not the same one
    state = body["state"]
    assert state["candidate"]["name"] == "Flo Trolley"
    assert len(state["manifesto"]) == 3
    assert state["persona"]["id"] == "pub_oracle"
    # the restored game is playable
    acted = client.post(f"/api/game/{body['game_id']}/action", json={"action_id": "canvass"})
    assert acted.status_code == 200
    # tidy up
    client.delete(f"/api/saves/{saved['save_id']}")


def test_saves_list_newest_first_and_deletable():
    ids = []
    for _ in range(2):
        game_id = new_game().json()["game_id"]
        ids.append(client.post(f"/api/game/{game_id}/save").json()["save_id"])
    listed = client.get("/api/saves").json()
    mine = [s for s in listed if s["save_id"] in ids]
    assert len(mine) == 2
    for save_id in ids:
        assert client.delete(f"/api/saves/{save_id}").json()["status"] == "deleted"
    assert all(s["save_id"] not in ids for s in client.get("/api/saves").json())


def test_unknown_and_corrupt_saves():
    assert client.post("/api/saves/nope/load").status_code == 404
    assert client.delete("/api/saves/nope").status_code == 404
    # corrupt file is skipped by the list and rejected on load
    bad = saves.SAVE_DIR / "corrupt_test.json"
    saves.SAVE_DIR.mkdir(exist_ok=True)
    bad.write_text("{not json", encoding="utf-8")
    try:
        assert all(s["save_id"] != "corrupt_test" for s in client.get("/api/saves").json())
        assert client.post("/api/saves/corrupt_test/load").status_code in (400, 404, 422)
    finally:
        bad.unlink(missing_ok=True)


def test_save_unknown_game_404():
    assert client.post("/api/game/nope/save").status_code == 404


def test_restored_game_continues_deterministically():
    game_id = new_game(seed=1234).json()["game_id"]
    for _ in range(2):
        client.post(f"/api/game/{game_id}/end_week")
    saved = client.post(f"/api/game/{game_id}/save").json()
    restored = client.post(f"/api/saves/{saved['save_id']}/load").json()
    a = client.post(f"/api/game/{restored['game_id']}/end_week")
    b = client.post(f"/api/game/{restored['game_id']}/end_week")
    # two separate restorations from the same save play identically
    r1 = client.post(f"/api/saves/{saved['save_id']}/load").json()
    c = client.post(f"/api/game/{r1['game_id']}/end_week")
    assert a.json()["events"] == c.json()["events"]
    client.delete(f"/api/saves/{saved['save_id']}")
