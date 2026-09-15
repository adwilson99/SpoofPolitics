/* Loony to Westminster — game engine (client-side port of the Python backend).
   Pure logic, zero server: weekly loop, actions, elections, rival AI, debates,
   events, manifesto synergies, personas, save/load. All state is plain JSON.

   This mirrors backend/game/*.py — when gameplay changes there, port it here
   (or vice versa). Same snapshot shape, same rules, same affectionate cruelty. */
"use strict";

const PLAYER_ID = "__player__";
const BUCKETS = ("youth middle pensioner").split(" ");

/* ------------------------------------------------------------------ actions */

const ACTION_CATALOG = [
  { id: "canvass", name: "Canvass the High Street", emoji: "🧸", desc: "Press the flesh, dodge the awkward questions, collect a few converts.", ap: 1, cost: 0, cp: 6, bias: { youth: 0.3, middle: 0.4, pensioner: 0.3 }, variance: 0, special: "" },
  { id: "leaflets", name: "Deliver Leaflets", emoji: "📄", desc: "Straight into the recycling bin of democracy. Pensioners read every word.", ap: 1, cost: 40, cp: 5, bias: { youth: 0.2, middle: 0.3, pensioner: 0.5 }, variance: 0, special: "" },
  { id: "social_post", name: "Post on Social Media", emoji: "📱", desc: "High risk, high reward. Could go viral; could go 'who is this man'.", ap: 1, cost: 0, cp: 5, bias: { youth: 0.7, middle: 0.25, pensioner: 0.05 }, variance: 0.8, special: "social_post" },
  { id: "baby_kiss", name: "Kiss a Baby", emoji: "👶", desc: "Timeless. Roughly one baby in five screams directly into the camera.", ap: 1, cost: 0, cp: 6, bias: { youth: 0.1, middle: 0.4, pensioner: 0.5 }, variance: 0, special: "baby_kiss" },
  { id: "pub_visit", name: "Buy a Round at the Pub", emoji: "🍺", desc: "Cheap votes and free advice. Everybody in the pub is an expert.", ap: 1, cost: 30, cp: 5, bias: { youth: 0.4, middle: 0.5, pensioner: 0.1 }, variance: 0, special: "" },
  { id: "radio_phone_in", name: "Local Radio Phone-in", emoji: "📻", desc: "Defend your policies against a caller named Terry about parking.", ap: 1, cost: 20, cp: 5, bias: { youth: 0.1, middle: 0.3, pensioner: 0.6 }, variance: 0, special: "" },
  { id: "rally", name: "Hold a Rally", emoji: "🎤", desc: "Flags, foghorns, fainting. Expensive but it moves numbers.", ap: 2, cost: 150, cp: 12, bias: { youth: 0.34, middle: 0.33, pensioner: 0.33 }, variance: 0, special: "" },
  { id: "press_stunt", name: "Stage a Press Stunt", emoji: "📸", desc: "Giant prop, bigger risk. Front page or laughing stock — sometimes both.", ap: 2, cost: 60, cp: 10, bias: { youth: 0.4, middle: 0.35, pensioner: 0.25 }, variance: 0.6, special: "press_stunt" },
  { id: "fundraise", name: "Fundraising Drive", emoji: "💰", desc: "Rattle the tin: crowdfunder push, jumble sale, sponsored silence.", ap: 1, cost: 0, cp: 0, bias: {}, variance: 0, special: "fundraise" },
  { id: "sponsor", name: "Sign a Sponsor", emoji: "🤝", desc: "Take investor money. Bigger war chest, bigger scandal risk. Costs money-time, not AP.", ap: 0, cost: 0, cp: 0, bias: {}, variance: 0, special: "sponsor" },
  { id: "marketing", name: "Buy Marketing", emoji: "📣", desc: "Paid promotion: billboards, video ads, radio spots. Costs money, not AP.", ap: 0, cost: 0, cp: 0, bias: {}, variance: 0, special: "marketing" },
  { id: "force_ge", name: "Force a General Election", emoji: "🎰", desc: "You've built momentum — dare the country to settle it now.", ap: 0, cost: 0, cp: 0, bias: {}, variance: 0, special: "force_ge" },
];
const ACTIONS_BY_ID = {};
for (const a of ACTION_CATALOG) ACTIONS_BY_ID[a.id] = a;

function fmtTemplate(template, ctx) {
  return String(template).replace(/\{(\w+)\}/g, (m, k) => (ctx[k] != null ? ctx[k] : m));
}

/* ---------------------------------------------------------------- elections */

const ELECTIONS = {
  PLAYER_BASE_WEIGHT: 0.2,
  PLAYER_CP_WEIGHT_SCALE: 7.0,
  CP_HALF_SATURATION: 30.0,
  MOMENTUM_WEIGHT_BONUS: 0.05,
  MOMENTUM_CAP: 3.0,
  RIVAL_CP_HALF_SATURATION: 36.0,
  GE_CP_HALF_SATURATION: 70.0,
  NOISE_SIGMA: 0.07,
  BASE_TURNOUT_BOOST: 0.04,
  COALITION_BASE_CHANCE: 0.3,

  eligibleParties(country, region) {
    return country.all_parties.filter((p) => p.regions === null || p.regions.includes(region.id));
  },

  ballotForRegion(country, region, rng) {
    const cap = country.election.max_candidates_on_ballot;
    const eligible = ELECTIONS.eligibleParties(country, region);
    const majorIds = new Set(country.major_parties.map((p) => p.id));
    const spoofIds = new Set(country.spoof_parties.map((p) => p.id));
    const majors = eligible.filter((p) => majorIds.has(p.id));
    const spoofs = eligible.filter((p) => spoofIds.has(p.id));
    const slots = Math.max(0, cap - 1 - majors.length);
    return majors.concat(rng.sample(spoofs, Math.min(spoofs.length, slots)));
  },

  baseWeight(party, region, mood) {
    const d = region.demographics;
    const demo = (party.appeal.youth * d.youth + party.appeal.middle * d.middle + party.appeal.pensioner * d.pensioner) / 100.0;
    const ax = party.axis_fit;
    const axis = 0.4 * (ax.niche_joy * d.niche_joy + ax.protest_mood * d.protest_mood + ax.cost_of_living * d.cost_of_living + ax.change_hungry * d.change_hungry);
    return (demo + 0.5 * axis) * mood;
  },

  cpMultiplier(cp, half) {
    return 1.0 + (2.2 * cp) / (cp + half);
  },

  playerWeight(cpTotal, momentum, half) {
    const w = ELECTIONS.PLAYER_BASE_WEIGHT + (ELECTIONS.PLAYER_CP_WEIGHT_SCALE * cpTotal) / (cpTotal + half);
    return w * (1.0 + ELECTIONS.MOMENTUM_WEIGHT_BONUS * Math.min(momentum, ELECTIONS.MOMENTUM_CAP));
  },

  integerise(weights, totalVotes) {
    const weightTotal = Object.values(weights).reduce((a, b) => a + b, 0);
    const raw = {};
    const votes = {};
    for (const [k, w] of Object.entries(weights)) {
      raw[k] = (w / weightTotal) * totalVotes;
      votes[k] = Math.floor(raw[k]);
    }
    let remaining = totalVotes - Object.values(votes).reduce((a, b) => a + b, 0);
    const byFraction = Object.keys(raw).sort((a, b) => raw[b] - votes[b] - (raw[a] - votes[a]));
    for (const k of byFraction.slice(0, remaining)) votes[k] += 1;
    return votes;
  },

  noisy(weights, rng, sigma = ELECTIONS.NOISE_SIGMA) {
    const out = {};
    for (const [k, w] of Object.entries(weights)) {
      out[k] = w <= 0 ? 0.0 : w * Math.exp(rng.gauss(0.0, sigma));
    }
    return out;
  },

  votesCast(region, cpTotal, rng) {
    const excitement = ELECTIONS.BASE_TURNOUT_BOOST * Math.min(1.0, cpTotal / 60.0);
    const turnout = Math.min(0.85, Math.max(0.3, region.turnout_base + excitement + rng.gauss(0.0, 0.02)));
    return [Math.floor(region.electorate * turnout), turnout];
  },

  runByelection(country, region, mood, playerCp, momentum, rivalCp, rng) {
    const ballot = ELECTIONS.ballotForRegion(country, region, rng);
    const cpTotal = Object.values(playerCp).reduce((a, b) => a + b, 0);

    const weights = {};
    for (const party of ballot) {
      weights[party.id] =
        ELECTIONS.baseWeight(party, region, mood[party.id] != null ? mood[party.id] : 1.0) *
        ELECTIONS.cpMultiplier(rivalCp[party.id] || 0.0, ELECTIONS.RIVAL_CP_HALF_SATURATION);
    }
    weights[PLAYER_ID] = ELECTIONS.playerWeight(cpTotal, momentum, ELECTIONS.CP_HALF_SATURATION);

    const [votesCast, turnout] = ELECTIONS.votesCast(region, cpTotal, rng);
    const votes = ELECTIONS.integerise(ELECTIONS.noisy(weights, rng), votesCast);

    const standings = Object.entries(votes).sort((a, b) => b[1] - a[1]);
    const ranked = [];
    let playerRank = 0;
    let playerShare = 0.0;
    let playerVotes = 0;
    standings.forEach(([pid, v], idx) => {
      const rank = idx + 1;
      const share = votesCast ? v / votesCast : 0.0;
      if (pid === PLAYER_ID) {
        playerRank = rank;
        playerShare = share;
        playerVotes = v;
        ranked.push([pid, "?", v]);
      } else {
        const party = country.all_parties.find((p) => p.id === pid);
        ranked.push([pid, party ? party.short : pid, v]);
      }
    });

    const won = playerRank === 1;
    const depositLost = !won && (playerVotes < country.deposit.vote_threshold || playerShare < (country.deposit.share_threshold ?? 0.05));
    return {
      region_id: region.id,
      region_name: region.name,
      votes_cast: votesCast,
      turnout,
      standings: ranked,
      player_votes: playerVotes,
      player_rank: playerRank,
      player_share: Math.round(playerShare * 10000) / 10000,
      deposit_lost: depositLost,
      won,
    };
  },

  runGeneralElection(country, mood, playerCp, momentum, rivalCp, rng) {
    const cpTotal = Object.values(playerCp).reduce((a, b) => a + b, 0);
    const seats = { [PLAYER_ID]: 0 };
    const national = { [PLAYER_ID]: 0 };
    const regionWinners = {};

    for (const region of country.regions) {
      const ballot = ELECTIONS.ballotForRegion(country, region, rng);
      const weights = {};
      for (const party of ballot) {
        weights[party.id] =
          ELECTIONS.baseWeight(party, region, mood[party.id] != null ? mood[party.id] : 1.0) *
          ELECTIONS.cpMultiplier(rivalCp[party.id] || 0.0, ELECTIONS.GE_CP_HALF_SATURATION);
      }
      weights[PLAYER_ID] = ELECTIONS.playerWeight(cpTotal, momentum, ELECTIONS.GE_CP_HALF_SATURATION);
      const [votesCast] = ELECTIONS.votesCast(region, cpTotal, rng);
      const votes = ELECTIONS.integerise(ELECTIONS.noisy(weights, rng), votesCast);
      const winner = Object.keys(votes).reduce((a, b) => (votes[a] >= votes[b] ? a : b));
      regionWinners[region.id] = winner;
      seats[winner] = (seats[winner] || 0) + 1;
      for (const [pid, v] of Object.entries(votes)) national[pid] = (national[pid] || 0) + v;
    }

    const rankOf = (pid, table) => Object.keys(table).sort((a, b) => table[b] - table[a]).indexOf(pid) + 1;
    const seatsRank = rankOf(PLAYER_ID, seats);
    const votesRank = rankOf(PLAYER_ID, national);

    let coalitionAttempted = false;
    let coalitionSuccess = false;
    let pm = seatsRank === 1;
    if (!pm && votesRank === 1 && seatsRank === 2) {
      coalitionAttempted = true;
      const chance = ELECTIONS.COALITION_BASE_CHANCE + 0.1 * Math.min(momentum, ELECTIONS.MOMENTUM_CAP);
      coalitionSuccess = rng.random() < chance;
      pm = coalitionSuccess;
    }

    return {
      seats,
      national_votes: national,
      player_rank_seats: seatsRank,
      player_rank_votes: votesRank,
      coalition_attempted: coalitionAttempted,
      coalition_success: coalitionSuccess,
      region_winners: regionWinners,
    };
  },
};

/* ----------------------------------------------------------- rival AI (P4) */

const RIVALS = {
  DEBATE_WEEK: 1,
  GENERIC_NEWS: [
    "{short} flood the local Facebook groups with graphics nobody asked for.",
    "{short} hold a photo op next to something vaguely photogenic.",
    "{short} activists descend on the high street in matching rosettes.",
    "A {short} leaflet arrives claiming credit for the weather.",
    "{short} release an attack advert; fact-checkers release a sigh.",
  ],
  SPOOF_NEWS: [
    "{short} arrive by unconventional vehicle. The crowd is delighted.",
    "{short} promise to fix everything, immediately, using nonsense.",
    "{short} out-poll several serious people, somehow.",
    "A {short} candidate is heckled; the heckler becomes a supporter.",
  ],
  STUNT_NEWS: [
    "{short} unveil a vehicle wrapped in their own logo. Traffic chaos. Brand awareness: total.",
    "{short} stage a stunt involving a barge, a brass band and mild legal jeopardy.",
    "{short} abseil down the town hall 'for the Baileywick of local democracy'. Nobody asked.",
    "{short} deliver a manifesto by treasure hunt. The first clue is underwater.",
  ],
  ATTACK_NEWS: [
    "{short} launch a attack ad quoting your manifesto selectively. Very selectively.",
    "{short} demand to know who *really* wrote your leaflets. You wrote them. Mostly.",
    "{short} hand out flyers titled 'Questions {player} Can't Answer'. There are forty.",
  ],
  DEBATE_WIN_FALLBACK: ["Even {short} manages a grudging nod. The nod makes the evening news."],
  DEBATE_LOSE_FALLBACK: ["{short} asks who costed your manifesto. The costing, it turns out, is a napkin."],

  _ctx(state, country, regionName) {
    return {
      short: "",
      player: state.candidate.party_name,
      party: state.candidate.party_name.toUpperCase(),
      region: regionName,
      issue: "",
      newspaper: country.flavour.newspapers[0],
      show: country.flavour.tv_shows[0],
      rival: country.major_parties[0].short,
      symbol: country.currency.symbol,
      amount: String(country.deposit.amount),
    };
  },

  _quip(party, rng, ctx, fallback) {
    const line = party.quips && party.quips.length && rng.random() < 0.65 ? rng.choice(party.quips) : rng.choice(fallback);
    ctx.short = party.short;
    return fmtTemplate(line, ctx);
  },

  _drainBucket(traits, campaign) {
    if (traits.focus !== "even") return traits.focus;
    let best = "youth";
    for (const b of BUCKETS) if ((campaign.player_cp[b] || 0) > (campaign.player_cp[best] || 0)) best = b;
    return best;
  },

  weeklyMoves(state, country, aggression, rng) {
    const news = [];
    const campaign = state.campaign;
    if (!campaign) return news;

    let region = null;
    if (campaign.region_id) region = country.region(campaign.region_id);
    let eligible;
    if (campaign.kind === "general") eligible = country.all_parties;
    else if (region) eligible = ELECTIONS.eligibleParties(country, region);
    else return news;

    const spoofIds = new Set(country.spoof_parties.map((p) => p.id));
    let maxCp = 0;
    for (const p of eligible) maxCp = Math.max(maxCp, campaign.rival_cp[p.id] || 0.0);
    const finalWeek = campaign.weeks_left <= RIVALS.DEBATE_WEEK + 1;
    const ctx = RIVALS._ctx(state, country, region ? region.name : country.election.generalelection_label);

    for (const party of eligible) {
      const traits = party.traits || { aggression: 1.0, focus: "even", variance: 0.2, stunt: 0.15, attack: 0.1, grit: 0.5 };
      const baseEffort = rng.uniform(1.2, 3.2) * (1.0 + 0.03 * state.week);
      let effort = baseEffort * aggression * traits.aggression;
      if (campaign.kind === "general") effort *= 0.9;

      let strategy = "grind";
      const roll = rng.random();
      if (finalWeek && roll < 0.2 + 0.25 * traits.aggression - 0.1 * traits.variance) strategy = "surge";
      else if (maxCp > 8.0 && (campaign.rival_cp[party.id] || 0.0) >= maxCp - 1e-9 && rng.random() < 0.3 - 0.5 * traits.variance) strategy = "coast";
      else if (rng.random() < traits.attack) strategy = "attack";

      if (strategy === "surge") effort *= 1.6;
      else if (strategy === "coast") effort *= 0.55;

      let madeNews = false;
      if (rng.random() < traits.stunt + (strategy === "surge" ? 0.25 : 0.0)) {
        effort += baseEffort * 0.8;
        news.push({ week: state.week, headline: RIVALS._quip(party, rng, ctx, RIVALS.STUNT_NEWS), tone: "neutral" });
        madeNews = true;
      }

      campaign.rival_cp[party.id] = Math.round(((campaign.rival_cp[party.id] || 0.0) + effort) * 100) / 100;

      if (strategy === "attack") {
        const bucket = RIVALS._drainBucket(traits, campaign);
        const drain = Math.min((campaign.player_cp[bucket] || 0.0) * (0.06 + 0.06 * traits.attack), 2.5);
        if (drain > 0) campaign.player_cp[bucket] = Math.max(0.0, campaign.player_cp[bucket] - drain);
        if (!madeNews) {
          news.push({ week: state.week, headline: RIVALS._quip(party, rng, ctx, RIVALS.ATTACK_NEWS), tone: "bad" });
          madeNews = true;
        }
      }

      if (!madeNews && rng.random() < 0.08 + 0.08 * traits.variance) {
        const pool = spoofIds.has(party.id) ? RIVALS.SPOOF_NEWS : RIVALS.GENERIC_NEWS;
        ctx.short = party.short;
        news.push({ week: state.week, headline: fmtTemplate(rng.choice(pool), ctx), tone: "neutral" });
      }
    }
    return news;
  },

  debateNight(state, country, rng, debateBonus = 0.0) {
    const campaign = state.campaign;
    if (!campaign) return null;
    let region = null;
    if (campaign.region_id) region = country.region(campaign.region_id);
    let eligible;
    if (campaign.kind === "general") eligible = country.all_parties;
    else if (region) eligible = ELECTIONS.eligibleParties(country, region);
    else return null;
    if (!eligible.length) return null;

    const frontrunner = eligible.reduce((a, b) => ((campaign.rival_cp[b.id] || 0) > (campaign.rival_cp[a.id] || 0) ? b : a));
    const playerTotal = Object.values(campaign.player_cp).reduce((a, b) => a + b, 0);
    const rivalTotal = Object.values(campaign.rival_cp).reduce((a, b) => a + b, 0);
    const cpShare = playerTotal + rivalTotal > 0 ? playerTotal / (playerTotal + rivalTotal) : 0.0;

    const playerScore = 0.15 + 1.1 * cpShare + 0.05 * state.momentum + debateBonus + rng.gauss(0.0, 0.12);
    const rivalScore = frontrunner.traits.grit * 1.15 + rng.gauss(0.0, 0.12);

    const ctx = RIVALS._ctx(state, country, region ? region.name : country.election.generalelection_label);
    ctx.short = frontrunner.short;

    if (playerScore > rivalScore + 0.05) {
      return {
        headline: `DEBATE NIGHT: ${ctx.party} WINS THE ARGUMENT (TECHNICALLY)`,
        tone: "good",
        lines: [
          "DEBATE NIGHT: you were composed, quotable, and only slightly evasive.",
          RIVALS._quip(frontrunner, rng, ctx, RIVALS.DEBATE_WIN_FALLBACK),
        ],
        cp_factor: 1.0,
        cp_bonus: { youth: 2.0, middle: 2.0, pensioner: 2.0 },
        momentum_delta: 0.25,
      };
    }
    if (playerScore < rivalScore - 0.05) {
      return {
        headline: `DEBATE NIGHT: ${frontrunner.short.toUpperCase()} LANDS THE PUNCHLINES`,
        tone: "bad",
        lines: [
          "DEBATE NIGHT: you said 'the real question is' nine times. It became a drinking game.",
          RIVALS._quip(frontrunner, rng, ctx, RIVALS.DEBATE_LOSE_FALLBACK),
        ],
        cp_factor: 0.88,
        cp_bonus: {},
        momentum_delta: -0.25,
      };
    }
    return {
      headline: "DEBATE NIGHT: DIGNIFIED, COMPETENT, IMMEDIATELY FORGOTTEN",
      tone: "neutral",
      lines: ["DEBATE NIGHT: a draw. The pundits call it 'spiky but pleasant'. Nobody clips it."],
      cp_factor: 1.0,
      cp_bonus: { youth: 1.0, middle: 1.0, pensioner: 1.0 },
      momentum_delta: 0.0,
    };
  },
};

/* ------------------------------------------------- content (P3): manifesto */

const CONTENT = {
  MANIFESTO_MAX: 3,
  MANIFESTO_CP_PER_POLICY: 4.0,

  policyById(country, policyId) {
    const p = country.policies.find((x) => x.id === policyId);
    if (!p) throw new Error(`unknown policy '${policyId}'`);
    return p;
  },

  personaOf(country, personaId) {
    if (!personaId) return null;
    const p = country.personas.find((x) => x.id === personaId);
    if (!p) throw new Error(`unknown persona '${personaId}'`);
    return p;
  },

  _normalise(weights) {
    const total = Object.values(weights).reduce((a, b) => a + b, 0);
    if (total <= 0) {
      const even = {};
      for (const b of BUCKETS) even[b] = 1.0 / BUCKETS.length;
      return even;
    }
    const out = {};
    for (const b of BUCKETS) out[b] = (weights[b] || 0.0) / total;
    return out;
  },

  activeSynergies(country, policyIds) {
    const tags = [];
    for (const pid of policyIds) {
      const p = country.policies.find((x) => x.id === pid);
      if (p) tags.push(...(p.tags || []));
    }
    const out = [];
    for (const syn of country.synergies || []) {
      const needed = syn.requires_tags || [];
      let ok = true;
      for (const tag of new Set(needed)) {
        if (tags.filter((t) => t === tag).length < needed.filter((t) => t === tag).length) {
          ok = false;
          break;
        }
      }
      if (ok && (syn.requires_policies || []).every((pid) => policyIds.includes(pid))) out.push(syn);
    }
    return out;
  },

  buildManifesto(country, policyIds) {
    if (policyIds.length > CONTENT.MANIFESTO_MAX) throw new Error(`a manifesto can hold at most ${CONTENT.MANIFESTO_MAX} policies`);
    if (new Set(policyIds).size !== policyIds.length) throw new Error("duplicate policies in manifesto");
    const policies = policyIds.map((pid) => CONTENT.policyById(country, pid));

    const cp = {};
    for (const b of BUCKETS) cp[b] = 0.0;
    for (const policy of policies) {
      const norm = CONTENT._normalise(policy.appeal || {});
      for (const b of BUCKETS) cp[b] += CONTENT.MANIFESTO_CP_PER_POLICY * norm[b];
    }
    const synergies = CONTENT.activeSynergies(country, policyIds);
    for (const syn of synergies) {
      const norm = CONTENT._normalise(syn.bonus_bias || {});
      for (const b of BUCKETS) cp[b] += syn.bonus_cp * norm[b];
    }
    return { policies, synergies, cp_by_bucket: cp, cp_total: Object.values(cp).reduce((a, b) => a + b, 0) };
  },

  actionCpMultiplier(persona, actionId) {
    return persona ? (persona.action_cp_multipliers[actionId] || 1.0) : 1.0;
  },
  fundraiseMultiplier(persona) {
    return persona ? persona.fundraise_multiplier || 1.0 : 1.0;
  },
  scandalResistance(persona) {
    return persona ? persona.scandal_resistance || 0.0 : 0.0;
  },
  babyCryImmunity(persona) {
    return Boolean(persona && persona.baby_cry_immunity);
  },
  debateBonus(persona) {
    return persona ? persona.debate_bonus || 0.0 : 0.0;
  },

  pickEvent(events, rng, goodBias) {
    const wantGood = rng.random() < goodBias;
    let pool = wantGood ? events.good : events.bad;
    let isGood = wantGood;
    if (!pool.length) {
      pool = wantGood ? events.bad : events.good;
      isGood = !wantGood;
    }
    if (!pool.length) return null;
    const total = pool.reduce((a, e) => a + e.weight, 0);
    let roll = rng.uniform(0, total);
    for (const event of pool) {
      roll -= event.weight;
      if (roll <= 0) return [event, isGood];
    }
    return [pool[pool.length - 1], isGood];
  },

  quietHeadline(country, rng) {
    const t = country.flavour.quiet_week_templates || [];
    return t.length ? rng.choice(t) : "";
  },
};

/* ------------------------------------------------------------- the engine */

const ENGINE_CONST = {
  HEAD_START_CP_CAP: 45.0,
  BABY_CRY_CHANCE: 0.2,
  BABY_GOLD_CHANCE: 0.1,
  BYELECTION_DONATION_BASE: 150,
  BYELECTION_DONATION_PER_STAR: 30,
  SECOND_PLACE_SHARE: 0.12,
  SCANDAL_CP_HIT: 0.35,
  SCANDAL_WEEKLY_CAP: 0.6,
  GE_RIVAL_ENDOWMENT: 16.0,
  PLAYER_GE_ENDOWMENT: 3.0,
  GE_CAMPAIGN_WEEKS: 2,
};

class GameEngine {
  constructor(country, preset, difficultyKey, candidate, seed = null) {
    this.country = country;
    this.preset = preset;
    this.persona = CONTENT.personaOf(country, candidate.persona || "");
    this._manifestoCache = null;
    seed = seed != null ? seed : Math.floor(Math.random() * 2 ** 31);
    this.rng = makeRng(seed);

    const mood = {};
    for (const p of country.all_parties) {
      mood[p.id] = Math.round(Math.min(1.5, Math.max(0.55, this.rng.gauss(1.0, 0.15))) * 1000) / 1000;
    }
    this.state = {
      country_id: country.id,
      difficulty: difficultyKey,
      rng_seed: seed,
      week: 1,
      phase: "between",
      candidate,
      funds: preset.starting_funds,
      ap: preset.ap_per_week,
      ap_per_week: preset.ap_per_week,
      momentum: 0.0,
      wins: 0,
      deposit_forgiveness: preset.deposit_forgiveness,
      deposits_lost: 0,
      scandals: 0,
      ge_turn: preset.ge_turn,
      ge_unlocked: false,
      ge_forced: false,
      next_byelection_week: 2,
      campaigns_fought: 0,
      region_owners: {},
      campaign: null,
      head_start_cp: {},
      sponsors: [],
      marketing: [],
      mood,
      polls: {},
      news: [],
      last_byresult: null,
      ge_result: null,
      game_over: { over: false, victory: false, reason: "" },
    };
    this._updatePolls();
    this._openingNews();
  }

  /* helpers ------------------------------------------------------------ */

  _news(headline, tone = "neutral") {
    this.state.news.push({ week: this.state.week, headline, tone });
    if (this.state.news.length > 80) this.state.news = this.state.news.slice(-80);
  }

  _openingNews() {
    const c = this.state.candidate;
    this._news(`LOCAL ELECTION SHOCK: '${c.party_name}' TO STAND IN UPCOMING BY-ELECTION`);
    if (c.slogan) this._news(`Candidate promises '${c.slogan}'. Nation shrugs, intrigued.`, "good");
  }

  _displayParty(pid) {
    if (pid === PLAYER_ID) {
      const c = this.state.candidate;
      return c.party_name ? `${c.name} (${c.party_name})` : c.name;
    }
    return this.country.party(pid).short;
  }

  _bucketsFor(bias, cp) {
    const total = Object.values(bias).reduce((a, b) => a + b, 0) || 1.0;
    const out = {};
    for (const b of BUCKETS) out[b] = (cp * (bias[b] || 0.0)) / total;
    return out;
  }

  _addPlayerCp(cpByBucket) {
    const target = this.state.campaign ? this.state.campaign.player_cp : this.state.head_start_cp;
    for (const [bucket, amount] of Object.entries(cpByBucket)) {
      target[bucket] = (target[bucket] || 0.0) + amount;
    }
    if (!this.state.campaign) {
      const total = Object.values(this.state.head_start_cp).reduce((a, b) => a + b, 0);
      if (total > ENGINE_CONST.HEAD_START_CP_CAP) {
        const scale = ENGINE_CONST.HEAD_START_CP_CAP / total;
        const scaled = {};
        for (const [b, v] of Object.entries(this.state.head_start_cp)) scaled[b] = v * scale;
        this.state.head_start_cp = scaled;
      }
    }
  }

  /* actions ------------------------------------------------------------ */

  availableActions() {
    const s = this.state;
    const out = [];
    for (const a of ACTION_CATALOG) {
      if (a.id === "force_ge" && !(s.ge_unlocked && s.phase === "between" && !s.game_over.over)) continue;
      const affordable = s.ap >= a.ap && s.funds >= a.cost && !s.game_over.over;
      out.push({
        id: a.id,
        name: a.name,
        emoji: a.emoji,
        desc: a.desc,
        ap: a.ap,
        cost: a.cost,
        affordable,
        reason_unavailable: s.ap >= a.ap && s.funds >= a.cost ? "" : s.ap < a.ap ? "not enough AP" : "not enough funds",
      });
    }
    return out;
  }

  applyAction(actionId, params = {}) {
    const s = this.state;
    if (s.game_over.over) throw new Error("the campaign is over; start a new game");
    const a = ACTIONS_BY_ID[actionId];
    if (!a) throw new Error(`unknown action '${actionId}'`);

    if (actionId === "force_ge") {
      if (!s.ge_unlocked) throw new Error("you haven't earned the momentum to force an election yet");
      if (s.phase !== "between") throw new Error("you can only force an election between campaigns");
      s.ge_forced = true;
      this._news(`${s.candidate.party_name.toUpperCase()} DEMANDS A GENERAL ELECTION: 'SETTLE IT NOW'`, "good");
      return "You hurl the gauntlet. The country will decide.";
    }

    if (s.ap < a.ap) throw new Error(`not enough action points (need ${a.ap}, have ${s.ap})`);
    if (s.funds < a.cost) throw new Error(`not enough funds (need ${this.country.currency.symbol}${a.cost})`);

    const feedback = this._execute(a, params || {});
    s.ap -= a.ap;
    s.funds -= a.cost;
    return feedback;
  }

  _execute(a, params) {
    const s = this.state;
    const handler = a.special;

    if (handler === "fundraise") {
      const amount = Math.trunc((this.rng.randint(60, 140) + 12 * s.momentum) * CONTENT.fundraiseMultiplier(this.persona));
      s.funds += amount;
      return `The tin rattles: +${this.country.currency.symbol}${amount}.`;
    }
    if (handler === "sponsor") return this._signSponsor(params);
    if (handler === "marketing") return this._buyMarketing(params);

    let multiplier = 1.0;
    let feedback = a.desc;

    if (handler === "social_post") {
      multiplier = Math.max(0.1, 1.0 + this.rng.gauss(0.0, a.variance));
      if (multiplier > 1.5) {
        this._news(`${s.candidate.party_name} POST GOES VIRAL: '${s.candidate.slogan || "vote sensibly"}'`, "good");
        feedback = "Your post is everywhere. Even your aunt shared it.";
      } else if (multiplier < 0.5) {
        this._news(`${s.candidate.party_name} post lands with a thud`, "bad");
        feedback = "Four likes. One is your mum. One is suspicious.";
      } else {
        feedback = "A solid post. The internet remains calm.";
      }
    } else if (handler === "baby_kiss") {
      const roll = this.rng.random();
      if (roll < ENGINE_CONST.BABY_CRY_CHANCE) {
        if (CONTENT.babyCryImmunity(this.persona)) {
          feedback = "The baby weighs you up, decides you're one of the good ones, and gurgles approval.";
        } else {
          multiplier = 0.3;
          this._news("BABY-GATE: candidate kissed infant; infant objected loudly", "bad");
          feedback = "The baby screams. The photo makes the local paper. Not the good part.";
        }
      } else if (roll < ENGINE_CONST.BABY_CRY_CHANCE + ENGINE_CONST.BABY_GOLD_CHANCE) {
        multiplier = 1.4;
        this._news("Heartwarming baby photo charms nation, ad execs weep", "good");
        feedback = "The baby giggles. Front page gold.";
      } else {
        feedback = "A pleasant baby. A pleasant photo. Politics continues.";
      }
    } else if (handler === "press_stunt") {
      multiplier = Math.max(0.15, 1.0 + this.rng.gauss(0.0, a.variance));
      if (multiplier > 1.4) {
        this._news(`LOCAL PRESS ENTRANCED BY ${s.candidate.party_name.toUpperCase()} STUNT`, "good");
        feedback = "The stunt dominates the news cycle. Editors demand more.";
      } else if (multiplier < 0.6) {
        this._news(`${s.candidate.party_name} stunt mocked mercilessly online`, "bad");
        feedback = "The prop collapsed. So did the bit.";
      } else {
        feedback = "Decent coverage. The local paper spellt your name right, mostly.";
      }
    }

    const cpRoll =
      a.cp * Math.max(0.2, 1.0 + this.rng.gauss(0.0, a.variance)) * multiplier * CONTENT.actionCpMultiplier(this.persona, a.id);
    this._addPlayerCp(this._bucketsFor(a.bias, cpRoll));
    return feedback;
  }

  _signSponsor(params) {
    const s = this.state;
    if (!this.country.sponsorship) throw new Error("sponsorship is not enabled in this country");
    const tier = (this.country.sponsorship.tiers || []).find((t) => t.id === params.tier_id);
    if (!tier) throw new Error("unknown sponsor tier");
    if (s.sponsors.some((sp) => sp.tier_id === tier.id)) throw new Error("you have already signed this sponsor");
    s.sponsors.push({ tier_id: tier.id, name: tier.name, emoji: tier.emoji, amount: tier.amount, scandal_risk: tier.scandal_risk });
    s.funds += tier.amount;
    this._news(`${s.candidate.party_name} signs ${tier.name}: ${this.country.currency.symbol}${tier.amount} 'no strings attached'`, "bad");
    return `Signed ${tier.emoji} ${tier.name}: +${this.country.currency.symbol}${tier.amount}. What could go wrong?`;
  }

  _buyMarketing(params) {
    const s = this.state;
    const channel = this.country.marketing_channels.find((c) => c.id === params.channel_id);
    if (!channel) throw new Error("unknown marketing channel");
    const cost = Math.trunc(channel.cost);
    if (s.funds < cost) throw new Error("not enough funds for that placement");
    s.funds -= cost;
    const cp = channel.reach * this.preset.marketing_efficiency;
    let weights = {};
    for (const b of BUCKETS) weights[b] = channel.appeal[b] || 0.0;
    if (Object.values(weights).reduce((a, b) => a + b, 0) === 0) {
      for (const b of BUCKETS) weights[b] = 1.0;
    }
    this._addPlayerCp(this._bucketsFor(weights, cp));
    s.marketing.push({ channel_id: channel.id, name: channel.name, emoji: channel.emoji, weeks_left: channel.weeks });
    const where = s.campaign ? `the ${s.campaign.region_name} campaign` : "your next campaign (banked)";
    return `${channel.emoji} ${channel.name} booked for ${where} (-${this.country.currency.symbol}${cost}).`;
  }

  /* the week ----------------------------------------------------------- */

  endWeek() {
    const s = this.state;
    if (s.game_over.over) throw new Error("the campaign is over; start a new game");
    let lines = [];

    for (const n of RIVALS.weeklyMoves(s, this.country, this.preset.rival_aggression, this.rng)) lines.push(n.headline);

    for (const m of s.marketing) m.weeks_left -= 1;
    s.marketing = s.marketing.filter((m) => m.weeks_left > 0);

    lines = lines.concat(this._scandalCheck());
    lines = lines.concat(this._weeklyEvent());

    if (s.campaign) {
      s.campaign.weeks_left -= 1;
      if (s.campaign.kind === "byelection" && s.campaign.weeks_left <= 0) {
        lines = lines.concat(this._resolveByelection());
      } else if (s.campaign && s.campaign.weeks_left === RIVALS.DEBATE_WEEK) {
        lines = lines.concat(this._debateNight());
      }
    }

    if (s.campaign && s.campaign.kind === "general" && (s.campaign.weeks_left <= 0 || s.ge_forced)) {
      lines = lines.concat(this._resolveGeneralElection());
    } else {
      this._rollCalendar();
    }

    if (!lines && s.phase !== "game_over") {
      const quiet = CONTENT.quietHeadline(this.country, this.rng);
      if (quiet) {
        const headline = fmtTemplate(quiet, this._eventContext());
        this._news(headline, "neutral");
        lines.push(headline);
      }
    }

    s.week += 1;
    s.ap = s.ap_per_week;
    this._updatePolls();

    if (s.funds < 0 && !s.game_over.over) {
      s.game_over.over = true;
      s.game_over.victory = false;
      s.game_over.reason = "Bankrupt. The returning officer keeps your deposit, your bike, and what's left of your dignity.";
      s.phase = "game_over";
      lines.push("BANKRUPTCY: the campaign war chest is empty. Game over.");
    }
    return lines;
  }

  _scandalCheck() {
    const s = this.state;
    if (!s.sponsors.length || !this.country.sponsorship) return [];
    let p = Math.min(
      ENGINE_CONST.SCANDAL_WEEKLY_CAP,
      s.sponsors.reduce((a, sp) => a + sp.scandal_risk, 0) * this.preset.scandal_magnitude
    );
    p *= 1.0 - CONTENT.scandalResistance(this.persona);
    if (this.rng.random() >= p) return [];
    s.scandals += 1;
    const template = this.rng.choice(this.country.sponsorship.scandal_headline_templates);
    this._news(fmtTemplate(template, { party: s.candidate.party_name.toUpperCase() }), "bad");

    const factor = 1.0 - ENGINE_CONST.SCANDAL_CP_HIT * this.preset.scandal_magnitude;
    if (s.campaign) s.campaign.player_cp = Object.fromEntries(Object.entries(s.campaign.player_cp).map(([b, v]) => [b, v * factor]));
    s.head_start_cp = Object.fromEntries(Object.entries(s.head_start_cp).map(([b, v]) => [b, v * factor]));

    const lines = [`SCANDAL! Journalists are asking who really funds ${s.candidate.party_name}.`];
    if (s.sponsors.length > 1) {
      const worst = s.sponsors.reduce((a, b) => (b.scandal_risk > a.scandal_risk ? b : a));
      s.sponsors = s.sponsors.filter((sp) => sp !== worst);
      lines.push(`${worst.name} quietly 'distances themselves' from the campaign.`);
      this._news(`${worst.name} distances themselves from ${s.candidate.party_name}`, "neutral");
    }
    return lines;
  }

  /* content ------------------------------------------------------------ */

  _eventContext() {
    const s = this.state;
    let region;
    if (s.campaign && s.campaign.region_id) region = this.country.region(s.campaign.region_id);
    else region = this.rng.choice(this.country.regions);
    const rival = this.rng.choice(this.country.major_parties);
    return {
      party: s.candidate.party_name.toUpperCase(),
      region: region.name,
      issue: this.rng.choice(region.local_issues),
      newspaper: this.rng.choice(this.country.flavour.newspapers),
      show: this.rng.choice(this.country.flavour.tv_shows),
      rival: rival.short,
      symbol: this.country.currency.symbol,
      amount: String(this.country.deposit.amount),
    };
  }

  _weeklyEvent() {
    const s = this.state;
    if (this.preset.event_frequency <= 0) return [];
    const events = this.country.events;
    if (!events || !(events.good.length || events.bad.length)) return [];
    if (this.rng.random() >= this.preset.event_frequency) return [];
    const picked = CONTENT.pickEvent(events, this.rng, this.preset.good_event_bias);
    if (!picked) return [];
    const [event, isGood] = picked;
    const sign = isGood ? 1 : -1;
    const headline = fmtTemplate(event.headline, this._eventContext());
    this._news(headline, isGood ? "good" : "bad");
    if (event.funds) s.funds += sign * event.funds;
    if (event.cp) {
      const add = {};
      for (const b of BUCKETS) add[b] = (sign * event.cp) / BUCKETS.length;
      this._addPlayerCp(add);
    }
    if (event.momentum) s.momentum = Math.max(0.0, s.momentum + sign * event.momentum);
    return [headline];
  }

  _manifestoReport() {
    if (!this._manifestoCache) {
      this._manifestoCache = CONTENT.buildManifesto(this.country, this.state.candidate.policies || []);
    }
    return this._manifestoCache;
  }

  _startCampaign(kind, regionId, weeks) {
    const s = this.state;
    let regionName;
    if (kind === "general") {
      regionName = `the ${this.country.election.generalelection_label}`;
      s.phase = "ge_campaign";
    } else {
      regionName = this.country.region(regionId).name;
      s.phase = "by_campaign";
    }
    const report = this._manifestoReport();
    let startingCp;
    if (kind === "general") {
      startingCp = {}; // a General Election is a whole different fight: the war chest stays in the safe
    } else {
      startingCp = {};
      for (const [b, v] of Object.entries(s.head_start_cp)) startingCp[b] = v * 0.75; // banked enthusiasm fades
    }
    if (report.cp_total > 0) {
      for (const [bucket, amount] of Object.entries(report.cp_by_bucket)) {
        startingCp[bucket] = (startingCp[bucket] || 0.0) + amount;
      }
    }
    s.campaign = {
      kind,
      region_id: regionId,
      region_name: regionName,
      weeks_total: weeks,
      weeks_left: weeks,
      player_cp: startingCp,
      rival_cp: {},
    };
    s.head_start_cp = {};
    if (kind === "general") {
      this._seedGeRivals(s.campaign);
      const recognition = ENGINE_CONST.PLAYER_GE_ENDOWMENT * Math.min(s.wins, 4);
      if (recognition) {
        for (const b of BUCKETS) s.campaign.player_cp[b] = (s.campaign.player_cp[b] || 0.0) + recognition / BUCKETS.length;
      }
      this._news(`THE ${this.country.election.generalelection_label.toUpperCase()} IS ON: ${s.candidate.party_name} fights nationwide`, "neutral");
    } else {
      this._news(`BY-ELECTION CALLED: ${regionName} goes to the polls`, "neutral");
    }
    if (report.policies.length) {
      const names = report.policies.map((p) => `${p.emoji} ${p.name}`).join(", ");
      this._news(`MANIFESTO LAUNCH: ${names}`, "good");
    }
    for (const syn of report.synergies) {
      this._news(`MANIFESTO SYNERGY: ${syn.emoji} ${syn.name} — ${syn.blurb}`, "good");
    }
  }

  _seedGeRivals(campaign) {
    const grow = 1.0 + 0.025 * this.state.week;
    for (const party of this.country.all_parties) {
      let total = 0.0;
      let count = 0;
      for (const region of this.country.regions) {
        if (party.regions !== null && !party.regions.includes(region.id)) continue;
        total += ELECTIONS.baseWeight(party, region, this.state.mood[party.id] != null ? this.state.mood[party.id] : 1.0);
        count += 1;
      }
      const avg = total / Math.max(count, 1);
      const scale = this.preset.ge_defense * grow; // harder modes defend the GE much harder
      campaign.rival_cp[party.id] = Math.round(ENGINE_CONST.GE_RIVAL_ENDOWMENT * scale * avg * 100) / 100;
    }
  }

  _rollCalendar() {
    const s = this.state;
    if (s.campaign) return;
    const geStartWeek = s.ge_turn - this.country.election.campaign_weeks_per_election;
    const geStart = s.ge_forced || s.week + 1 >= geStartWeek;
    if (geStart) {
      this._startCampaign("general", null, ENGINE_CONST.GE_CAMPAIGN_WEEKS);
      return;
    }
    if (s.week + 1 >= s.next_byelection_week) {
      const region = this.rng.choice(this.country.regions);
      const weeks = this.country.election.campaign_weeks_per_election;
      this._startCampaign("byelection", region.id, weeks);
      const rest = Math.max(1, this.preset.byelection_interval_turns - weeks);
      s.next_byelection_week = s.week + 1 + weeks + rest;
    }
  }

  _debateNight() {
    const outcome = RIVALS.debateNight(this.state, this.country, this.rng, CONTENT.debateBonus(this.persona));
    if (!outcome) return [];
    this._news(outcome.headline, outcome.tone);
    if (outcome.cp_factor !== 1.0 && this.state.campaign) {
      this.state.campaign.player_cp = Object.fromEntries(
        Object.entries(this.state.campaign.player_cp).map(([b, v]) => [b, v * outcome.cp_factor])
      );
    }
    if (outcome.cp_bonus) this._addPlayerCp(outcome.cp_bonus);
    if (outcome.momentum_delta) this.state.momentum = Math.max(0.0, this.state.momentum + outcome.momentum_delta);
    return outcome.lines;
  }

  /* elections ----------------------------------------------------------- */

  _resolveByelection() {
    const s = this.state;
    const region = this.country.region(s.campaign.region_id);
    const result = ELECTIONS.runByelection(
      this.country,
      region,
      s.mood,
      s.campaign.player_cp,
      s.momentum,
      s.campaign.rival_cp,
      this.rng
    );
    result.standings = result.standings.map(([pid, , v]) => [pid, this._displayParty(pid), v]);
    s.last_byresult = result;
    s.campaigns_fought += 1;
    s.campaign = null;
    s.phase = "between";
    s.region_owners[region.id] = result.won ? PLAYER_ID : result.standings[0][0];

    const lines = [];
    const cur = this.country.currency.symbol;
    if (result.won) {
      s.wins += 1;
      s.momentum += 1.0;
      const donation = ENGINE_CONST.BYELECTION_DONATION_BASE + ENGINE_CONST.BYELECTION_DONATION_PER_STAR * Math.trunc(s.momentum);
      s.funds += donation;
      this._news(`HISTORIC: ${s.candidate.party_name} WINS ${region.name.toUpperCase()}!`, "good");
      lines.push(`🏆 VICTORY in ${region.name}! ${result.player_votes.toLocaleString()} votes (${(result.player_share * 100).toFixed(1)}%). Donations flood in: +${cur}${donation}.`);
    } else {
      if (result.player_rank === 2 && result.player_share >= ENGINE_CONST.SECOND_PLACE_SHARE) {
        s.momentum += 0.5;
        lines.push(`A gallant second in ${region.name} (${(result.player_share * 100).toFixed(1)}%). Momentum grows (+0.5★).`);
      } else {
        lines.push(`Defeat in ${region.name}: rank #${result.player_rank}, ${result.player_votes.toLocaleString()} votes (${(result.player_share * 100).toFixed(1)}%).`);
      }
      if (result.deposit_lost) {
        if (s.deposit_forgiveness > 0) {
          s.deposit_forgiveness -= 1;
          lines.push(`Under ${this.country.deposit.vote_threshold.toLocaleString()} votes — but a mysterious benefactor covers your ${cur}${this.country.deposit.amount} deposit. Once.`);
        } else {
          s.funds -= this.country.deposit.amount;
          s.deposits_lost += 1;
          lines.push(this.country.deposit.loss_line);
          this._news(`${s.candidate.party_name} loses deposit in ${region.name}`, "bad");
        }
      }
    }

    if (!s.ge_unlocked && s.wins >= this.preset.wins_required) {
      s.ge_unlocked = true;
      this._news(`${s.candidate.party_name} gains national momentum — a General Election beckons`, "good");
      lines.push(`⭐ Wins required reached (${s.wins}/${this.preset.wins_required})! You may now force a General Election — or wait for the clock.`);
    }
    return lines;
  }

  _resolveGeneralElection() {
    const s = this.state;
    const result = ELECTIONS.runGeneralElection(
      this.country,
      s.mood,
      s.campaign.player_cp,
      s.momentum,
      s.campaign.rival_cp,
      this.rng
    );
    s.ge_result = result;
    s.campaign = null;
    s.phase = "game_over";
    s.ge_forced = false;
    Object.assign(s.region_owners, result.region_winners);

    const pm = result.player_rank_seats === 1 || result.coalition_success;
    s.game_over.over = true;
    s.game_over.victory = pm;
    if (pm) {
      let reason = this.rng.choice(this.country.flavour.victory_lines).replace(/\{residence\}/g, this.country.offices.residence);
      if (result.coalition_success) reason = `${this.country.offices.coalition_talks} went your way. ` + reason;
      s.game_over.reason = reason;
    } else {
      s.game_over.reason = this.rng.choice(this.country.flavour.defeat_lines);
    }

    const seatsDesc = Object.entries(result.seats).sort((a, b) => b[1] - a[1]).slice(0, 5);
    const summary = seatsDesc.map(([pid, n]) => `${this._displayParty(pid)}: ${n}`).join(", ");
    const lines = [
      `${this.country.election.generalelection_label} night! Regions won — ${summary}`,
      pm
        ? `You are the new ${this.country.offices.leader_title}! 🎉`
        : `You finish with #${result.player_rank_seats} most regions and #${result.player_rank_votes} in votes. Not this time.`,
    ];
    return lines;
  }

  /* polls ---------------------------------------------------------------- */

  _updatePolls() {
    const s = this.state;
    const polls = {};
    for (const party of this.country.all_parties) {
      let total = 0.0;
      let weight = 0.0;
      for (const region of this.country.regions) {
        if (party.regions !== null && !party.regions.includes(region.id)) continue;
        total += ELECTIONS.baseWeight(party, region, s.mood[party.id] != null ? s.mood[party.id] : 1.0);
        weight += 1.0;
      }
      polls[party.id] = Math.round((total / Math.max(weight, 1.0)) * 10000) / 10000;
    }
    const norm = Object.values(polls).reduce((a, b) => a + b, 0) || 1.0;
    const out = {};
    for (const [pid, v] of Object.entries(polls)) out[pid] = Math.round((v / norm) * 10000) / 10000;
    s.polls = out;
  }

  /* snapshot --------------------------------------------------------------- */

  snapshot() {
    const s = this.state;
    const report = this._manifestoReport();
    const actions = this.availableActions();
    return {
      country: {
        id: this.country.id,
        name: this.country.name,
        flag_emoji: this.country.flag_emoji,
        currency_symbol: this.country.currency.symbol,
        leader_title: this.country.offices.leader_title,
        deposit: this.country.deposit.amount,
        deposit_threshold: this.country.deposit.vote_threshold,
      },
      difficulty: s.difficulty,
      wins_required: this.preset.wins_required,
      week: s.week,
      phase: s.phase,
      candidate: {
        name: s.candidate.name,
        party_name: s.candidate.party_name,
        slogan: s.candidate.slogan,
        emoji: s.candidate.emoji,
        color: s.candidate.color,
        policies: s.candidate.policies,
        persona: s.candidate.persona,
      },
      funds: s.funds,
      ap: s.ap,
      ap_per_week: s.ap_per_week,
      momentum: s.momentum,
      wins: s.wins,
      ge_turn: s.ge_turn,
      ge_unlocked: s.ge_unlocked,
      deposits_lost: s.deposits_lost,
      scandals: s.scandals,
      campaign: s.campaign,
      sponsors: s.sponsors,
      sponsor_tiers: this.country.sponsorship ? this.country.sponsorship.tiers : [],
      marketing: s.marketing,
      marketing_channels: this.country.marketing_channels,
      persona: this.persona,
      manifesto: report.policies,
      synergies: report.synergies,
      manifesto_cp: Math.round(report.cp_total * 100) / 100,
      news: s.news.slice(-12).reverse(),
      last_byresult: s.last_byresult,
      ge_result: s.ge_result,
      game_over: s.game_over,
      region_owners: s.region_owners,
      polls: s.polls,
      actions,
    };
  }

  /* save / load ------------------------------------------------------------ */

  toState() {
    return this.state;
  }

  static fromState(state, country, preset) {
    const engine = new GameEngine(country, preset, state.difficulty, state.candidate, state.rng_seed);
    engine.state = state;
    engine.persona = CONTENT.personaOf(country, state.candidate.persona || "");
    engine._manifestoCache = null;
    engine.rng = makeRng(state.rng_seed ^ 0x5a4e);
    return engine;
  }
}

/* ------------------------------------------------- config expansion (P6) */

function expandCountry(cfg) {
  const parentToSplits = {};
  const regions = [];
  for (const r of cfg.regions) {
    if (!r.splits || !r.splits.length) {
      regions.push(r);
      continue;
    }
    const ids = [];
    for (const sp of r.splits) {
      ids.push(sp.id);
      regions.push({
        id: sp.id,
        name: sp.name,
        electorate: sp.electorate,
        turnout_base: sp.turnout_base != null ? sp.turnout_base : r.turnout_base,
        demographics: sp.demographics || r.demographics,
        local_issues: sp.local_issues || r.local_issues,
      });
    }
    parentToSplits[r.id] = ids;
  }
  cfg.regions = regions;
  for (const p of [].concat(cfg.major_parties, cfg.spoof_parties)) {
    if (p.regions !== null) {
      const mapped = [];
      for (const rid of p.regions) mapped.push(...(parentToSplits[rid] || [rid]));
      p.regions = mapped;
    }
  }
  return cfg;
}

/* handy party accessor used by the engine */
function attachConfigHelpers(cfg) {
  cfg.all_parties = [].concat(cfg.major_parties, cfg.spoof_parties);
  cfg.party = (pid) => {
    const p = cfg.all_parties.find((x) => x.id === pid);
    if (!p) throw new Error(`unknown party id: ${pid}`);
    return p;
  };
  cfg.region = (rid) => {
    const r = cfg.regions.find((x) => x.id === rid);
    if (!r) throw new Error(`unknown region id: ${rid}`);
    return r;
  };
  return cfg;
}

globalThis.ENGINE = {
  GameEngine,
  expandCountry,
  attachConfigHelpers,
  CONTENT,
  ELECTIONS,
  RIVALS,
  fmtTemplate,
  PLAYER_ID,
  BUCKETS,
  ACTION_CATALOG,
};
