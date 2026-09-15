/* API layer with two backends behind one interface:
   - ServerAPI: the FastAPI backend (Render / local python run.py)
   - LocalAPI:  the whole game running client-side (itch.io build)
   Mode is auto-detected at boot: if /api/health answers with JSON we have a
   server; otherwise the game quietly runs entirely in the browser. */
"use strict";

const ServerAPI = {
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
    return ServerAPI._handle(await fetch(path, { headers: { Accept: "application/json" } }));
  },

  async _send(method, path, body) {
    return ServerAPI._handle(
      await fetch(path, {
        method,
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body || {}),
      })
    );
  },

  async del(path) {
    return ServerAPI._handle(await fetch(path, { method: "DELETE" }));
  },

  health() {
    return ServerAPI.get("/api/health");
  },
  countries() {
    return ServerAPI.get("/api/countries");
  },
  country(id) {
    return ServerAPI.get(`/api/countries/${encodeURIComponent(id)}`);
  },
  difficulties() {
    return ServerAPI.get("/api/difficulties");
  },

  newGame(body) {
    return ServerAPI.post("/api/game/new", body);
  },
  game(id) {
    return ServerAPI.get(`/api/game/${encodeURIComponent(id)}`);
  },
  action(id, actionId, params) {
    return ServerAPI.post(`/api/game/${encodeURIComponent(id)}/action`, {
      action_id: actionId,
      params: params || {},
    });
  },
  endWeek(id) {
    return ServerAPI.post(`/api/game/${encodeURIComponent(id)}/end_week`, {});
  },
  abandon(id) {
    return ServerAPI.del(`/api/game/${encodeURIComponent(id)}`);
  },

  updateCandidate(id, fields) {
    return ServerAPI.patch(`/api/game/${encodeURIComponent(id)}/candidate`, fields);
  },

  saveGame(id) {
    return ServerAPI.post(`/api/game/${encodeURIComponent(id)}/save`, {});
  },
  saves() {
    return ServerAPI.get("/api/saves");
  },
  loadSave(saveId) {
    return ServerAPI.post(`/api/saves/${encodeURIComponent(saveId)}/load`, {});
  },
  deleteSave(saveId) {
    return ServerAPI.del(`/api/saves/${encodeURIComponent(saveId)}`);
  },
};

const API = {
  backend: null, // resolved lazily: "server" or "local"
  _promise: null,

  async _impl() {
    if (API.backend) return API.backend;
    if (!API._promise) {
      API._promise = (async () => {
        try {
          const res = await fetch("/api/health", { headers: { Accept: "application/json" } });
          const ct = res.headers.get("content-type") || "";
          API.backend = res.ok && ct.includes("json") ? ServerAPI : LocalAPI;
        } catch (e) {
          API.backend = LocalAPI;
        }
        return API.backend;
      })();
    }
    return API._promise;
  },
};

for (const fn of [
  "health",
  "countries",
  "country",
  "difficulties",
  "newGame",
  "game",
  "action",
  "endWeek",
  "abandon",
  "updateCandidate",
  "saveGame",
  "saves",
  "loadSave",
  "deleteSave",
]) {
  API[fn] = function (...args) {
    return API._impl().then((backend) => backend[fn](...args));
  };
}
