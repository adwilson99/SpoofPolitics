/* Loony to Westminster — frontend app.
   Screens: title (country + difficulty) → setup (candidate creation) → campaign. */
"use strict";

const state = {
  countries: [],
  difficulties: {},
  selectedCountry: null,
  selectedDifficulty: null,
  countryConfigs: {}, // id -> full config (cached)

  // candidate creation
  emoji: "🎩",
  persona: "",
  policies: new Set(),

  // running game
  gameId: null,
  snapshot: null,
  weekLog: [],
  activeTab: "campaign",
  pendingPaper: false,
  mapToken: 0,
};

const el = (id) => document.getElementById(id);

const EMOJI_CHOICES = ["🎩", "🗳️", "🧹", "🍺", "📱", "👶", "🦓", "🧀", "⭐", "🚂"];

const PHASE_LABELS = {
  between: "Between campaigns",
  by_campaign: "By-election campaign",
  ge_campaign: "General Election campaign",
  game_over: "Game over",
};

const PLAYER_ID = "__player__";

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(message, ms = 3200) {
  const toast = el("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.add("hidden"), ms);
}

function showScreen(name) {
  for (const id of ["title-screen", "setup-screen", "campaign-screen"]) {
    el(id).classList.toggle("hidden", id !== `${name}-screen`);
  }
  window.scrollTo(0, 0);
}

const TABS = ["campaign", "map", "polls", "warchest", "news", "settings"];

function showTab(name) {
  state.activeTab = name;
  document.querySelectorAll(".tab-page").forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${name}`));
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  if (name === "settings" && state.snapshot) fillSettings(state.snapshot);
  window.scrollTo(0, 0);
}

function countryCfg() {
  return state.countryConfigs[state.selectedCountry] || null;
}

/* ---------- Disclaimer ---------- */

const DISMISS_KEY = "ltw_disclaimer_dismissed_v1";

function showDisclaimerBar(text) {
  el("disclaimer-bar-text").textContent = text;
  el("disclaimer-bar").classList.remove("hidden");
  el("disclaimer-inline").textContent = text;
  if (localStorage.getItem(DISMISS_KEY)) {
    el("disclaimer-bar").classList.add("hidden");
  }
}

/* ---------- Title screen ---------- */

function renderCountries() {
  const grid = el("country-grid");
  grid.innerHTML = "";
  for (const c of state.countries) {
    const card = document.createElement("button");
    card.className = "country-card";
    card.type = "button";
    card.innerHTML = `
      <div class="flag">${esc(c.flag_emoji)}</div>
      <div class="name">${esc(c.name)}</div>
      <div class="in-game-title">${esc(c.game_title)}</div>`;
    card.addEventListener("click", () => selectCountry(c.id, card));
    grid.appendChild(card);
  }
}

async function selectCountry(id, cardEl) {
  state.selectedCountry = id;
  document
    .querySelectorAll(".country-card")
    .forEach((n) => n.classList.toggle("selected", n === cardEl));

  try {
    if (!state.countryConfigs[id]) {
      state.countryConfigs[id] = await API.country(id);
    }
    const cfg = state.countryConfigs[id];
    el("game-title").textContent = cfg.game_title;
    el("game-subtitle").textContent = cfg.subtitle || "";
    el("title-flag").textContent = cfg.flag_emoji;
    document.title = cfg.game_title;
  } catch (err) {
    showToast(`Could not load country: ${err.message}`);
  }
  updateStartButton();
}

function renderDifficulties() {
  const grid = el("difficulty-grid");
  grid.innerHTML = "";
  for (const [key, preset] of Object.entries(state.difficulties)) {
    const card = document.createElement("button");
    card.className = "difficulty-card";
    card.type = "button";
    card.innerHTML = `
      <div class="label">${esc(preset.label)}</div>
      <div class="desc">${esc(preset.description)}</div>
      <div class="facts">
        By-election wins needed: ${preset.wins_required} ·
        Starting funds: ${preset.starting_funds}
      </div>`;
    card.addEventListener("click", () => {
      state.selectedDifficulty = key;
      document
        .querySelectorAll(".difficulty-card")
        .forEach((n) => n.classList.toggle("selected", n === card));
      updateStartButton();
    });
    grid.appendChild(card);
  }
}

function updateStartButton() {
  const ready = state.selectedCountry && state.selectedDifficulty;
  el("start-button").disabled = !ready;
  el("setup-hint").textContent = ready
    ? "Ready! Click to create your candidate."
    : "Select a country and a difficulty to begin.";
}

/* ---------- Candidate creation ---------- */

function enterSetup() {
  const cfg = countryCfg();
  if (!cfg) return;
  state.emoji = "🎩";
  state.persona = "";
  state.policies = new Set();
  el("cand-name").value = "";
  el("cand-party").value = "";
  el("cand-slogan").value = "";
  el("cand-color").value = "#D4A937";
  el("setup-kicker").textContent = `${cfg.flag_emoji} ${cfg.name} · ${state.difficulties[state.selectedDifficulty].label}`;
  renderEmojiRow();
  renderPersonaGrid();
  renderPolicyGrid();
  updateLaunchButton();
  showScreen("setup");
}

function renderEmojiRow() {
  renderEmojiRowInto("emoji-row", () => renderEmojiRow());
}

function renderEmojiRowInto(containerId, rerender) {
  const row = el(containerId);
  row.innerHTML = "";
  for (const e of EMOJI_CHOICES) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "emoji-choice" + (state.emoji === e ? " selected" : "");
    b.textContent = e;
    b.addEventListener("click", () => {
      state.emoji = e;
      rerender();
    });
    row.appendChild(b);
  }
}

function renderPersonaGrid() {
  renderPersonaGridInto("persona-grid", () => renderPersonaGrid());
}

function renderPersonaGridInto(containerId, rerender) {
  const cfg = countryCfg();
  const grid = el(containerId);
  if (!grid || !cfg) return;
  grid.innerHTML = "";

  const none = document.createElement("button");
  none.type = "button";
  none.className = "pick-card persona" + (state.persona === "" ? " selected" : "");
  none.innerHTML = `<div class="pick-head"><span class="pick-emoji">🚫</span><span class="pick-name">No persona</span></div>
    <div class="pick-blurb">Just you, a rosette, and an unreasonable amount of hope.</div>`;
  none.addEventListener("click", () => {
    state.persona = "";
    rerender();
  });
  grid.appendChild(none);

  for (const p of cfg.personas || []) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "pick-card persona" + (state.persona === p.id ? " selected" : "");
    card.innerHTML = `
      <div class="pick-head"><span class="pick-emoji">${esc(p.emoji)}</span><span class="pick-name">${esc(p.name)}</span></div>
      <div class="pick-blurb">${esc(p.blurb)}</div>`;
    card.addEventListener("click", () => {
      state.persona = state.persona === p.id ? "" : p.id;
      rerender();
    });
    grid.appendChild(card);
  }
}

function renderPolicyGrid() {
  const cfg = countryCfg();
  const grid = el("policy-grid");
  grid.innerHTML = "";
  for (const p of cfg.policies || []) {
    const picked = state.policies.has(p.id);
    const full = state.policies.size >= 3 && !picked;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "pick-card policy" + (picked ? " selected" : "") + (full ? " disabled" : "");
    const tags = (p.tags || []).map((t) => `<span class="tag-chip">${esc(t.replace(/_/g, " "))}</span>`).join("");
    card.innerHTML = `
      <div class="pick-head"><span class="pick-emoji">${esc(p.emoji)}</span><span class="pick-name">${esc(p.name)}</span></div>
      <div class="pick-blurb">${esc(p.blurb)}</div>
      <div class="tag-row">${tags}</div>`;
    card.addEventListener("click", () => {
      if (picked) state.policies.delete(p.id);
      else if (state.policies.size < 3) state.policies.add(p.id);
      renderPolicyGrid();
      updateLaunchButton();
    });
    grid.appendChild(card);
  }
  el("policy-hint").textContent = `${state.policies.size} of 3 policies selected.`;
}

function updateLaunchButton() {
  const name = el("cand-name").value.trim();
  const party = el("cand-party").value.trim();
  const policiesOk = state.policies.size === 3;
  let hint = "";
  if (!name || !party) hint = "Give us a name and a party name.";
  else if (!policiesOk) hint = `Pick exactly 3 policies (${state.policies.size}/3 selected).`;
  el("launch-button").disabled = !(name && party && policiesOk);
  el("launch-hint").textContent = hint || "Ready to embarrass yourself in front of the nation.";
}

async function launchGame() {
  const body = {
    country_id: state.selectedCountry,
    difficulty: state.selectedDifficulty,
    name: el("cand-name").value.trim(),
    party_name: el("cand-party").value.trim(),
    slogan: el("cand-slogan").value.trim(),
    emoji: state.emoji,
    color: el("cand-color").value,
    policies: [...state.policies],
    persona: state.persona,
  };
  try {
    const res = await API.newGame(body);
    state.gameId = res.game_id;
    state.snapshot = res.state;
    state.weekLog = [];
    showScreen("campaign");
    showTab("campaign");
    renderCampaign();
  } catch (err) {
    showToast(`Could not start the campaign: ${err.message}`, 5000);
  }
}

/* ---------- Campaign screen ---------- */

function partyMap() {
  const cfg = countryCfg();
  const map = {};
  if (cfg) {
    for (const p of cfg.major_parties.concat(cfg.spoof_parties)) map[p.id] = p;
  }
  return map;
}

function apDots(ap, perWeek) {
  const full = Math.max(0, Math.min(ap, perWeek));
  return `<span class="ap-dots">${"●".repeat(full)}${"○".repeat(Math.max(0, perWeek - full))}</span>`;
}

function renderCampaign(opts = {}) {
  const s = state.snapshot;
  if (!s) return;
  renderHud(s);
  renderMapPanel(s);
  renderStatus(s);
  renderActions(s);
  renderManifesto(s);
  renderPolls(s);
  renderWarchest(s);
  renderNews(s);
  renderResult(s);
  renderWeekLog();

  el("end-week-button").disabled = s.game_over.over;

  renderGameOver(s, opts);
}

function renderGameOver(s, opts) {
  const overlay = el("gameover-overlay");
  const confetti = el("confetti");
  if (s.game_over.over && !opts.deferGameOver) {
    el("go-emoji").textContent = s.game_over.victory ? "🎉" : "🫥";
    el("go-title").textContent = s.game_over.victory
      ? `You are the new ${s.country.leader_title}!`
      : "The nation has spoken";
    el("go-reason").textContent = s.game_over.reason;
    el("go-stats").innerHTML = `
      <div>Weeks campaigned: <b>${s.week}</b></div>
      <div>By-election wins: <b>${s.wins} / ${s.wins_required}</b></div>
      <div>Momentum: <b>★ ${s.momentum.toFixed(1)}</b></div>
      <div>Deposits lost: <b>${s.deposits_lost}</b> · Scandals survived: <b>${s.scandals}</b></div>`;
    const geo = s.ge_result;
    const finale = geo
      ? `<div>The ${esc(s.country.leader_title)} race: <b>#${geo.player_rank_seats}</b> by seats · <b>#${geo.player_rank_votes}</b> by votes${geo.coalition_success ? " · coalition negotiated 🤝" : ""}</div>`
      : "<div>Career ended before the big one. The door was never locked.</div>";
    el("go-recap").innerHTML = `
      <div>Campaign length: <b>${s.week} weeks</b> · Mode: <b>${esc(s.difficulty)}</b></div>
      ${finale}`;
    if (s.game_over.victory) {
      confetti.classList.remove("hidden");
      launchConfetti();
    } else {
      confetti.classList.add("hidden");
      confetti.innerHTML = "";
    }
    overlay.classList.remove("hidden");
  } else {
    confetti.classList.add("hidden");
    confetti.innerHTML = "";
    overlay.classList.add("hidden");
  }
}

function launchConfetti() {
  const box = el("confetti");
  box.innerHTML = "";
  const pieces = ["🎉", "🎊", "⭐", "🗳️", "🎩", "🥳"];
  for (let i = 0; i < 50; i++) {
    const p = document.createElement("span");
    p.className = "confetti-piece";
    p.textContent = pieces[i % pieces.length];
    p.style.left = (Math.random() * 100).toFixed(1) + "%";
    p.style.animationDelay = (Math.random() * 2.5).toFixed(2) + "s";
    p.style.animationDuration = (2.5 + Math.random() * 2.5).toFixed(2) + "s";
    p.style.fontSize = (14 + Math.random() * 18).toFixed(0) + "px";
    box.appendChild(p);
  }
}

const PHASE_ICONS = {
  between: "📋",
  by_campaign: "🗳️",
  ge_campaign: "📺",
  game_over: "🏁",
};

function renderHud(s) {
  const cur = s.country.currency_symbol;
  const phaseIcon = PHASE_ICONS[s.phase] || "🏛️";
  const phaseName = PHASE_LABELS[s.phase] || s.phase;
  el("hud").innerHTML = `
    <div class="hud-chip" title="Week ${s.week} of the campaign">📅 <b>${s.week}</b></div>
    <div class="hud-chip" title="${esc(phaseName)}">${phaseIcon}</div>
    <div class="hud-chip" title="War chest: ${cur}${s.funds.toLocaleString()}">💰 <b>${s.funds.toLocaleString()}</b></div>
    <div class="hud-chip" title="Action points: ${s.ap} of ${s.ap_per_week} left this week">${apDots(s.ap, s.ap_per_week)}</div>
    <div class="hud-chip" title="Momentum: ${s.momentum.toFixed(1)} stars">★ <b>${s.momentum.toFixed(1)}</b></div>
    <div class="hud-chip" title="By-election wins: ${s.wins} of ${s.wins_required} needed">🏆 <b>${s.wins}/${s.wins_required}</b></div>
    <div class="hud-chip dim" title="Deposits lost: ${s.deposits_lost} · Scandals: ${s.scandals} · General Election by week ${s.ge_turn}">💔${s.deposits_lost} ⚠️${s.scandals} ⏳${s.ge_turn}</div>`;
}

function renderMapPanel(s) {
  const parties = partyMap();
  parties[PLAYER_ID] = { short: s.candidate.party_name || "You", color: s.candidate.color };
  const owners = s.region_owners || {};

  // Control summary (per county).
  const counts = {};
  for (const pid of Object.values(owners)) counts[pid] = (counts[pid] || 0) + 1;
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const total = Object.keys(owners).length;
  el("map-legend").innerHTML = entries.length
    ? `Control (${total} county${total === 1 ? "" : "ies"}): ` +
      entries
        .map(([pid, n]) => {
          const p = parties[pid];
          const col = pid === PLAYER_ID ? s.candidate.color : (p ? p.color : "#777");
          const nm = pid === PLAYER_ID ? "You" : (p ? p.short : pid);
          return `<span class="legend-item"><span class="dot" style="background:${esc(col)}"></span>${esc(nm)} ×${n}</span>`;
        })
        .join("")
    : '<span class="dim">No counties controlled yet — virgin territory.</span>';

  const body = el("map-body");
  const token = (state.mapToken = (state.mapToken || 0) + 1);
  const paint = () => {
    if (token !== state.mapToken) return; // a newer render superseded this one
    // Counties aggregate onto the real map's 12 NUTS1 regions: dominant owner paints.
    const tally = {};
    for (const [county, pid] of Object.entries(owners)) {
      const nuts = UKMAP.nutsFor(county);
      if (!nuts) continue;
      tally[nuts] = tally[nuts] || {};
      tally[nuts][pid] = (tally[nuts][pid] || 0) + 1;
    }
    const colors = {}, titles = {};
    for (const { id, name } of UKMAP.NUTS1) {
      const parts = Object.entries(tally[id] || {}).sort((a, b) => b[1] - a[1]);
      if (parts.length) {
        const dom = parts[0][0];
        const p = parties[dom];
        colors[id] = dom === PLAYER_ID ? s.candidate.color : (p ? p.color : "#777");
        titles[id] =
          `${name} — ` +
          parts
            .map(([pid, n]) => `${pid === PLAYER_ID ? "you" : (parties[pid] ? parties[pid].short : pid)} ${n}`)
            .join(", ");
      } else {
        titles[id] = `${name} — up for grabs`;
      }
    }
    const highlight = s.campaign && s.campaign.region_id ? UKMAP.nutsFor(s.campaign.region_id) : null;
    UKMAP.apply(body, colors, highlight, titles);
    el("map-hint").textContent = s.campaign
      ? `Gold outline: you're fighting ${s.campaign.region_name}. Won counties stay coloured until another party takes them.`
      : "Won counties stay coloured until another party takes them.";
  };
  if (body.querySelector("svg")) {
    paint();
  } else {
    body.innerHTML = '<p class="hint">Unfolding the map…</p>';
    UKMAP.mount(body)
      .then(paint)
      .catch((err) => {
        body.innerHTML = `<p class="hint">Map could not load: ${esc(err.message)}</p>`;
      });
  }
}

function renderStatus(s) {
  const box = el("campaign-status");
  const cur = s.country.currency_symbol;
  let body = "";
  if (s.campaign) {
    const kindLabel =
      s.campaign.kind === "general" ? "General Election campaign" : "By-election campaign";
    const weeksLeft = s.campaign.weeks_left;
    const when =
      weeksLeft <= 1 ? "🗳️ Polling day is THIS WEEK!" : `🗳️ Polling day in ${weeksLeft} weeks`;
    const cp = Object.values(s.campaign.player_cp).reduce((a, b) => a + b, 0);
    body = `
      <div class="status-line big">${esc(s.campaign.region_name)}</div>
      <div class="status-line">${kindLabel} · ${when}</div>
      <div class="status-line dim">Campaign energy: ${cp.toFixed(1)} CP · Rival energy: ${Object.values(s.campaign.rival_cp).reduce((a, b) => a + b, 0).toFixed(1)}</div>`;
  } else if (s.phase === "between") {
    body = `
      <div class="status-line big">No election right now — a rare luxury.</div>
      <div class="status-line">Fundraise, sign sponsors, book marketing (it banks for next time), or simply panic productively.</div>`;
  }
  const forceBtn =
    s.ge_unlocked && s.phase === "between" && !s.game_over.over
      ? `<button id="force-ge-button" class="btn-force">🎲 You have the momentum — FORCE a General Election</button>`
      : "";
  box.innerHTML = `<h3>The campaign</h3>${body}${forceBtn}`;
  const fb = el("force-ge-button");
  if (fb) fb.addEventListener("click", () => doAction("force_ge"));
}

function renderActions(s) {
  const grid = el("actions-grid");
  grid.innerHTML = "";
  const cur = s.country.currency_symbol;
  for (const a of s.actions) {
    if (a.id === "sponsor" || a.id === "marketing" || a.id === "force_ge") continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "action-btn";
    btn.disabled = !a.affordable;
    if (!a.affordable) btn.title = a.reason_unavailable;
    const cost = a.cost > 0 ? ` · ${cur}${a.cost}` : "";
    btn.innerHTML = `
      <div class="action-head"><span class="action-emoji">${esc(a.emoji)}</span><span class="action-name">${esc(a.name)}</span></div>
      <div class="action-meta">${a.ap} AP${cost}</div>
      <div class="action-desc">${esc(a.desc)}</div>`;
    btn.addEventListener("click", () => doAction(a.id));
    grid.appendChild(btn);
  }
}

function renderManifesto(s) {
  const box = el("manifesto-panel");
  const persona = s.persona
    ? `<span class="mani-persona">${esc(s.persona.emoji)} ${esc(s.persona.name)}</span>`
    : `<span class="mani-persona dim">no persona</span>`;
  const policies = s.manifesto
    .map((p) => `<span class="mani-policy" title="${esc(p.blurb)}">${esc(p.emoji)} ${esc(p.name)}</span>`)
    .join("");
  const syn = s.synergies
    .map((x) => `<span class="syn-badge" title="${esc(x.blurb)}">${esc(x.emoji)} ${esc(x.name)}</span>`)
    .join("");
  box.innerHTML = `
    <h3>Manifesto</h3>
    <div class="mani-row">${persona}</div>
    <div class="mani-row">${policies || '<span class="dim">no policies</span>'}</div>
    <div class="mani-row">${syn ? syn : ""}<span class="dim">banked appeal: ${s.manifesto_cp.toFixed(1)} CP per campaign</span></div>`;
}

function renderPolls(s) {
  const cfg = countryCfg();
  const parties = {};
  if (cfg) {
    for (const p of cfg.major_parties.concat(cfg.spoof_parties)) parties[p.id] = p;
  }
  parties[PLAYER_ID] = {
    short: s.candidate.party_name || "You",
    color: s.candidate.color,
  };
  const entries = Object.entries(s.polls)
    .map(([id, share]) => ({ id, share, party: parties[id] || { short: id, color: "#888" } }))
    .sort((a, b) => b.share - a.share);
  const rows = entries.slice(0, 9);
  const max = rows.length ? rows[0].share : 1;
  const stack = entries
    .map(
      (r) =>
        `<span class="vote-seg${r.id === PLAYER_ID ? " you" : ""}" style="width:${(r.share * 100).toFixed(2)}%;background:${esc(r.party.color)}" title="${esc(r.party.short)}: ${(r.share * 100).toFixed(1)}%"></span>`
    )
    .join("");
  el("polls-panel").innerHTML = `
    <h3>Poll of polls <span class="dim small">(cosmetic)</span></h3>
    <div class="votes-bar polls-stack">${stack}</div>
    ${rows
      .map(
        (r) => `
      <div class="poll-row${r.id === PLAYER_ID ? " you" : ""}">
        <div class="poll-label">${esc(r.party.short)}</div>
        <div class="poll-bar-track"><div class="poll-bar" style="width:${((r.share / max) * 100).toFixed(1)}%;background:${esc(r.party.color)}"></div></div>
        <div class="poll-pct">${(r.share * 100).toFixed(1)}%</div>
      </div>`
      )
      .join("")}`;
}

function renderWarchest(s) {
  const box = el("warchest-panel");
  const cur = s.country.currency_symbol;
  const signed = new Set(s.sponsors.map((sp) => sp.tier_id));

  const signedChips = s.sponsors
    .map((sp) => `<span class="chip" title="Scandal risk ${(sp.scandal_risk * 100).toFixed(0)}%">${esc(sp.emoji)} ${esc(sp.name)}</span>`)
    .join("");
  const tierButtons = (s.sponsor_tiers || [])
    .filter((t) => !signed.has(t.id))
    .map(
      (t) => `
      <button class="buy-btn" data-tier="${esc(t.id)}" ${s.funds < 0 ? "disabled" : ""}>
        <b>${esc(t.emoji)} ${esc(t.name)}</b> +${cur}${t.amount.toLocaleString()}
        <span class="risk">risk ${(t.scandal_risk * 100).toFixed(0)}%</span>
        <span class="buy-blurb">${esc(t.blurb)}</span>
      </button>`
    )
    .join("");

  const activeMarketing = s.marketing
    .map((m) => `<span class="chip">${esc(m.emoji)} ${esc(m.name)} <span class="dim">${m.weeks_left}w</span></span>`)
    .join("");
  const channelButtons = (s.marketing_channels || [])
    .map(
      (c) => `
      <button class="buy-btn" data-channel="${esc(c.id)}" ${s.funds < c.cost ? "disabled" : ""}>
        <b>${esc(c.emoji)} ${esc(c.name)}</b> −${cur}${c.cost} · reach ${c.reach} · ${c.weeks}w
        <span class="buy-blurb">${esc(c.blurb)}</span>
      </button>`
    )
    .join("");

  box.innerHTML = `
    <h3>War chest</h3>
    <div class="warchest-sub">Sponsors on the payroll</div>
    <div class="chip-row">${signedChips || '<span class="dim">none (clean hands, empty pockets)</span>'}</div>
    ${tierButtons ? `<div class="warchest-sub">Sign a sponsor</div><div class="buy-list">${tierButtons}</div>` : ""}
    <div class="warchest-sub">Paid promotion</div>
    <div class="chip-row">${activeMarketing || ""}</div>
    <div class="buy-list">${channelButtons}</div>`;

  for (const b of box.querySelectorAll("[data-tier]")) {
    b.addEventListener("click", () => doAction("sponsor", { tier_id: b.dataset.tier }));
  }
  for (const b of box.querySelectorAll("[data-channel]")) {
    b.addEventListener("click", () => doAction("marketing", { channel_id: b.dataset.channel }));
  }
}

function renderNews(s) {
  el("news-panel").innerHTML = `
    <h3>News</h3>
    <div class="news-list">
      ${s.news
        .map(
          (n, i) => `
        <button type="button" class="news-item clickable tone-${esc(n.tone)}" data-news-index="${i}">
          <span class="news-week">W${n.week}</span> ${esc(n.headline)}
          <span class="readmore">read the article →</span>
        </button>`
        )
        .join("")}
    </div>`;
  for (const btn of el("news-panel").querySelectorAll("[data-news-index]")) {
    btn.addEventListener("click", () => {
      openArticle(s.news[Number(btn.dataset.newsIndex)], s);
    });
  }
}

function renderResult(s) {
  const panel = el("result-panel");
  const r = s.last_byresult;
  if (!r) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  const rows = r.standings
    .map(
      ([pid, name, votes], i) => `
      <tr class="${pid === PLAYER_ID ? "row-player" : ""}${i === 0 ? " row-winner" : ""}">
        <td>${i + 1}</td><td>${esc(name)}</td><td class="num">${votes.toLocaleString()}</td>
      </tr>`
    )
    .join("");
  panel.innerHTML = `
    <h3>Last result — ${esc(r.region_name)}</h3>
    <div class="result-banner ${r.won ? "good" : r.deposit_lost ? "bad" : ""}">
      ${r.won ? "🏆 VICTORY" : r.deposit_lost ? "💔 Deposit lost" : `#${r.player_rank} place — deposit saved`}
    </div>
    <table class="standings">
      <thead><tr><th>#</th><th>Candidate</th><th>Votes</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="status-line dim">Turnout ${(r.turnout * 100).toFixed(1)}% · your share ${(r.player_share * 100).toFixed(1)}%</div>`;
}

function renderWeekLog() {
  const log = el("week-log");
  const lines = state.weekLog.slice(0, 6);
  log.innerHTML = lines.map((l) => `<div class="log-line">${esc(l)}</div>`).join("");
}

/* ---------- Campaign actions ---------- */

async function doAction(actionId, params) {
  try {
    const res = await API.action(state.gameId, actionId, params);
    state.snapshot = res.state;
    if (res.feedback) showToast(res.feedback, 3600);
    renderCampaign();
  } catch (err) {
    showToast(err.message, 4200);
  }
}

async function endWeek() {
  try {
    const res = await API.endWeek(state.gameId);
    state.snapshot = res.state;
    state.weekLog = [...(res.events || []), ...state.weekLog];
    const s = state.snapshot;
    const geNight = !!(s.ge_result && s.game_over.over);
    renderCampaign({ deferGameOver: geNight || s.game_over.over });
    if (geNight) {
      runElectionNight(s);
      return;
    }
    if (s.game_over.over) {
      renderCampaign(); // bankruptcy etc: straight to the final edition
      return;
    }
    const debate = extractDebateEvents(res.events || []);
    if (debate.length) {
      state.pendingPaper = true; // the paper goes to press after the debate
      showDebateModal(debate);
    } else {
      showTurnSummary(s);
    }
  } catch (err) {
    showToast(err.message, 4200);
  }
}

/* ---------- The Weekly Dispatch: turn summary + articles ---------- */

function showTurnSummary(s) {
  state.pendingPaper = false;
  const week = s.week - 1; // the week that just ended
  const cfg = countryCfg();
  const papers = cfg ? cfg.flavour.newspapers : ["The Daily Blab"];
  el("paper-name").textContent = papers[week % papers.length].toUpperCase();
  el("paper-week").textContent = `Week ${week} edition · ${s.country.name}`;
  el("paper-summary").innerHTML = `
    <span class="sum-chip">Treasury: <b>${s.country.currency_symbol}${s.funds.toLocaleString()}</b></span>
    <span class="sum-chip">Momentum: <b>★ ${s.momentum.toFixed(1)}</b></span>
    <span class="sum-chip">Wins: <b>${s.wins}/${s.wins_required}</b></span>
    <span class="sum-chip">Deposits lost: <b>${s.deposits_lost}</b></span>
    <span class="sum-chip">${esc(PHASE_LABELS[s.phase] || s.phase)}</span>`;

  const items = s.news.filter((n) => n.week === week).slice().reverse(); // chronological
  const list = el("paper-news");
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML =
      '<div class="news-item tone-neutral">A deafeningly quiet week. The presses yawned and went to the pub.</div>';
  } else {
    for (const n of items) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = `news-item clickable tone-${esc(n.tone)}`;
      row.innerHTML = `${esc(n.headline)}<span class="readmore">read all about it →</span>`;
      row.addEventListener("click", () => openArticle(n, s));
      list.appendChild(row);
    }
  }
  el("turn-summary").classList.remove("hidden");
}

const ARTICLE_IMAGE_KEYWORDS = [
  ["pothole", "🚧"], ["baby", "👶"], ["bin", "🗑️"], ["debate", "🎤"],
  ["deposit", "💷"], ["rally", "📣"], ["scandal", "💰"], ["cash", "💰"],
  ["envelope", "✉️"], ["win", "🏆"], ["victory", "🏆"], ["ferry", "⛴️"],
  ["seagull", "🐦"], ["pony", "🐴"], ["moon", "🌕"], ["cheese", "🧀"],
  ["leaflet", "📄"], ["telly", "📺"], ["tweet", "📱"], ["viral", "😂"],
  ["potholes", "🚧"], ["cornwall", "🧀"], ["stream", "📱"],
];

function articleImage(item) {
  const text = item.headline.toLowerCase();
  const picks = [];
  for (const [keyword, emoji] of ARTICLE_IMAGE_KEYWORDS) {
    if (text.includes(keyword) && !picks.includes(emoji)) picks.push(emoji);
    if (picks.length >= 3) break;
  }
  if (!picks.length) picks.push("🗞️", "🎩");
  const fill = item.tone === "good" ? "#37542e" : item.tone === "bad" ? "#542e35" : "#2c3a57";
  const spots = picks
    .map(
      (e, i) =>
        `<text x="${200 + (i - (picks.length - 1) / 2) * 92}" y="122" font-size="62" text-anchor="middle">${e}</text>`
    )
    .join("");
  return `<svg viewBox="0 0 400 200" class="article-svg" role="img" aria-label="Illustration for: ${esc(item.headline)}">
    <defs><pattern id="halftone" width="10" height="10" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.3" fill="#d4a937" opacity="0.3"/></pattern></defs>
    <rect width="400" height="200" fill="${fill}"/>
    <rect width="400" height="200" fill="url(#halftone)"/>
    ${spots}
  </svg>`;
}

function articleText(item, s) {
  const cfg = countryCfg();
  const flavour = cfg ? cfg.flavour : null;
  const paper = flavour
    ? flavour.newspapers[item.week % flavour.newspapers.length]
    : "The Daily Blab";
  const region = s.campaign
    ? s.campaign.region_name
    : s.last_byresult
      ? s.last_byresult.region_name
      : s.country.name;
  const rivals = cfg ? cfg.major_parties : [];
  const rival = rivals.length ? rivals[item.week % rivals.length].short : "the other lot";
  let issue = "local grievances";
  try {
    if (cfg && s.campaign && s.campaign.region_id) {
      const issues = cfg.region(s.campaign.region_id).local_issues;
      issue = issues[item.week % issues.length];
    }
  } catch (e) {
    /* flavour only: never let the news die on a typo */
  }
  const ctx = { party: s.candidate.party_name, rival, region, issue, paper };
  const fill = (t) => t.replace(/\{(\w+)\}/g, (_, k) => (ctx[k] != null ? ctx[k] : ""));

  const openers = {
    good: [
      `Political correspondents were left rubbing their eyes this week as {party} did something that can only be described as competent. In {region}, crowds gathered; several of them even cheered on purpose.`,
      `It was, by any measure, a good week for {party}. {rival} activists were reportedly "disappointed but not surprised", which is the most devastating thing they have said all year.`,
    ],
    bad: [
      `It has not been a smooth seven days for {party}. What was meant to be a routine photo opportunity in {region} has escalated into a full national conversation, none of it helpful.`,
      `{rival} strategists could barely conceal their delight as events overtook {party} this week. "We literally did nothing," a source confirmed. "It just happened."`,
    ],
    neutral: [
      `This week in {region}: politics continued. {party} campaigned, {rival} campaigned, and the electorate went about its business with the weary patience of a queue at the post office.`,
      `Observers say the week passed without incident, unless you count {issue}, which everyone in {region} did, loudly and at length.`,
    ],
  };
  const middles = [
    `At the heart of the story is {issue} — an issue on which every voter in {region} considers themselves the region's leading expert. {party} has pledged action; {rival} has pledged to look into the pledge.`,
    `Insiders describe a campaign war room split between those who want to move on and those who want to "double down, but charmingly". The rosette budget remains undisclosed.`,
    `The arithmetic is unforgiving: with the deposit rule looming over every count, {party} needs more than goodwill — it needs five per cent of a nation famously reluctant to give anyone five per cent.`,
  ];
  const closers = [
    `"I stand by every word," the {party} candidate told this newspaper, adjusting a rosette the size of a dinner plate.`,
    `A spokesperson for {rival} responded with a long sigh and a leaflet. {party} will be hoping the news cycle moves on before polling day in {region}.`,
    `The {paper} political desk will, of course, be following developments with the vigilant indifference our readers deserve.`,
  ];
  const pick = (arr, salt) => arr[(item.week + salt) % arr.length];
  const tone = openers[item.tone] ? item.tone : "neutral";
  return [
    fill(pick(openers[tone], 1)),
    fill(pick(middles, 2)),
    fill(pick(closers, 3)),
  ];
}

function openArticle(item, s) {
  const cfg = countryCfg();
  const flavour = cfg ? cfg.flavour : null;
  const paper = flavour
    ? flavour.newspapers[item.week % flavour.newspapers.length]
    : "The Daily Blab";
  const kickers = {
    good: "🎉 GOOD NEWS FOR THE CAMPAIGN",
    bad: "🔥 TROUBLE AT THE POLLS",
    neutral: "📰 AS IT HAPPENED",
  };
  el("article-paper").textContent = paper.toUpperCase();
  el("article-kicker").textContent = kickers[item.tone] || kickers.neutral;
  el("article-week").textContent = `Week ${item.week}`;
  el("article-image").innerHTML = articleImage(item);
  el("article-headline").textContent = item.headline;
  el("article-byline").textContent = `By our political correspondent · ${paper} · Week ${item.week}`;
  el("article-body").innerHTML = articleText(item, s)
    .map((p) => `<p>${esc(p)}</p>`)
    .join("");
  el("article-view").classList.remove("hidden");
}

function extractDebateEvents(events) {
  const out = [];
  for (let i = 0; i < events.length; i++) {
    if (events[i].startsWith("DEBATE NIGHT")) {
      out.push(events[i]);
      if (events[i + 1] && !events[i + 1].startsWith("DEBATE NIGHT")) {
        out.push(events[i + 1]);
        i++;
      }
    }
  }
  return out;
}

function showDebateModal(lines) {
  el("debate-lines").innerHTML = lines.map((l) => `<p>${esc(l)}</p>`).join("");
  el("debate-modal").classList.remove("hidden");
}

let electionTimer = null;

function runElectionNight(s) {
  const parties = partyMap();
  parties[PLAYER_ID] = { short: s.candidate.party_name || "You", color: s.candidate.color };
  const cfg = countryCfg();
  const names = {};
  if (cfg) {
    for (const r of cfg.regions) names[r.id] = r.name;
  }
  const winners = s.ge_result.region_winners || {};
  // Reveal order: counties grouped by NUTS1 region, roughly north to south.
  const counties = Object.keys(winners).filter((id) => UKMAP.nutsFor(id));
  const order = [];
  for (const { id: nutsId } of UKMAP.NUTS1) {
    for (const county of counties) {
      if (UKMAP.nutsFor(county) === nutsId) order.push(county);
    }
  }

  el("en-map").innerHTML = "";
  el("en-ticker").innerHTML = "";
  el("en-summary").classList.add("hidden");
  el("en-coalition").classList.add("hidden");
  el("en-sub").textContent = "Results are coming in…";
  el("election-night").classList.remove("hidden");

  clearInterval(electionTimer);
  const revealed = {}; // nutsId -> {partyId: counties won so far}
  const nutsColors = {}; // nutsId -> colour, accumulated: once painted, a region stays painted
  let i = 0;
  const step = () => {
    if (i >= order.length) {
      clearInterval(electionTimer);
      finishElectionNight(s, parties);
      return;
    }
    const county = order[i++];
    const pid = winners[county];
    const nuts = UKMAP.nutsFor(county);
    revealed[nuts] = revealed[nuts] || {};
    revealed[nuts][pid] = (revealed[nuts][pid] || 0) + 1;
    let best = null;
    let bestN = -1;
    for (const [p, n] of Object.entries(revealed[nuts])) {
      if (n > bestN) {
        best = p;
        bestN = n;
      }
    }
    const color = best === PLAYER_ID ? s.candidate.color : (parties[best] ? parties[best].color : "#777");
    nutsColors[nuts] = color;
    UKMAP.apply(el("en-map"), nutsColors, nuts, {});
    const p = parties[pid] || { short: pid };
    const tick = document.createElement("div");
    tick.className = "ticker-line" + (pid === PLAYER_ID ? " you" : "");
    tick.textContent = `${names[county] || county} — ${pid === PLAYER_ID ? "🎉 " : ""}${p.short}`;
    el("en-ticker").prepend(tick);
  };
  UKMAP.mount(el("en-map"))
    .then(() => {
      UKMAP.apply(el("en-map"), {}, null, {});
      const interval = Math.max(90, Math.round(2800 / Math.max(order.length, 1)));
      electionTimer = setInterval(step, interval);
      step(); // first result lands immediately
    })
    .catch(() => {
      finishElectionNight(s, parties); // no map, no problem: straight to the count
    });
}

function finishElectionNight(s, parties) {
  el("en-sub").textContent = s.game_over.victory
    ? "And the nation chose CHAOS."
    : "That's the count. It's over.";
  const votes = s.ge_result.national_votes || {};
  const total = Object.values(votes).reduce((a, b) => a + b, 0) || 1;
  const entries = Object.entries(votes)
    .map(([pid, v]) => ({ pid, v, share: v / total, party: parties[pid] || { short: pid, color: "#777" } }))
    .sort((a, b) => b.v - a.v);
  el("en-votes-bar").innerHTML = entries
    .map(
      (e2) =>
        `<span class="vote-seg${e2.pid === PLAYER_ID ? " you" : ""}" style="width:${(e2.share * 100).toFixed(2)}%;background:${esc(e2.party.color)}" title="${esc(e2.party.short)}: ${(e2.share * 100).toFixed(1)}%"></span>`
    )
    .join("");
  el("en-votes-legend").innerHTML = entries
    .slice(0, 6)
    .map(
      (e2) =>
        `<span class="legend-item"><span class="dot" style="background:${esc(e2.party.color)}"></span>${esc(e2.party.short)} ${(e2.share * 100).toFixed(1)}%</span>`
    )
    .join("");
  const seats = Object.entries(s.ge_result.seats || {})
    .map(([pid, n]) => ({ pid, n, party: parties[pid] || { short: pid, color: "#777" } }))
    .sort((a, b) => b.n - a.n);
  el("en-seats").innerHTML = seats
    .map(
      (e2) =>
        `<div class="seat-row${e2.pid === PLAYER_ID ? " you" : ""}"><span class="dot" style="background:${esc(e2.party.color)}"></span>${esc(e2.party.short)} <b>${e2.n}</b></div>`
    )
    .join("");
  if (s.ge_result.coalition_attempted) {
    const c = el("en-coalition");
    c.classList.remove("hidden");
    c.textContent = s.ge_result.coalition_success
      ? "Coalition talks went your way. The keys are yours."
      : "Coalition talks collapsed. Someone took the ball home.";
  }
  el("en-summary").classList.remove("hidden");
}

async function abandonGame() {
  if (state.gameId) {
    try {
      await API.abandon(state.gameId);
    } catch (e) {
      /* already gone is fine */
    }
  }
  state.gameId = null;
  state.snapshot = null;
  state.weekLog = [];
  state.pendingPaper = false;
  el("gameover-overlay").classList.add("hidden");
  el("turn-summary").classList.add("hidden");
  showScreen("title");
  renderSaves();
}

/* ---------- Save / load (Phase 6) ---------- */

async function saveCurrentGame() {
  if (!state.gameId) return;
  try {
    const meta = await API.saveGame(state.gameId);
    showToast(`Campaign saved (week ${meta.week}). The nation holds its breath.`, 3000);
  } catch (err) {
    showToast(err.message, 4200);
  }
}

async function loadSavedGame(saveId) {
  try {
    const res = await API.loadSave(saveId);
    state.gameId = res.game_id;
    state.snapshot = res.state;
    state.weekLog = [];
    // make sure the country config is cached: the newspaper needs its flavour
    const countryId = res.state.country.id;
    state.selectedCountry = countryId;
    if (!state.countryConfigs[countryId]) {
      state.countryConfigs[countryId] = await API.country(countryId);
    }
    el("gameover-overlay").classList.add("hidden");
    el("election-night").classList.add("hidden");
    showScreen("campaign");
    showTab("campaign");
    renderCampaign();
  } catch (err) {
    showToast(err.message, 4200);
  }
}

async function renderSaves() {
  try {
    const saves = await API.saves();
    const section = el("saves-section");
    if (!saves.length) {
      section.classList.add("hidden");
      return;
    }
    section.classList.remove("hidden");
    const list = el("saves-list");
    list.innerHTML = "";
    for (const sv of saves) {
      const card = document.createElement("div");
      card.className = "save-card";
      const outcome = sv.game_over ? (sv.victory ? " · won 🏆" : " · lost") : "";
      card.innerHTML = `
        <div class="save-emoji">${esc(sv.emoji || "🎩")}</div>
        <div class="save-info">
          <div class="save-name">${esc(sv.name)} <span class="dim">· ${esc(sv.party_name)}</span></div>
          <div class="save-meta">Week ${sv.week} · ${sv.wins}/${sv.wins_required} wins · ★ ${Number(sv.momentum).toFixed(1)} · ${esc(sv.difficulty)}${outcome}</div>
          <div class="save-meta dim">${new Date(sv.saved_at).toLocaleString()}</div>
        </div>
        <div class="save-actions">
          <button class="btn-small save-load">Load</button>
          <button class="btn-small save-del" title="Delete save">🗑️</button>
        </div>`;
      card.querySelector(".save-load").addEventListener("click", () => loadSavedGame(sv.save_id));
      card.querySelector(".save-del").addEventListener("click", async () => {
        try {
          await API.deleteSave(sv.save_id);
          renderSaves();
        } catch (e) {
          showToast(e.message, 4200);
        }
      });
      list.appendChild(card);
    }
  } catch (err) {
    /* saves are optional decoration; never block the title screen */
  }
}

/* ---------- Settings tab (Phase 6+) ---------- */

function fillSettings(s) {
  el("set-name").value = s.candidate.name;
  el("set-party").value = s.candidate.party_name;
  el("set-slogan").value = s.candidate.slogan || "";
  el("set-color").value = s.candidate.color;
  state.emoji = s.candidate.emoji || "🎩";
  state.persona = s.candidate.persona || "";
  renderEmojiRowInto("set-emoji-row", () => renderEmojiRowInto("set-emoji-row", () => {}));
  renderPersonaGridInto("set-persona-grid", () =>
    renderPersonaGridInto("set-persona-grid", () => {})
  );
  el("settings-info").textContent = `${s.country.flag_emoji} ${s.country.name} · ${s.difficulty} · week ${s.week}`;
}

async function applySettings() {
  if (!state.gameId) return;
  const fields = {};
  const name = el("set-name").value.trim();
  const party = el("set-party").value.trim();
  if (name) fields.name = name;
  if (party) fields.party_name = party;
  fields.slogan = el("set-slogan").value.trim();
  fields.emoji = state.emoji;
  fields.color = el("set-color").value;
  fields.persona = state.persona;
  try {
    const res = await API.updateCandidate(state.gameId, fields);
    state.snapshot = res.state;
    showToast(res.feedback || "Updated.", 2600);
    renderCampaign();
  } catch (err) {
    showToast(err.message, 4200);
  }
}

/* ---------- Boot ---------- */

async function boot() {
  try {
    const [countries, difficulties] = await Promise.all([
      API.countries(),
      API.difficulties(),
    ]);
    state.countries = countries;
    state.difficulties = difficulties;
    renderCountries();
    renderDifficulties();

    const first = countries[0];
    if (first) {
      const cfg = await API.country(first.id);
      state.countryConfigs[first.id] = cfg;
      showDisclaimerBar(cfg.disclaimer);
    }
    renderSaves();
  } catch (err) {
    showToast(`Failed to reach the game server: ${err.message}`, 6000);
  }
  // PWA: installable / offline-capable (needs https or localhost)
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}

el("start-button").addEventListener("click", enterSetup);
el("back-button").addEventListener("click", () => showScreen("title"));
el("launch-button").addEventListener("click", launchGame);
el("cand-name").addEventListener("input", updateLaunchButton);
el("cand-party").addEventListener("input", updateLaunchButton);
el("end-week-button").addEventListener("click", endWeek);
el("save-button").addEventListener("click", saveCurrentGame);
el("abandon-button").addEventListener("click", abandonGame);
el("apply-settings").addEventListener("click", applySettings);
el("title-button").addEventListener("click", async () => {
  await saveCurrentGame(); // never lose the campaign to a stray click
  el("gameover-overlay").classList.add("hidden");
  showScreen("title");
  renderSaves();
});
document.querySelectorAll(".tab-btn").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab))
);
el("go-button").addEventListener("click", abandonGame);
el("debate-close").addEventListener("click", () => {
  el("debate-modal").classList.add("hidden");
  if (state.pendingPaper && state.snapshot && !state.snapshot.game_over.over) {
    showTurnSummary(state.snapshot); // the presses were waiting for the debate
  }
});
el("paper-close").addEventListener("click", () => el("turn-summary").classList.add("hidden"));
el("article-back").addEventListener("click", () => el("article-view").classList.add("hidden"));
el("en-continue").addEventListener("click", () => {
  el("election-night").classList.add("hidden");
  renderCampaign();
});

el("disclaimer-close").addEventListener("click", () => {
  el("disclaimer-bar").classList.add("hidden");
  localStorage.setItem(DISMISS_KEY, "1");
});

boot();
