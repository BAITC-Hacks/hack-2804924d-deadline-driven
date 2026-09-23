"""Beeline agent: public data -> adaptive pilots -> budgeted campaigns.

No imports from environment, mock_environment or scoring_core. No network.
Historical transitions rank hypotheses; only pilots validate target effects.
"""
from pathlib import Path
from math import sqrt, isfinite
import time

import numpy as np
import pandas as pd


class Agent:
    def __init__(self):
        self.report = {}

    def _history(self):
        path = Path(__file__).resolve().parent / "data" / "change_tariff.csv"
        try:
            h = pd.read_csv(path)
            before = pd.to_numeric(h.AVG_ARPU_PREV_3M, errors="coerce")
            after = pd.to_numeric(h.AVG_ARPU_NEXT_3M, errors="coerce")
            h = h.loc[(before > 0) & (after >= 0)].copy()
            before, after = before.loc[h.index], after.loc[h.index]
            h["segment"] = np.where(before < 1000, "LOW", np.where(before > 5000, "HIGH", "MID"))
            # Robust descriptive prior: extreme ratios from tiny denominators
            # should not dominate rankings. This is not a conversion estimate.
            h["relative"] = ((after - before) / before).clip(-1, 2)
            groups = h.groupby(["tariff_plan_code_from", "segment", "tariff_plan_code_to"])
            return {key: (float(g.relative.mean()), len(g)) for key, g in groups}
        except (OSError, ValueError, AttributeError, KeyError) as exc:
            self.report["history_warning"] = str(exc)
            return {}

    def _cells(self, profile):
        cells = []
        for (current, arpu), group in profile.groupby(["current_tariff", "arpu_segment"], observed=True, sort=True):
            filters = {"filter_current_tariff": str(current), "filter_arpu_segment": str(arpu)}
            pieces = [(filters, group)]
            # Do not silently truncate: every selected audience is expressible
            # with the SDK's public filters.
            for column in ("data_segment", "call_segment"):
                refined = []
                for f, g in pieces:
                    if len(g) <= 5000:
                        refined.append((f, g))
                    else:
                        refined.extend((dict(f, **{"filter_" + column: str(v)}), sub)
                                       for v, sub in g.groupby(column, observed=True, sort=True))
                pieces = refined
            for f, g in pieces:
                if 10 <= len(g) <= 5000:
                    cells.append({"filters": f, "current": str(current), "segment": str(arpu),
                                  "n": len(g), "arpu": float(g.predicted_arpu.sum()),
                                  "unexposed": 1.0})
        return cells

    @staticmethod
    def _estimate(arm):
        # Weak historical prior. Noise scale 0.8 is stated in public SDK docs;
        # do not infer it from hidden effect tables or mock fallback functions.
        weight = 8.0
        count = arm["samples"]
        mean = (weight * arm["prior"] + arm["weighted_sum"]) / (weight + count)
        uncertainty = 0.8 / arm["pilot_multiplier"] / sqrt(weight + count)
        return mean, uncertainty

    @classmethod
    def _channel_estimate(cls, arm, channel, channels):
        observation = arm["channel_observations"].get(channel)
        if observation:
            count, weighted = observation
            return weighted / count, .8 / sqrt(count)
        mean, uncertainty = cls._estimate(arm)
        multiplier = channels[channel]["multiplier"]
        return mean * multiplier, uncertainty * multiplier

    def act(self, env):
        started = time.monotonic()
        self.report = {"pilots": [], "warnings": [], "campaigns": []}
        profile = env.customer_profile
        required = {"ID_NUMBER", "current_tariff", "arpu_segment", "data_segment", "call_segment", "predicted_arpu"}
        if not required.issubset(profile.columns):
            raise ValueError("Missing profile columns: " + str(sorted(required - set(profile.columns))))
        if profile.ID_NUMBER.duplicated().any() or not np.isfinite(profile.predicted_arpu).all():
            raise ValueError("Profile contains duplicate IDs or non-finite ARPU")
        tariffs = sorted(str(t) for t in env.tariffs.tariff_plan_code)
        channels = {str(k): {"cost": float(v["cost_per_contact"]),
                             "multiplier": float(v["conversion_multiplier"])}
                    for k, v in env.channels.items()}
        if any(not isfinite(v["cost"]) or not isfinite(v["multiplier"])
               or v["cost"] < 0 or v["multiplier"] <= 0 for v in channels.values()):
            raise ValueError("Invalid channel parameters")
        # Prefer an inexpensive informative channel, adapting to available money.
        affordable = [k for k in channels if channels[k]["cost"] * 150 <= env.remaining_budget * .25]
        if not affordable:
            affordable = [min(channels, key=lambda k: channels[k]["cost"])]
        pilot_channel = max(affordable, key=lambda k: channels[k]["multiplier"] ** 2 / (1 + channels[k]["cost"] / 20))
        multiplier = channels[pilot_channel]["multiplier"]
        cost = channels[pilot_channel]["cost"]
        cells = self._cells(profile)
        history = self._history()
        arms = []
        for cell_id, cell in enumerate(cells):
            choices = []
            for target in tariffs:
                if target == cell["current"]:
                    continue
                historical, n = history.get((cell["current"], cell["segment"], target), (0., 0))
                shrunk = historical * n / (n + 30)
                choices.append((shrunk, target, n))
            # A few alternatives per audience; limited pilots must also cover
            # different customer groups. Tie breaks are deterministic.
            for historical, target, n in sorted(choices, reverse=True)[:3]:
                arms.append({"cell": cell_id, "target": target,
                             "prior": .15 * historical, "history_n": n,
                             "samples": 0, "weighted_sum": 0., "batches": 0,
                             "pilot_multiplier": multiplier, "failed": False,
                             "channel_observations": {}, "failed_channels": set()})
        initial_budget, initial_contacts = float(env.remaining_budget), int(env.remaining_contacts)
        exploration_budget = .25 * initial_budget
        exploration_contacts = min(3000, int(.25 * initial_contacts))
        spent = used = 0
        pilot_limit = min(20, int(env.pilots_left))
        # Reserve up to four calls for direct validation of expensive channels.
        confirmation_slots = min(4, max(0, pilot_limit - 1))
        for step in range(pilot_limit - confirmation_slots):
            if time.monotonic() - started > 240 or env.pilots_left <= 0:
                break
            cap = min(200, exploration_contacts - used, int(env.remaining_contacts) - 10)
            if cost:
                cap = min(cap, int(min(exploration_budget-spent, env.remaining_budget) // cost))
            if cap < 10:
                break
            options = []
            per_cell = {i: sum(a["batches"] for a in arms if a["cell"] == i) for i in range(len(cells))}
            for i, arm in enumerate(arms):
                if arm["failed"]:
                    continue
                cell = cells[arm["cell"]]
                mean, se = self._estimate(arm)
                if arm["samples"] == 0:
                    # First rounds cover distinct high-value hypotheses.
                    score = cell["arpu"] * (max(0., mean) + .10) / (1 + per_cell[arm["cell"]])
                    if step >= min(12, pilot_limit):
                        score *= .35
                else:
                    if step < min(12, pilot_limit):
                        continue
                    score = cell["arpu"] * max(0., mean + se) / sqrt(1 + arm["batches"])
                options.append((score, -i, i))
            if not options:
                break
            arm = arms[max(options)[2]]
            cell = cells[arm["cell"]]
            n = min(cap, cell["n"], 150 if arm["samples"] == 0 else 200)
            try:
                result = env.run_pilot(target_tariff=arm["target"], channel=pilot_channel,
                                       n_customers=n, **cell["filters"])
            except (RuntimeError, ValueError) as exc:
                arm["failed"] = True
                self.report["warnings"].append(str(exc))
                continue
            actual, ratio = int(result["n_customers"]), float(result["observed_lift_ratio"])
            used = initial_contacts - int(env.remaining_contacts)
            spent = initial_budget - float(env.remaining_budget)
            if actual <= 0 or not isfinite(ratio):
                arm["failed"] = True
                self.report["warnings"].append("Invalid pilot observation")
                continue
            arm["samples"] += actual
            cell["unexposed"] *= max(0., 1 - actual / cell["n"])
            arm["weighted_sum"] += actual * ratio / multiplier
            arm["batches"] += 1
            arm["channel_observations"][pilot_channel] = (
                arm["samples"], arm["weighted_sum"] * multiplier)
            self.report["pilots"].append({"filters": dict(cell["filters"]), "target": arm["target"],
                                           "channel": pilot_channel, "n": actual, "ratio": ratio,
                                           "cost": float(result["cost"]), "phase": "exploration"})

        for _ in range(confirmation_slots):
            if env.pilots_left <= 0 or time.monotonic() - started > 240:
                break
            provisional = self._select(arms, cells, channels, float(env.remaining_budget),
                                       int(env.remaining_contacts), pilot_channel, provisional=True)
            checks = []
            for i, channel in provisional:
                arm, ch = arms[i], channels[channel]
                cell = cells[arm["cell"]]
                if (ch["cost"] <= cost or channel in arm["channel_observations"]
                        or channel in arm["failed_channels"]):
                    continue
                n = min(150, cell["n"], int(env.remaining_contacts) - cell["n"],
                        int(.25 * initial_contacts) - used)
                if ch["cost"]:
                    n = min(n, int(min(exploration_budget - spent, env.remaining_budget) // ch["cost"]))
                if n < 10:
                    continue
                mean, se = self._channel_estimate(arm, channel, channels)
                # Validate the largest financial commitment with uncertain effect.
                priority = cell["arpu"] * se
                checks.append((priority, i, channel, n))
            if not checks:
                break
            _, i, channel, n = max(checks)
            arm = arms[i]
            cell = cells[arm["cell"]]
            try:
                result = env.run_pilot(target_tariff=arm["target"], channel=channel,
                                       n_customers=n, **cell["filters"])
            except (RuntimeError, ValueError) as exc:
                arm["failed_channels"].add(channel)
                self.report["warnings"].append(str(exc))
                continue
            actual, ratio = int(result["n_customers"]), float(result["observed_lift_ratio"])
            used = initial_contacts - int(env.remaining_contacts)
            spent = initial_budget - float(env.remaining_budget)
            if actual <= 0 or not isfinite(ratio):
                arm["failed_channels"].add(channel)
                self.report["warnings"].append("Invalid confirmation observation")
                continue
            arm["channel_observations"][channel] = (actual, actual * ratio)
            cell["unexposed"] *= max(0., 1 - actual / cell["n"])
            self.report["pilots"].append({"filters": dict(cell["filters"]), "target": arm["target"],
                "channel": channel, "n": actual, "ratio": ratio, "cost": float(result["cost"]),
                "phase": "confirmation"})
        selected = self._select(arms, cells, channels, float(env.remaining_budget),
                                int(env.remaining_contacts), pilot_channel)
        campaigns = []
        for index, (i, channel) in enumerate(selected, 1):
            arm, ch = arms[i], channels[channel]
            cell = cells[arm["cell"]]
            campaign = {"campaign_name": f"campaign_{index:02d}", **cell["filters"],
                        "target_tariff": arm["target"], "channel": channel}
            campaigns.append(campaign)
            mean, se = self._channel_estimate(arm, channel, channels)
            self.report["campaigns"].append({**campaign, "contacts": cell["n"],
                "cost": cell["n"]*ch["cost"], "estimated_ratio": mean,
                "uncertainty": se, "pilot_samples": arm["samples"],
                "channel_confirmed": channel in arm["channel_observations"]})
        self.report.update(pilot_cost=spent, pilot_contacts=used,
                           final_cost=sum(c["cost"] for c in self.report["campaigns"]),
                           final_contacts=sum(c["contacts"] for c in self.report["campaigns"]),
                           runtime_seconds=round(time.monotonic()-started, 3))
        return campaigns

    def _select(self, arms, cells, channels, available_budget, available_contacts,
                pilot_channel, provisional=False):
        # One campaign per disjoint cell. Only observed arms are eligible unless
        # all experiments fail or appear negative (mandatory minimum fallback).
        budget, contacts = available_budget, available_contacts
        options = []
        for i, arm in enumerate(arms):
            if not arm["samples"]:
                continue
            cell = cells[arm["cell"]]
            # Pilot IDs are not public. A population-level exposure adjustment
            # avoids claiming all future uplift as new after pilot contacts.
            exposure = 1 - cell["unexposed"]
            for channel, ch in channels.items():
                if channel in arm["failed_channels"]:
                    continue
                if (not provisional and ch["cost"] > channels[pilot_channel]["cost"]
                        and channel not in arm["channel_observations"]):
                    continue
                mean, se = self._channel_estimate(arm, channel, channels)
                lower = mean - .75 * se
                channel_cost = cell["n"] * ch["cost"]
                gain = lower * cell["arpu"] * (1-exposure) - channel_cost
                if gain > 0 and channel_cost <= budget and cell["n"] <= contacts:
                    burden = cell["n"] / max(contacts, 1) + channel_cost / max(budget, 1)
                    options.append((gain / burden, gain, i, channel, channel_cost))
        selected, used_cells = [], set()
        for _, gain, i, channel, channel_cost in sorted(options, reverse=True):
            arm = arms[i]
            cell = cells[arm["cell"]]
            if arm["cell"] in used_cells or cell["n"] > contacts or channel_cost > budget:
                continue
            selected.append((i, channel))
            used_cells.add(arm["cell"])
            budget -= channel_cost
            contacts -= cell["n"]
            if len(selected) == 10:
                break
        if not selected:
            # Minimum-one requirement: choose a feasible least-risk small cell,
            # with sampled evidence preferred. It may still lose money.
            fallback = []
            for i, arm in enumerate(arms):
                cell = cells[arm["cell"]]
                mean, se = self._estimate(arm)
                for channel, ch in channels.items():
                    if ch["cost"] > channels[pilot_channel]["cost"]:
                        continue
                    expense = cell["n"] * ch["cost"]
                    if cell["n"] <= contacts and expense <= budget:
                        gain = (mean-se) * ch["multiplier"] * cell["arpu"] - expense
                        fallback.append((bool(arm["samples"]), gain, -cell["n"], i, channel))
            if fallback:
                *_, i, channel = max(fallback)
                selected = [(i, channel)]
                if not provisional:
                    self.report["warnings"].append("Minimum-one fallback: no conservative positive plan")
        # Spend remaining money on positive marginal channel improvements.
        # A free channel's high gain/resource ratio must not prevent upgrades
        # once audience selection is complete. Recompute after every upgrade.
        budget = available_budget - sum(
            cells[arms[i]["cell"]]["n"] * channels[ch]["cost"] for i, ch in selected)
        while selected:
            upgrades = []
            for position, (i, current_channel) in enumerate(selected):
                arm = arms[i]
                cell = cells[arm["cell"]]
                exposure = 1 - cell["unexposed"]
                old_mean, old_se = self._channel_estimate(arm, current_channel, channels)
                old_lower = old_mean - .75 * old_se
                old = channels[current_channel]
                for channel, ch in channels.items():
                    if channel in arm["failed_channels"]:
                        continue
                    if (not provisional and ch["cost"] > channels[pilot_channel]["cost"]
                            and channel not in arm["channel_observations"]):
                        continue
                    mean, se = self._channel_estimate(arm, channel, channels)
                    extra_cost = (ch["cost"] - old["cost"]) * cell["n"]
                    extra_gain = ((mean - .75 * se) - old_lower) * cell["arpu"] * (1-exposure) - extra_cost
                    if extra_cost > 0 and extra_cost <= budget and extra_gain > 0:
                        upgrades.append((extra_gain/extra_cost, position, channel, extra_cost))
            if not upgrades:
                break
            _, position, channel, extra_cost = max(upgrades)
            selected[position] = (selected[position][0], channel)
            budget -= extra_cost
        return selected
