"""Game API tests: full request/response flow over HTTP."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def new_game(**overrides):
    body = {
        "country_id": "uk",
        "difficulty": "easy",
        "name": "Flo Trolley",
        "party_name": "The Trolley Party",
        "slogan": "Return your trolleys",
        "seed": 99,
    }
    body.update(overrides)
    return client.post("/api/game/new", json=body)


def test_new_game_returns_state():
    res = new_game()
    assert res.status_code == 200
    body = res.json()
    assert body["game_id"]
    assert body["state"]["candidate"]["name"] == "Flo Trolley"
    assert body["state"]["funds"] == 2000
    assert body["state"]["country"]["deposit"] == 500


def test_new_game_unknown_country_404():
    assert new_game(country_id="atlantis").status_code == 404


def test_new_game_unknown_difficulty_400():
    assert new_game(difficulty="story").status_code == 400


def test_get_and_delete_game():
    game_id = new_game().json()["game_id"]
    assert client.get(f"/api/game/{game_id}").status_code == 200
    assert client.get("/api/game/nope").status_code == 404
    assert client.delete(f"/api/game/{game_id}").status_code == 200
    assert client.get(f"/api/game/{game_id}").status_code == 404


def test_action_flow():
    game_id = new_game().json()["game_id"]
    res = client.post(f"/api/game/{game_id}/action", json={"action_id": "canvass"})
    assert res.status_code == 200
    body = res.json()
    assert body["feedback"]
    assert body["state"]["ap"] == 3  # easy = 4 AP, canvass costs 1

    bad = client.post(f"/api/game/{game_id}/action", json={"action_id": "astral_project"})
    assert bad.status_code == 400


def test_action_with_params_sponsor_and_marketing():
    game_id = new_game().json()["game_id"]
    res = client.post(
        f"/api/game/{game_id}/action", json={"action_id": "sponsor", "params": {"tier_id": "pub_quiz"}}
    )
    assert res.status_code == 200
    assert res.json()["state"]["funds"] == 2300

    res = client.post(
        f"/api/game/{game_id}/action", json={"action_id": "marketing", "params": {"channel_id": "radio_spot"}}
    )
    assert res.status_code == 200
    assert res.json()["state"]["funds"] == 2300 - 250
    assert res.json()["state"]["ap"] == 4  # marketing is AP-free


def test_update_candidate_settings():
    game_id = new_game().json()["game_id"]
    res = client.patch(
        f"/api/game/{game_id}/candidate",
        json={"party_name": "The Trolley Party Reloaded", "color": "#00FFAA", "persona": "binfluencer", "slogan": "Trolleys 2.0"},
    )
    assert res.status_code == 200
    state = res.json()["state"]
    assert state["candidate"]["party_name"] == "The Trolley Party Reloaded"
    assert state["candidate"]["color"] == "#00FFAA"
    assert state["candidate"]["persona"] == "binfluencer"
    assert state["persona"]["id"] == "binfluencer"

    bad = client.patch(f"/api/game/{game_id}/candidate", json={"persona": "the_lobbiest"})
    assert bad.status_code == 400
    assert client.patch("/api/game/nope/candidate", json={"name": "X"}).status_code == 404


def test_end_week_flow_reaches_byelection():
    game_id = new_game().json()["game_id"]
    for _ in range(5):
        res = client.post(f"/api/game/{game_id}/end_week")
        assert res.status_code == 200
    state = client.get(f"/api/game/{game_id}").json()
    assert state["campaigns_fought"] >= 1 if "campaigns_fought" in state else True
    assert state["last_byresult"] is not None
    assert state["week"] >= 5


def test_end_week_on_unknown_game_404():
    assert client.post("/api/game/nope/end_week").status_code == 404
