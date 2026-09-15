/* Headless smoke test for the client-side engine port.
   Runs full games on every difficulty straight from the shipped configs.

   Usage: node tools/engine_smoke.mjs */
import fs from "node:fs";

const load = (p) => fs.readFileSync(p, "utf8");
const src = [load("frontend/js/rng.js"), load("frontend/js/engine.js")].join("\n");
(0, eval)(src); // defines globalThis.ENGINE

const E = globalThis.ENGINE;
const cfgRaw = JSON.parse(load("frontend/config/countries/uk.json"));
const presets = JSON.parse(load("frontend/config/difficulty.json"));

const ACTABLE = new Set([
  "canvass", "leaflets", "social_post", "baby_kiss", "pub_visit", "radio_phone_in", "rally", "press_stunt",
]);

function runGame(difficulty, seed) {
  const cfg = E.attachConfigHelpers(E.expandCountry(structuredClone(cfgRaw)));
  const preset = presets[difficulty];
  const candidate = {
    name: "Bot",
    party_name: "The Simulation Party",
    slogan: "01101",
    emoji: "🎩",
    color: "#D4A937",
    policies: ["pothole_cheese", "freddo_price_cap", "teatime_buses"],
    persona: "pub_oracle",
  };
  const engine = new E.GameEngine(cfg, preset, difficulty, candidate, seed);
  let guard = 0;
  while (!engine.state.game_over.over && guard < 140) {
    guard += 1;
    let acted = true;
    while (engine.state.ap > 0 && acted) {
      acted = false;
      const actable = engine.availableActions().filter((a) => a.affordable && ACTABLE.has(a.id));
      if (actable.length) {
        engine.applyAction(actable[0].id, {});
        acted = true;
      }
    }
    while (engine.state.funds < 400 && engine.state.ap > 0) engine.applyAction("fundraise");
    if (engine.state.ge_unlocked && engine.state.phase === "between") engine.applyAction("force_ge");
    engine.endWeek();
  }

  const s = engine.state;
  // structural sanity
  if (!s.game_over.over) throw new Error(`${difficulty}: game did not end`);
  if (s.ge_result && Object.keys(s.ge_result.seats).length === 0) throw new Error(`${difficulty}: GE produced no seats`);
  for (const [rid] of Object.entries(s.region_owners)) {
    if (!cfg.region(rid)) throw new Error(`${difficulty}: unknown owned region ${rid}`);
  }
  // save roundtrip: JSON-safe state revives into an identical snapshot
  const revived = E.GameEngine.fromState(JSON.parse(JSON.stringify(engine.toState())), cfg, preset);
  if (JSON.stringify(revived.snapshot()) !== JSON.stringify(engine.snapshot())) {
    throw new Error(`${difficulty}: save roundtrip changed the snapshot`);
  }

  return {
    weeks: s.week,
    wins: s.wins,
    victory: s.game_over.victory,
    hasGe: Boolean(s.ge_result),
    deposits: s.deposits_lost,
    owners: Object.keys(s.region_owners).length,
  };
}

let failures = 0;
for (const difficulty of Object.keys(presets)) {
  const results = [];
  for (let i = 0; i < 5; i++) {
    try {
      results.push(runGame(difficulty, 4200 + i * 17));
    } catch (err) {
      failures += 1;
      console.error(`  ${difficulty} seed ${4200 + i * 17}: FAILED — ${err.stack}`);
    }
  }
  const geCount = results.filter((r) => r.hasGe).length;
  const wins = results.filter((r) => r.victory).length;
  const avgOwners = (results.reduce((a, r) => a + r.owners, 0) / Math.max(results.length, 1)).toFixed(1);
  console.log(`${difficulty}: ${results.length} games | reached GE ${geCount} | victories ${wins} | avg counties owned ${avgOwners}`);
}
if (failures) {
  console.error(`${failures} game(s) failed`);
  process.exit(1);
}
console.log("engine port smoke OK");
