"""GameEngine: the weekly campaign loop.

Owns an EngineState plus the country/difficulty configs and a seeded RNG.
All gameplay mutations go through here; the API layer is a thin wrapper.

Turn flow (end_week):
  1. rivals campaign (earn CP, sometimes make news)
  2. marketing placements tick down
  3. scandal check (sponsored campaigns attract journalists)
  4. campaign clock ticks; by-election night / General Election may resolve
  5. calendar rolls over: next by-election or the GE campaign begins
  6. week++, AP refresh, polls update, bankruptcy check
"""
from __future__ import annotations

import random
from typing import Any

from backend.config import loader
from backend.config.loader import CountryConfig, DifficultyPreset
from backend.game import actions as acts
from backend.game import content, elections, rivals
from backend.game.models import (
    ActiveMarketing,
    ByelectionResult,
    CampaignState,
    Candidate,
    EngineState,
    GEResult,
    NewsItem,
    Phase,
    Sponsor,
)

HEAD_START_CP_CAP = 45.0
BABY_CRY_CHANCE = 0.2
BABY_GOLD_CHANCE = 0.1
BYELECTION_DONATION_BASE = 150
BYELECTION_DONATION_PER_STAR = 30
SECOND_PLACE_SHARE = 0.12
SCANDAL_CP_HIT = 0.35
SCANDAL_WEEKLY_CAP = 0.6
GE_RIVAL_ENDOWMENT = 16.0  # rivals' national presence, injected as GE campaign CP
PLAYER_GE_ENDOWMENT = 6.0  # national recognition per by-election win (capped at 4 wins)
GE_CAMPAIGN_WEEKS = 2      # every General Election is a two-week sprint, forced or not


class GameEngine:
    def __init__(
        self,
        country_id: str,
        difficulty: str,
        candidate: Candidate,
        seed: int | None = None,
    ) -> None:
        presets = loader.load_difficulties()
        if difficulty not in presets:
            raise ValueError(f"unknown difficulty '{difficulty}'")
        self.preset: DifficultyPreset = presets[difficulty]
        self.country: CountryConfig = loader.load_country(
            country_id, split_counties=self.preset.split_counties
        )
        self.persona = content.persona_of(self.country, candidate.persona)
        self._manifesto_cache: content.ManifestoReport | None = None
        seed = seed if seed is not None else random.SystemRandom().randrange(2**31)
        self.rng = random.Random(seed)

        mood = {
            p.id: round(min(1.5, max(0.55, self.rng.gauss(1.0, 0.15))), 3)
            for p in self.country.all_parties
        }
        self.state = EngineState(
            country_id=country_id,
            difficulty=difficulty,
            rng_seed=seed,
            candidate=candidate,
            funds=self.preset.starting_funds,
            ap=self.preset.ap_per_week,
            ap_per_week=self.preset.ap_per_week,
            ge_turn=self.preset.ge_turn,
            deposit_forgiveness=self.preset.deposit_forgiveness,
            mood=mood,
            next_byelection_week=2,
        )
        self._update_polls()
        self._opening_news()

    # ------------------------------------------------------------------ news

    def _news(self, headline: str, tone: str = "neutral") -> NewsItem:
        item = NewsItem(week=self.state.week, headline=headline, tone=tone)
        self.state.news.append(item)
        if len(self.state.news) > 80:
            self.state.news = self.state.news[-80:]
        return item

    def _opening_news(self) -> None:
        c = self.state.candidate
        self._news(f"LOCAL ELECTION SHOCK: '{c.party_name}' TO STAND IN UPCOMING BY-ELECTION")
        if c.slogan:
            self._news(f"Candidate promises '{c.slogan}'. Nation shrugs, intrigued.", "good")

    # ------------------------------------------------------------- helpers

    def _display_name(self, party_id: str) -> str:
        if party_id == elections.PLAYER_ID:
            c = self.state.candidate
            return f"{c.name} ({c.party_name})" if c.party_name else c.name
        return self.country.party(party_id).short

    def _buckets_for(self, weights: dict[str, float], cp: float) -> dict[str, float]:
        total = sum(weights.values()) or 1.0
        return {b: cp * weights.get(b, 0.0) / total for b in acts.BUCKETS}

    def _add_player_cp(self, cp_by_bucket: dict[str, float]) -> None:
        if self.state.campaign is not None:
            target = self.state.campaign.player_cp
        else:
            target = self.state.head_start_cp
        for bucket, amount in cp_by_bucket.items():
            target[bucket] = target.get(bucket, 0.0) + amount
        if self.state.campaign is None:
            total = sum(self.state.head_start_cp.values())
            if total > HEAD_START_CP_CAP:
                scale = HEAD_START_CP_CAP / total
                self.state.head_start_cp = {b: v * scale for b, v in self.state.head_start_cp.items()}

    def _total_cp(self) -> float:
        if self.state.campaign is not None:
            return sum(self.state.campaign.player_cp.values())
        return sum(self.state.head_start_cp.values())

    # -------------------------------------------------------------- actions

    def available_actions(self) -> list[dict[str, Any]]:
        out = []
        s = self.state
        for a in acts.CATALOG:
            if a.id == "force_ge" and not (s.ge_unlocked and s.phase == Phase.BETWEEN and not s.game_over.over):
                continue
            out.append(
                {
                    "id": a.id,
                    "name": a.name,
                    "emoji": a.emoji,
                    "desc": a.desc,
                    "ap": a.ap,
                    "cost": a.cost,
                    "affordable": s.ap >= a.ap and s.funds >= a.cost and not s.game_over.over,
                    "reason_unavailable": ""
                    if (s.ap >= a.ap and s.funds >= a.cost)
                    else ("not enough AP" if s.ap < a.ap else "not enough funds"),
                }
            )
        return out

    def apply_action(self, action_id: str, params: dict[str, Any] | None = None) -> str:
        """Perform a player action; returns a feedback line. Raises ValueError on misuse."""
        params = params or {}
        s = self.state
        if s.game_over.over:
            raise ValueError("the campaign is over; start a new game")
        try:
            a = acts.get(action_id)
        except KeyError:
            raise ValueError(f"unknown action '{action_id}'") from None

        if action_id == "force_ge":
            if not s.ge_unlocked:
                raise ValueError("you haven't earned the momentum to force an election yet")
            if s.phase != Phase.BETWEEN:
                raise ValueError("you can only force an election between campaigns")
            s.ge_forced = True
            self._news(f"{s.candidate.party_name.upper()} DEMANDS A GENERAL ELECTION: 'SETTLE IT NOW'", "good")
            return "You hurl the gauntlet. The country will decide."

        if s.ap < a.ap:
            raise ValueError(f"not enough action points (need {a.ap}, have {s.ap})")
        if s.funds < a.cost:
            raise ValueError(f"not enough funds (need {self.country.currency.symbol}{a.cost})")

        feedback = self._execute(a, params)
        s.ap -= a.ap
        s.funds -= a.cost
        return feedback

    def _execute(self, a: acts.ActionDef, params: dict[str, Any]) -> str:
        s = self.state
        handler = a.special

        if handler == "fundraise":
            amount = int((self.rng.randint(60, 140) + 12 * s.momentum) * content.fundraise_multiplier(self.persona))
            s.funds += amount
            return f"The tin rattles: +{self.country.currency.symbol}{amount}."

        if handler == "sponsor":
            return self._sign_sponsor(params)

        if handler == "marketing":
            return self._buy_marketing(params)

        multiplier = 1.0
        feedback = a.desc

        if handler == "social_post":
            multiplier = max(0.1, 1.0 + self.rng.gauss(0.0, a.variance))
            if multiplier > 1.5:
                self._news(f"{s.candidate.party_name} POST GOES VIRAL: '{s.candidate.slogan or 'vote sensibly'}'", "good")
                feedback = "Your post is everywhere. Even your aunt shared it."
            elif multiplier < 0.5:
                self._news(f"{s.candidate.party_name} post lands with a thud", "bad")
                feedback = "Four likes. One is your mum. One is suspicious."
            else:
                feedback = "A solid post. The internet remains calm."

        elif handler == "baby_kiss":
            roll = self.rng.random()
            if roll < BABY_CRY_CHANCE:
                if content.baby_cry_immunity(self.persona):
                    feedback = "The baby weighs you up, decides you're one of the good ones, and gurgles approval."
                else:
                    multiplier = 0.3
                    self._news("BABY-GATE: candidate kissed infant; infant objected loudly", "bad")
                    feedback = "The baby screams. The photo makes the local paper. Not the good part."
            elif roll < BABY_CRY_CHANCE + BABY_GOLD_CHANCE:
                multiplier = 1.4
                self._news("Heartwarming baby photo charms nation, ad execs weep", "good")
                feedback = "The baby giggles. Front page gold."
            else:
                feedback = "A pleasant baby. A pleasant photo. Politics continues."

        elif handler == "press_stunt":
            multiplier = max(0.15, 1.0 + self.rng.gauss(0.0, a.variance))
            if multiplier > 1.4:
                self._news(f"LOCAL PRESS ENTRANCED BY {s.candidate.party_name.upper()} STUNT", "good")
                feedback = "The stunt dominates the news cycle. Editors demand more."
            elif multiplier < 0.6:
                self._news(f"{s.candidate.party_name} stunt mocked mercilessly online", "bad")
                feedback = "The prop collapsed. So did the bit."
            else:
                feedback = "Decent coverage. The local paper spellt your name right, mostly."

        cp_roll = (
            a.cp
            * max(0.2, 1.0 + self.rng.gauss(0.0, a.variance))
            * multiplier
            * content.action_cp_multiplier(self.persona, a.id)
        )
        self._add_player_cp(self._buckets_for(a.bias, cp_roll))
        return feedback

    def _sign_sponsor(self, params: dict[str, Any]) -> str:
        s = self.state
        if self.country.sponsorship is None:
            raise ValueError("sponsorship is not enabled in this country")
        tier_id = params.get("tier_id")
        tier = next((t for t in self.country.sponsorship.tiers if t.id == tier_id), None)
        if tier is None:
            raise ValueError("unknown sponsor tier")
        if any(sp.tier_id == tier.id for sp in s.sponsors):
            raise ValueError("you have already signed this sponsor")
        s.sponsors.append(
            Sponsor(tier_id=tier.id, name=tier.name, emoji=tier.emoji, amount=tier.amount, scandal_risk=tier.scandal_risk)
        )
        s.funds += tier.amount
        self._news(f"{s.candidate.party_name} signs {tier.name}: {self.country.currency.symbol}{tier.amount} 'no strings attached'", "bad")
        return f"Signed {tier.emoji} {tier.name}: +{self.country.currency.symbol}{tier.amount}. What could go wrong?"

    def _buy_marketing(self, params: dict[str, Any]) -> str:
        s = self.state
        channel_id = params.get("channel_id")
        channel = next((c for c in self.country.marketing_channels if c.id == channel_id), None)
        if channel is None:
            raise ValueError("unknown marketing channel")
        cost = int(channel.cost)
        if s.funds < cost:
            raise ValueError("not enough funds for that placement")
        s.funds -= cost
        cp = channel.reach * self.preset.marketing_efficiency
        weights = {b: float(channel.appeal.get(b, 0.0)) for b in acts.BUCKETS}
        if sum(weights.values()) == 0:
            weights = {b: 1.0 for b in acts.BUCKETS}
        self._add_player_cp(self._buckets_for(weights, cp))
        s.marketing.append(
            ActiveMarketing(channel_id=channel.id, name=channel.name, emoji=channel.emoji, weeks_left=channel.weeks)
        )
        where = (
            f"the {s.campaign.region_name} campaign" if s.campaign else "your next campaign (banked)"
        )
        return f"{channel.emoji} {channel.name} booked for {where} (-{self.country.currency.symbol}{cost})."

    # ------------------------------------------------------------- the week

    def end_week(self) -> list[str]:
        """Advance one week; returns feedback/news lines for the UI."""
        s = self.state
        if s.game_over.over:
            raise ValueError("the campaign is over; start a new game")
        lines: list[str] = []

        # 1. rivals campaign
        lines += [n.headline for n in rivals.weekly_moves(s, self.country, self.preset.rival_aggression, self.rng)]

        # 2. marketing ticks
        for m in s.marketing:
            m.weeks_left -= 1
        s.marketing = [m for m in s.marketing if m.weeks_left > 0]

        # 3. scandal check
        lines += self._scandal_check()

        # 3b. weekly random event (Phase 3 content)
        lines += self._weekly_event()

        # 4. campaign clock
        if s.campaign is not None:
            s.campaign.weeks_left -= 1
            if s.campaign.kind == "byelection" and s.campaign.weeks_left <= 0:
                lines += self._resolve_byelection()
            elif s.campaign is not None and s.campaign.weeks_left == rivals.DEBATE_WEEK:
                lines += self._debate_night()

        # 5/6. general election phase management & calendar
        if s.campaign is not None and s.campaign.kind == "general" and (s.campaign.weeks_left <= 0 or s.ge_forced):
            lines += self._resolve_general_election()
        else:
            self._roll_calendar()

        # quiet week? the press will fill the void regardless
        if not lines and s.phase != Phase.GAME_OVER:
            quiet = content.quiet_headline(self.country, self.rng)
            if quiet:
                quiet = quiet.format(**self._event_context())
                self._news(quiet, "neutral")
                lines.append(quiet)

        # weekly reset
        s.week += 1
        s.ap = s.ap_per_week
        self._update_polls()

        if s.funds < 0 and not s.game_over.over:
            s.game_over.over = True
            s.game_over.victory = False
            s.game_over.reason = "Bankrupt. The returning officer keeps your deposit, your bike, and what's left of your dignity."
            s.phase = Phase.GAME_OVER
            lines.append("BANKRUPTCY: the campaign war chest is empty. Game over.")
        return lines

    def _scandal_check(self) -> list[str]:
        s = self.state
        if not s.sponsors or self.country.sponsorship is None:
            return []
        p = min(SCANDAL_WEEKLY_CAP, sum(sp.scandal_risk for sp in s.sponsors) * self.preset.scandal_magnitude)
        p *= 1.0 - content.scandal_resistance(self.persona)
        if self.rng.random() >= p:
            return []
        s.scandals += 1
        template = self.rng.choice(self.country.sponsorship.scandal_headline_templates)
        self._news(template.format(party=s.candidate.party_name.upper()), "bad")

        factor = 1.0 - SCANDAL_CP_HIT * self.preset.scandal_magnitude
        if s.campaign is not None:
            s.campaign.player_cp = {b: v * factor for b, v in s.campaign.player_cp.items()}
        s.head_start_cp = {b: v * factor for b, v in s.head_start_cp.items()}

        lines = [f"SCANDAL! Journalists are asking who really funds {s.candidate.party_name}."]
        if len(s.sponsors) > 1:
            worst = max(s.sponsors, key=lambda sp: sp.scandal_risk)
            s.sponsors.remove(worst)
            lines.append(f"{worst.name} quietly 'distances themselves' from the campaign.")
            self._news(f"{worst.name} distances themselves from {s.candidate.party_name}", "neutral")
        return lines

    # ------------------------------------------------------------- content

    def _debate_night(self) -> list[str]:
        """Phase 4: the traditional final-week debate vs the frontrunner rival."""
        outcome = rivals.debate_night(self.state, self.country, self.rng, content.debate_bonus(self.persona))
        if outcome is None:
            return []
        self._news(outcome.headline, outcome.tone)
        if outcome.cp_factor != 1.0 and self.state.campaign is not None:
            self.state.campaign.player_cp = {
                b: v * outcome.cp_factor for b, v in self.state.campaign.player_cp.items()
            }
        if outcome.cp_bonus:
            self._add_player_cp(outcome.cp_bonus)
        if outcome.momentum_delta:
            self.state.momentum = max(0.0, self.state.momentum + outcome.momentum_delta)
        return outcome.lines

    def _event_context(self) -> dict[str, str]:
        """Placeholders for event / quiet-week headline templates."""
        s = self.state
        if s.campaign is not None and s.campaign.region_id:
            region = self.country.region(s.campaign.region_id)
        else:
            region = self.rng.choice(self.country.regions)
        rival = self.rng.choice(self.country.major_parties)
        return {
            "party": s.candidate.party_name.upper(),
            "region": region.name,
            "issue": self.rng.choice(region.local_issues),
            "newspaper": self.rng.choice(self.country.flavour.newspapers),
            "show": self.rng.choice(self.country.flavour.tv_shows),
            "rival": rival.short,
            "symbol": self.country.currency.symbol,
            "amount": str(self.country.deposit.amount),
        }

    def _weekly_event(self) -> list[str]:
        """Roll one random news event (Phase 3); apply its funds/cp/momentum effects."""
        s = self.state
        if self.preset.event_frequency <= 0:
            return []
        events = self.country.events
        if not (events.good or events.bad):
            return []
        if self.rng.random() >= self.preset.event_frequency:
            return []
        picked = content.pick_event(events, self.rng, self.preset.good_event_bias)
        if picked is None:
            return []
        event, is_good = picked
        sign = 1 if is_good else -1
        headline = event.headline.format(**self._event_context())
        self._news(headline, "good" if is_good else "bad")
        if event.funds:
            s.funds += sign * event.funds
        if event.cp:
            self._add_player_cp({b: sign * event.cp / len(content.BUCKETS) for b in content.BUCKETS})
        if event.momentum:
            s.momentum = max(0.0, s.momentum + sign * event.momentum)
        return [headline]

    def _manifesto_report(self) -> content.ManifestoReport:
        if self._manifesto_cache is None:
            self._manifesto_cache = content.build_manifesto(self.country, self.state.candidate.policies)
        return self._manifesto_cache

    def _start_campaign(self, kind: str, region_id: str | None, weeks: int) -> None:
        s = self.state
        if kind == "general":
            region_name = f"the {self.country.election.generalelection_label}"
            s.phase = Phase.GE_CAMPAIGN
        else:
            region = self.country.region(region_id)
            region_name = region.name
            s.phase = Phase.BY_CAMPAIGN
        report = self._manifesto_report()
        if kind == "general":
            # A General Election is a whole different fight: the by-election
            # war chest stays in the safe. You arrive with recognition, not CP.
            starting_cp: dict[str, float] = {}
        else:
            # banked enthusiasm fades: some of what you stored since last time evaporates
            starting_cp = {b: v * 0.75 for b, v in s.head_start_cp.items()}
        if report.cp_total:
            for bucket, amount in report.cp_by_bucket.items():
                starting_cp[bucket] = starting_cp.get(bucket, 0.0) + amount
        s.campaign = CampaignState(
            kind=kind,
            region_id=region_id,
            region_name=region_name,
            weeks_total=weeks,
            weeks_left=weeks,
            player_cp=starting_cp,
            rival_cp={},
        )
        s.head_start_cp = {}
        if kind == "general":
            self._seed_ge_rivals(s.campaign)
            recognition = PLAYER_GE_ENDOWMENT * min(s.wins, 4)
            if recognition:
                share = recognition / len(acts.BUCKETS)
                for bucket in acts.BUCKETS:
                    s.campaign.player_cp[bucket] = s.campaign.player_cp.get(bucket, 0.0) + share
            self._news(f"THE {self.country.election.generalelection_label.upper()} IS ON: {s.candidate.party_name} fights nationwide", "neutral")
        else:
            self._news(f"BY-ELECTION CALLED: {region_name} goes to the polls", "neutral")
        if report.policies:
            names = ", ".join(f"{p.emoji} {p.name}" for p in report.policies)
            self._news(f"MANIFESTO LAUNCH: {names}", "good")
        for syn in report.synergies:
            self._news(f"MANIFESTO SYNERGY: {syn.emoji} {syn.name} — {syn.blurb}", "good")

    def _seed_ge_rivals(self, campaign: CampaignState) -> None:
        """Rivals start the General Election with their national standing — which
        grows the longer you take to get there. The establishment multiplies."""
        grow = 1.0 + 0.025 * self.state.week
        for party in self.country.all_parties:
            total, regions = 0.0, 0
            for region in self.country.regions:
                if party.regions is not None and region.id not in party.regions:
                    continue
                total += elections.base_weight(party, region, self.state.mood.get(party.id, 1.0))
                regions += 1
            avg = total / max(regions, 1)
            scale = self.preset.ge_defense * grow  # harder modes defend the GE much harder
            campaign.rival_cp[party.id] = round(GE_RIVAL_ENDOWMENT * scale * avg, 2)

    def _roll_calendar(self) -> None:
        """If no campaign is running, maybe start one for next week."""
        s = self.state
        if s.campaign is not None:
            return
        ge_start_week = s.ge_turn - self.country.election.campaign_weeks_per_election
        ge_start = s.ge_forced or s.week + 1 >= ge_start_week

        if ge_start:
            self._start_campaign("general", None, GE_CAMPAIGN_WEEKS)
            return
        if s.week + 1 >= s.next_byelection_week:
            region = self.rng.choice(self.country.regions)
            weeks = self.country.election.campaign_weeks_per_election
            self._start_campaign("byelection", region.id, weeks)
            rest = max(1, self.preset.byelection_interval_turns - weeks)
            # next campaign starts after this one (starts next week, runs `weeks`) + rest
            s.next_byelection_week = s.week + 1 + weeks + rest

    # ------------------------------------------------------------ elections

    def _resolve_byelection(self) -> list[str]:
        s = self.state
        region = self.country.region(s.campaign.region_id)
        result = elections.run_byelection(
            country=self.country,
            region=region,
            mood=s.mood,
            player_cp=s.campaign.player_cp,
            momentum=s.momentum,
            rival_cp=s.campaign.rival_cp,
            rng=self.rng,
        )
        result.standings = [
            (pid, self._display_name(pid), v) for pid, _, v in result.standings
        ]
        s.last_byresult = result
        s.campaigns_fought += 1
        s.campaign = None
        s.phase = Phase.BETWEEN
        # the seat changes hands and STAYS changed until someone wins it back
        winner = elections.PLAYER_ID if result.won else result.standings[0][0]
        s.region_owners[region.id] = winner

        lines: list[str] = []
        cur = self.country.currency.symbol
        if result.won:
            s.wins += 1
            s.momentum += 1.0
            donation = BYELECTION_DONATION_BASE + BYELECTION_DONATION_PER_STAR * int(s.momentum)
            s.funds += donation
            self._news(f"HISTORIC: {s.candidate.party_name} WINS {region.name.upper()}!", "good")
            lines.append(
                f"🏆 VICTORY in {region.name}! {result.player_votes:,} votes "
                f"({result.player_share:.1%}). Donations flood in: +{cur}{donation}."
            )
        else:
            if result.player_rank == 2 and result.player_share >= SECOND_PLACE_SHARE:
                s.momentum += 0.5
                lines.append(
                    f"A gallant second in {region.name} ({result.player_share:.1%}). "
                    f"Momentum grows (+0.5★)."
                )
            else:
                lines.append(
                    f"Defeat in {region.name}: rank #{result.player_rank}, "
                    f"{result.player_votes:,} votes ({result.player_share:.1%})."
                )
            if result.deposit_lost:
                if s.deposit_forgiveness > 0:
                    s.deposit_forgiveness -= 1
                    lines.append(
                        f"Under {self.country.deposit.vote_threshold:,} votes — but a mysterious "
                        f"benefactor covers your {cur}{self.country.deposit.amount} deposit. Once."
                    )
                else:
                    s.funds -= self.country.deposit.amount
                    s.deposits_lost += 1
                    lines.append(self.country.deposit.loss_line)
                    self._news(
                        f"{s.candidate.party_name} loses deposit in {region.name}", "bad"
                    )

        if not s.ge_unlocked and s.wins >= self.preset.wins_required:
            s.ge_unlocked = True
            self._news(f"{s.candidate.party_name} gains national momentum — a General Election beckons", "good")
            lines.append(
                f"⭐ Wins required reached ({s.wins}/{self.preset.wins_required})! "
                "You may now force a General Election — or wait for the clock."
            )
        return lines

    def _resolve_general_election(self) -> list[str]:
        s = self.state
        result = elections.run_general_election(
            country=self.country,
            mood=s.mood,
            player_cp=s.campaign.player_cp,
            momentum=s.momentum,
            rival_cp=s.campaign.rival_cp,
            rng=self.rng,
        )
        s.ge_result = result
        s.campaign = None
        s.phase = Phase.GAME_OVER
        s.ge_forced = False
        s.region_owners.update(result.region_winners)

        pm = result.player_rank_seats == 1 or result.coalition_success
        s.game_over.over = True
        s.game_over.victory = pm
        if pm:
            reason = self.rng.choice(self.country.flavour.victory_lines).format(
                residence=self.country.offices.residence
            )
            if result.coalition_success:
                reason = f"{self.country.offices.coalition_talks} went your way. " + reason
        else:
            reason = self.rng.choice(self.country.flavour.defeat_lines)
        s.game_over.reason = reason

        seats_desc = sorted(result.seats.items(), key=lambda kv: kv[1], reverse=True)
        summary = ", ".join(f"{self._display_name(pid)}: {n}" for pid, n in seats_desc[:5])
        return [
            f"{self.country.election.generalelection_label} night! Regions won — {summary}",
            (
                f"You are the new {self.country.offices.leader_title}! 🎉"
                if pm
                else f"You finish with #{result.player_rank_seats} most regions and #{result.player_rank_votes} in votes. Not this time."
            ),
        ]

    # ---------------------------------------------------------------- polls

    def _update_polls(self) -> None:
        """Rough national standing estimate for the UI (purely cosmetic)."""
        s = self.state
        polls: dict[str, float] = {}
        for party in self.country.all_parties:
            total = 0.0
            weight = 0.0
            for region in self.country.regions:
                if party.regions is not None and region.id not in party.regions:
                    continue
                total += elections.base_weight(party, region, s.mood.get(party.id, 1.0))
                weight += 1.0
            polls[party.id] = round(total / max(weight, 1.0), 4)
        norm = sum(polls.values()) or 1.0
        s.polls = {pid: round(v / norm, 4) for pid, v in polls.items()}

    # ------------------------------------------------------------- snapshot

    def snapshot(self) -> dict[str, Any]:
        s = self.state
        report = self._manifesto_report()
        return {
            "country": {
                "id": self.country.id,
                "name": self.country.name,
                "flag_emoji": self.country.flag_emoji,
                "currency_symbol": self.country.currency.symbol,
                "leader_title": self.country.offices.leader_title,
                "deposit": self.country.deposit.amount,
                "deposit_threshold": self.country.deposit.vote_threshold,
            },
            "difficulty": self.state.difficulty,
            "wins_required": self.preset.wins_required,
            "week": s.week,
            "phase": s.phase.value,
            "candidate": s.candidate.model_dump(),
            "funds": s.funds,
            "ap": s.ap,
            "ap_per_week": s.ap_per_week,
            "momentum": s.momentum,
            "wins": s.wins,
            "ge_turn": s.ge_turn,
            "ge_unlocked": s.ge_unlocked,
            "deposits_lost": s.deposits_lost,
            "scandals": s.scandals,
            "campaign": s.campaign.model_dump() if s.campaign else None,
            "sponsors": [sp.model_dump() for sp in s.sponsors],
            "sponsor_tiers": [
                t.model_dump() for t in (self.country.sponsorship.tiers if self.country.sponsorship else [])
            ],
            "marketing": [m.model_dump() for m in s.marketing],
            "marketing_channels": [c.model_dump() for c in self.country.marketing_channels],
            "persona": self.persona.model_dump() if self.persona else None,
            "manifesto": [p.model_dump() for p in report.policies],
            "synergies": [syn.model_dump() for syn in report.synergies],
            "manifesto_cp": round(report.cp_total, 2),
            "news": [n.model_dump() for n in reversed(s.news[-12:])],
            "last_byresult": s.last_byresult.model_dump() if s.last_byresult else None,
            "ge_result": s.ge_result.model_dump() if s.ge_result else None,
            "game_over": s.game_over.model_dump(),
            "region_owners": s.region_owners,
            "polls": s.polls,
            "actions": self.available_actions(),
        }

    # --------------------------------------------------------------- saving

    def to_json(self) -> dict[str, Any]:
        return self.state.model_dump()

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "GameEngine":
        state = EngineState.model_validate(data)
        engine = cls.__new__(cls)
        engine.preset = loader.load_difficulties()[state.difficulty]
        engine.country = loader.load_country(
            state.country_id, split_counties=engine.preset.split_counties
        )
        engine.rng = random.Random(state.rng_seed ^ 0x5A4E)  # "ZANS": diverge from game RNG
        engine.state = state
        engine.persona = content.persona_of(engine.country, state.candidate.persona)
        engine._manifesto_cache = None
        return engine
