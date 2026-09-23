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
            h = h.loc[(before > 0) & (after >= 0) & np.isfinite(before) & np.isfinite(after)].copy()
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

    def _cells(self, profile, max_size=5000):
        cells = []
        for (current, arpu), group in profile.groupby(["current_tariff", "arpu_segment"], observed=True, sort=True):
            filters = {"filter_current_tariff": str(current), "filter_arpu_segment": str(arpu)}
            pieces = [(filters, group)]
            # Do not silently truncate: every selected audience is expressible
            # with the SDK's public filters.
            for column in ("data_segment", "call_segment"):
                refined = []
                for f, g in pieces:
                    if len(g) <= max_size:
                        refined.append((f, g))
                    else:
                        refined.extend((dict(f, **{"filter_" + column: str(v)}), sub)
                                       for v, sub in g.groupby(column, observed=True, sort=True))
                pieces = refined
            for f, g in pieces:
                if 1 <= len(g) <= max_size:
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

    @staticmethod
    def _resources(env):
        budget = float(env.remaining_budget)
        contacts, pilots = float(env.remaining_contacts), float(env.pilots_left)
        if (not all(isfinite(v) and v >= 0 for v in (budget, contacts, pilots))
                or not contacts.is_integer() or not pilots.is_integer()):
            raise ValueError("Environment resource counters must be finite and nonnegative")
        return budget, int(contacts), int(pilots)

    @staticmethod
    def _pilot_observation(result, requested):
        if not isinstance(result, dict):
            raise ValueError("Pilot must return a dictionary")
        count = float(result["n_customers"])
        ratio, cost = float(result["observed_lift_ratio"]), float(result["cost"])
        if (not all(isfinite(v) for v in (count, ratio, cost)) or not count.is_integer()
                or not 1 <= count <= requested or cost < 0):
            raise ValueError("Pilot returned invalid count, effect or cost")
        return int(count), ratio, cost

    def _complete_report(self, env, initial_budget, initial_contacts, started):
        budget, contacts, _ = self._resources(env)
        final_cost = sum(c["cost"] for c in self.report["campaigns"])
        final_contacts = sum(c["contacts"] for c in self.report["campaigns"])
        self.report.update(pilot_cost=initial_budget-budget,
                           pilot_contacts=initial_contacts-contacts,
                           final_cost=final_cost, final_contacts=final_contacts,
                           runtime_seconds=round(time.monotonic()-started, 3),
                           estimates_are_forecasts=True)
        self.report["resources"] = {
            "initial_budget": initial_budget, "initial_contacts": initial_contacts,
            "budget_after_pilots": budget, "contacts_after_pilots": contacts,
            "budget_after_plan": budget-final_cost,
            "contacts_after_plan": contacts-final_contacts,
        }
        self.report["requirements"] = {
            "has_successful_pilot": bool(self.report["pilots"]),
            "has_final_campaign": bool(self.report["campaigns"]),
            "within_limits": (final_cost <= budget and final_contacts <= contacts
                              and len(self.report["campaigns"]) <= 10
                              and all(c["contacts"] <= 5000 for c in self.report["campaigns"])),
        }

    def act(self, env):
        started = time.monotonic()
        self.report = {"pilots": [], "warnings": [], "campaigns": [], "pilot_errors": []}
        initial_budget, initial_contacts, available_pilots = self._resources(env)
        profile = env.customer_profile
        required = {"ID_NUMBER", "current_tariff", "arpu_segment", "data_segment", "call_segment", "predicted_arpu"}
        if not required.issubset(profile.columns):
            raise ValueError("Missing profile columns: " + str(sorted(required - set(profile.columns))))
        if (profile.ID_NUMBER.isna().any() or profile.ID_NUMBER.duplicated().any()
                or not np.isfinite(profile.predicted_arpu).all() or (profile.predicted_arpu < 0).any()):
            raise ValueError("Profile contains invalid IDs or ARPU")
        tariffs = sorted(str(t) for t in env.tariffs.tariff_plan_code)
        channels = {str(k): {"cost": float(v["cost_per_contact"]),
                             "multiplier": float(v["conversion_multiplier"])}
                    for k, v in env.channels.items()}
        if not channels or any(not isfinite(v["cost"]) or not isfinite(v["multiplier"])
               or v["cost"] < 0 or v["multiplier"] <= 0 for v in channels.values()):
            raise ValueError("Invalid channel parameters")
        # Prefer an inexpensive informative channel, adapting to available money.
        affordable = [k for k in channels if channels[k]["cost"] * 150 <= env.remaining_budget * .25]
        if not affordable:
            affordable = [min(channels, key=lambda k: channels[k]["cost"])]
        pilot_channel = max(affordable, key=lambda k: channels[k]["multiplier"] ** 2 / (1 + channels[k]["cost"] / 20))
        multiplier = channels[pilot_channel]["multiplier"]
        cost = channels[pilot_channel]["cost"]
        final_cap = max(1, initial_contacts - (10 if available_pilots > 0 else 0))
        cells = self._cells(profile, min(5000, final_cap))
        if not cells:
            cells = self._cells(profile, min(5000, max(1, initial_contacts)))
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
                             "pilot_multiplier": multiplier, "failed": False})
        if not arms:
            self.report["warnings"].append("No audience expressible within the available contact limit")
            self._complete_report(env, initial_budget, initial_contacts, started)
            return []
        # Keep enough resources for at least one FULL, filter-expressible final
        # campaign, rather than just the minimum pilot size.
        reserve_contacts = min(cells[a["cell"]]["n"] for a in arms)
        cheapest_cost = min(c["cost"] for c in channels.values())
        reserve_budget = reserve_contacts * cheapest_cost
        exploration_budget = max(0., min(.25 * initial_budget, initial_budget-reserve_budget))
        exploration_contacts = max(0, min(3000, max(10, int(.25 * initial_contacts)),
                                          initial_contacts-reserve_contacts))
        spent = used = 0
        pilot_limit = min(20, available_pilots)
        for step in range(pilot_limit):
            if time.monotonic() - started > 240 or env.pilots_left <= 0:
                break
            cap = min(200, exploration_contacts - used, int(env.remaining_contacts) - reserve_contacts)
            if cost:
                cap = min(cap, int(min(exploration_budget-spent, env.remaining_budget-reserve_budget) // cost))
            if cap < 10:
                break
            options = []
            per_cell = {i: sum(a["batches"] for a in arms if a["cell"] == i) for i in range(len(cells))}
            for i, arm in enumerate(arms):
                if arm["failed"]:
                    continue
                cell = cells[arm["cell"]]
                if cell["n"] < 10:
                    continue
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
            budget_before, contacts_before, _ = self._resources(env)
            try:
                result = env.run_pilot(target_tariff=arm["target"], channel=pilot_channel,
                                       n_customers=n, **cell["filters"])
                actual, ratio, reported_cost = self._pilot_observation(result, n)
                after_budget, after_contacts, _ = self._resources(env)
                if (contacts_before-after_contacts != actual
                        or abs(budget_before-after_budget-reported_cost) > 1e-6):
                    raise ValueError("Pilot response disagrees with public resource counters")
            except Exception as exc:
                # Only the external call/response boundary is guarded. Do not
                # mask implementation errors in estimation or planning.
                arm["failed"] = True
                message = f"{type(exc).__name__}: {exc}"
                self.report["warnings"].append(message)
                self.report["pilot_errors"].append({"target": arm["target"],
                    "filters": dict(cell["filters"]), "error": message})
                continue
            finally:
                after_budget, after_contacts, _ = self._resources(env)
                used = initial_contacts - after_contacts
                spent = initial_budget - after_budget
                consumed = max(0, contacts_before-after_contacts)
                cell["unexposed"] *= max(0., 1-consumed/cell["n"])
            arm["samples"] += actual
            arm["weighted_sum"] += actual * ratio / multiplier
            arm["batches"] += 1
            self.report["pilots"].append({"filters": dict(cell["filters"]), "target": arm["target"],
                                           "channel": pilot_channel, "n": actual, "ratio": ratio,
                                           "cost": reported_cost})

        # One campaign per disjoint cell. Only observed arms are eligible unless
        # all experiments fail or appear negative (mandatory minimum fallback).
        budget, contacts = float(env.remaining_budget), int(env.remaining_contacts)
        options = []
        for i, arm in enumerate(arms):
            if not arm["samples"]:
                continue
            cell = cells[arm["cell"]]
            mean, se = self._estimate(arm)
            lower = mean - .75 * se
            # Pilot IDs are not public. A population-level exposure adjustment
            # avoids claiming all future uplift as new after pilot contacts.
            exposure = 1-cell["unexposed"]
            for channel, ch in channels.items():
                channel_cost = cell["n"] * ch["cost"]
                gain = lower * ch["multiplier"] * cell["arpu"] * (1-exposure) - channel_cost
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
        used_fallback = not selected
        if not selected:
            # Minimum-one requirement: choose a feasible least-risk small cell,
            # with sampled evidence preferred. It may still lose money.
            fallback = []
            for i, arm in enumerate(arms):
                cell = cells[arm["cell"]]
                mean, se = self._estimate(arm)
                for channel, ch in channels.items():
                    expense = cell["n"] * ch["cost"]
                    if cell["n"] <= contacts and expense <= budget:
                        gain = (mean-se) * ch["multiplier"] * cell["arpu"] - expense
                        fallback.append((bool(arm["samples"]), gain, -cell["n"], i, channel))
            if fallback:
                *_, i, channel = max(fallback)
                selected = [(i, channel)]
                self.report["warnings"].append("Minimum-one fallback: no conservative positive plan")
        # Spend remaining money on positive marginal channel improvements.
        # A free channel's high gain/resource ratio must not prevent upgrades
        # once audience selection is complete. Recompute after every upgrade.
        budget = float(env.remaining_budget) - sum(
            cells[arms[i]["cell"]]["n"] * channels[ch]["cost"] for i, ch in selected)
        while selected:
            upgrades = []
            for position, (i, current_channel) in enumerate(selected):
                arm = arms[i]
                cell = cells[arm["cell"]]
                mean, se = self._estimate(arm)
                exposure = 1-cell["unexposed"]
                reliable = max(0., mean - .75 * se) * cell["arpu"] * (1-exposure)
                old = channels[current_channel]
                for channel, ch in channels.items():
                    extra_cost = (ch["cost"] - old["cost"]) * cell["n"]
                    extra_gain = reliable * (ch["multiplier"] - old["multiplier"]) - extra_cost
                    if extra_cost > 0 and extra_cost <= budget and extra_gain > 0:
                        upgrades.append((extra_gain/extra_cost, position, channel, extra_cost))
            if not upgrades:
                break
            _, position, channel, extra_cost = max(upgrades)
            selected[position] = (selected[position][0], channel)
            budget -= extra_cost
        campaigns = []
        for index, (i, channel) in enumerate(selected, 1):
            arm, ch = arms[i], channels[channel]
            cell = cells[arm["cell"]]
            campaign = {"campaign_name": f"campaign_{index:02d}", **cell["filters"],
                        "target_tariff": arm["target"], "channel": channel}
            campaigns.append(campaign)
            mean, se = self._estimate(arm)
            self.report["campaigns"].append({**campaign, "contacts": cell["n"],
                "cost": cell["n"]*ch["cost"], "estimated_ratio": mean*ch["multiplier"],
                "uncertainty": se*ch["multiplier"], "pilot_samples": arm["samples"],
                "estimate_basis": "direct_pilot" if channel == pilot_channel else "channel_multiplier",
                "channel_confirmed": channel == pilot_channel,
                "estimated_unexposed_fraction": cell["unexposed"],
                "selection_reason": "Minimum-one fallback; estimated loss is possible" if used_fallback
                    else "Positive risk-adjusted estimate within remaining resources"})
        if not self.report["pilots"]:
            self.report["warnings"].append("No successful pilot: submission requirement not satisfied")
        if not campaigns:
            self.report["warnings"].append("No feasible final campaign with the remaining resources")
        self._complete_report(env, initial_budget, initial_contacts, started)
        return campaigns
