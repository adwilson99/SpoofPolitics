/* Thin fetch wrapper for the game API. All backend calls go through here. */
"use strict";

const API = {
  async _handle(res) {
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (body && body.detail) detail = body.detail;
      } catch (e) {
        /* non-JSON error body */
      }
      throw new Error(`API ${res.status}: ${detail}`);
    }
    return res.json();
  },

  async get(path) {
    return API._handle(await fetch(path, { headers: { Accept: "application/json" } }));
  },

  async post(path, body) {
    return API._send("POST", path, body);
  },

  async patch(path, body) {
    return API._send("PATCH", path, body);
  },

  async _send(method, path, body) {
    return API._handle(
      await fetch(path, {
        method,
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body || {}),
      })
    );
  },

  async del(path) {
    return API._handle(await fetch(path, { method: "DELETE" }));
  },

  health() {
    return API.get("/api/health");
  },
  countries() {
    return API.get("/api/countries");
  },
  country(id) {
    return API.get(`/api/countries/${encodeURIComponent(id)}`);
  },
  difficulties() {
    return API.get("/api/difficulties");
  },

  newGame(body) {
    return API.post("/api/game/new", body);
  },
  game(id) {
    return API.get(`/api/game/${encodeURIComponent(id)}`);
  },
  action(id, actionId, params) {
    return API.post(`/api/game/${encodeURIComponent(id)}/action`, {
      action_id: actionId,
      params: params || {},
    });
  },
  endWeek(id) {
    return API.post(`/api/game/${encodeURIComponent(id)}/end_week`, {});
  },
  abandon(id) {
    return API.del(`/api/game/${encodeURIComponent(id)}`);
  },

  updateCandidate(id, fields) {
    return API.patch(`/api/game/${encodeURIComponent(id)}/candidate`, fields);
  },

  saveGame(id) {
    return API.post(`/api/game/${encodeURIComponent(id)}/save`, {});
  },
  saves() {
    return API.get("/api/saves");
  },
  loadSave(saveId) {
    return API.post(`/api/saves/${encodeURIComponent(saveId)}/load`, {});
  },
  deleteSave(saveId) {
    return API.del(`/api/saves/${encodeURIComponent(saveId)}`);
  },
};
