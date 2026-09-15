"""Frontend serving tests: all assets reachable, new Phase 5 features wired up."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_static_assets_served():
    for path in (
        "/static/css/main.css",
        "/static/js/api.js",
        "/static/js/rng.js",
        "/static/js/engine.js",
        "/static/js/local-api.js",
        "/static/js/map.js",
        "/static/map/united-kingdom.svg",
        "/static/config/difficulty.json",
        "/static/config/countries/uk.json",
    ):
        assert client.get(path).status_code == 200, path


def test_index_includes_map_and_staging_screens():
    html = client.get("/").text
    assert "map.js" in html
    assert 'id="map-body"' in html
    assert 'id="election-night"' in html
    assert 'id="debate-modal"' in html
    assert 'id="gameover-overlay"' in html


def test_campaign_screen_has_six_tabs():
    html = client.get("/").text
    for tab in ("campaign", "map", "polls", "warchest", "news", "settings"):
        assert f'data-tab="{tab}"' in html, f"missing tab button {tab}"
        assert f'id="tab-{tab}"' in html, f"missing tab page {tab}"
    assert 'id="apply-settings"' in html
    assert 'id="set-color"' in html


def test_pwa_manifest_and_service_worker():
    import json

    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    body = manifest.json()
    assert body["name"] == "Loony to Westminster"
    assert body["display"] == "standalone"
    for icon in body["icons"]:
        assert client.get(icon["src"]).status_code == 200, icon["src"]
    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "CACHE" in sw.text and "/api/" in sw.text  # caches shell, never game state
    html = client.get("/").text
    assert 'rel="manifest"' in html
    assert "serviceWorker" in client.get("/static/js/app.js").text


def test_newspaper_popup_and_article_markup():
    html = client.get("/").text
    assert 'id="turn-summary"' in html
    assert 'id="paper-news"' in html
    assert 'id="article-view"' in html
    assert 'id="article-body"' in html
    assert "showTurnSummary" in client.get("/static/js/app.js").text


def test_map_assets_and_county_mapping():
    """The real open-source SVG is served, and every game county maps onto it."""
    from backend.config import loader

    assert client.get("/static/map/united-kingdom.svg").status_code == 200
    js = client.get("/static/js/map.js").text
    # all 12 colourable NUTS1 regions from the SVG are referenced
    for nuts in (
        "GB-UKC", "GB-UKD", "GB-UKE", "GB-UKF", "GB-UKG", "GB-UKH",
        "GB-UKI", "GB-UKJ", "GB-UKK", "GB-UKL", "GB-UKM", "GB-UKN",
    ):
        assert nuts in js, f"map.js is missing NUTS1 region {nuts}"
    # every easy/medium county and every hard-mode split half maps onto the SVG
    for region in loader.load_country("uk").regions:
        assert f"{region.id}:" in js, f"map is missing county {region.id}"
    for region in loader.load_country("uk", split_counties=True).regions:
        assert f"{region.id}:" in js, f"map is missing split county {region.id}"
