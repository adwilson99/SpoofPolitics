/* Local backend: the entire game runs in the browser. Sessions live in memory,
   saves in localStorage. Powers the itch.io build (and anywhere without a server). */
"use strict";

const LocalAPI = (() => {
  const engines = {}; // game_id -> GameEngine
  let current = null;
  const rawCfg = {}; // country_id -> raw config
  let presets = null;
  const SAVES_KEY = "ltw_saves";

  // Embedded configs (shipped as configs.js) work even on file://;
  // fetch() is the fallback for older builds.
  function shipped() {
    return globalThis.SHIPPED_CONFIGS || null;
  }

  async function fetchJson(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`missing game data: ${path} (${res.status})`);
    return res.json();
  }

  async function getPresets() {
    const s = shipped();
    if (s) return s.difficulties;
    if (!presets) presets = await fetchJson("static/config/difficulty.json");
    return presets;
  }

  async function getCountry(id, split) {
    const s = shipped();
    if (!rawCfg[id]) {
      rawCfg[id] = s && s.countries[id] ? s.countries[id] : await fetchJson(`static/config/countries/${id}.json`);
    }
    const cfg = structuredClone(rawCfg[id]);
    ENGINE.attachConfigHelpers(cfg);
    return split ? ENGINE.expandCountry(cfg) : cfg;
  }

  function rid() {
    return Math.random().toString(16).slice(2, 14);
  }

  function engineOrThrow(id) {
    const e = engines[id];
    if (!e) throw new Error(`unknown game '${id}'`);
    return e;
  }

  function readSaves() {
    try {
      return JSON.parse(localStorage.getItem(SAVES_KEY) || "[]");
    } catch (e) {
      return [];
    }
  }

  function writeSaves(list) {
    localStorage.setItem(SAVES_KEY, JSON.stringify(list));
  }

  return {
    async countries() {
      const s = shipped();
      if (s) {
        return Object.values(s.countries).map((raw) => ({
          id: raw.id,
          name: raw.name,
          flag_emoji: raw.flag_emoji,
          game_title: raw.game_title,
          subtitle: raw.subtitle || "",
        }));
      }
      const raw = await fetchJson("static/config/countries/uk.json");
      return [
        {
          id: raw.id,
          name: raw.name,
          flag_emoji: raw.flag_emoji,
          game_title: raw.game_title,
          subtitle: raw.subtitle || "",
        },
      ];
    },

    async country(id) {
      return getCountry(id, false);
    },

    async difficulties() {
      return getPresets();
    },

    async newGame(body) {
      const presets = await getPresets();
      const preset = presets[body.difficulty];
      if (!preset) throw new Error(`unknown difficulty '${body.difficulty}'`);
      const split = Boolean(preset.split_counties);
      const cfg = await getCountry(body.country_id, split);
      const candidate = {
        name: body.name,
        party_name: body.party_name,
        slogan: body.slogan || "",
        emoji: body.emoji,
        color: body.color,
        policies: body.policies || [],
        persona: body.persona || "",
      };
      ENGINE.CONTENT.personaOf(cfg, candidate.persona); // validates
      ENGINE.CONTENT.buildManifesto(cfg, candidate.policies); // validates
      const engine = new ENGINE.GameEngine(cfg, preset, body.difficulty, candidate, body.seed != null ? body.seed : null);
      const game_id = rid();
      engines[game_id] = engine;
      current = game_id;
      return { game_id, state: engine.snapshot() };
    },

    async action(gameId, actionId, params) {
      const e = engineOrThrow(gameId);
      const feedback = e.applyAction(actionId, params || {});
      return { game_id: gameId, feedback, state: e.snapshot() };
    },

    async endWeek(gameId) {
      const e = engineOrThrow(gameId);
      const events = e.endWeek();
      return { game_id: gameId, events, state: e.snapshot() };
    },

    async saveGame(gameId) {
      const e = engineOrThrow(gameId);
      const s = e.state;
      const save = {
        save_id: rid(),
        saved_at: new Date().toISOString(),
        meta: {
          week: s.week,
          phase: s.phase,
          name: s.candidate.name,
          party_name: s.candidate.party_name,
          emoji: s.candidate.emoji,
          color: s.candidate.color,
          difficulty: s.difficulty,
          country_id: s.country_id,
          wins: s.wins,
          wins_required: e.preset.wins_required,
          momentum: Math.round(s.momentum * 100) / 100,
          funds: s.funds,
          deposits_lost: s.deposits_lost,
          game_over: s.game_over.over,
          victory: s.game_over.victory,
        },
        state: e.toState(),
      };
      const list = readSaves().filter((x) => x.save_id !== save.save_id);
      list.unshift(save);
      writeSaves(list);
      return { save_id: save.save_id, ...save.meta, saved_at: save.saved_at };
    },

    async saves() {
      return readSaves().map(({ state, ...meta }) => meta);
    },

    async loadSave(saveId) {
      const save = readSaves().find((x) => x.save_id === saveId);
      if (!save) throw new Error(`unknown save '${saveId}'`);
      const presets = await getPresets();
      const preset = presets[save.state.difficulty];
      const cfg = await getCountry(save.state.country_id, Boolean(preset.split_counties));
      const engine = ENGINE.GameEngine.fromState(save.state, cfg, preset);
      const game_id = rid();
      engines[game_id] = engine;
      current = game_id;
      return { game_id, state: engine.snapshot() };
    },

    async deleteSave(saveId) {
      const list = readSaves();
      const idx = list.findIndex((x) => x.save_id === saveId);
      if (idx === -1) throw new Error(`unknown save '${saveId}'`);
      list.splice(idx, 1);
      writeSaves(list);
      return { status: "deleted" };
    },

    async abandon(gameId) {
      delete engines[gameId];
      if (current === gameId) current = null;
      return { status: "abandoned" };
    },

    async updateCandidate(gameId, fields) {
      const e = engineOrThrow(gameId);
      const c = e.state.candidate;
      if (fields.name != null) c.name = fields.name;
      if (fields.party_name != null) c.party_name = fields.party_name;
      if (fields.slogan != null) c.slogan = fields.slogan;
      if (fields.emoji != null) c.emoji = fields.emoji;
      if (fields.color != null) c.color = fields.color;
      if (fields.persona != null) {
        const persona = ENGINE.CONTENT.personaOf(e.country, fields.persona); // validates
        c.persona = fields.persona;
        e.persona = persona;
      }
      return {
        feedback: "The press office has updated your image. The rosette is ironed.",
        state: e.snapshot(),
      };
    },

    async health() {
      return { status: "ok", mode: "local" };
    },
  };
})();
