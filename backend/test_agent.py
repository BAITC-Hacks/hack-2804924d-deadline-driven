"""Tests use a public-interface fake; no access to scoring internals."""
import unittest
import json
from unittest.mock import patch
from pathlib import Path
import tempfile
import pandas as pd
from agent import Agent


class PublicEnv:
    def __init__(self, negative=False, errors=False):
        self.customer_profile = pd.DataFrame([
            {"ID_NUMBER": i, "current_tariff": "tariff_1" if i < 300 else "tariff_2",
             "arpu_segment": "HIGH", "data_segment": "HEAVY", "call_segment": "HIGH",
             "predicted_arpu": 8000.} for i in range(600)])
        self.tariffs = pd.DataFrame({"tariff_plan_code": ["tariff_1", "tariff_2", "tariff_3"]})
        self.channels = {"push": {"cost_per_contact": 0, "conversion_multiplier": .5},
                         "sms": {"cost_per_contact": 4, "conversion_multiplier": .65},
                         "digital_ads": {"cost_per_contact": 22, "conversion_multiplier": .85},
                         "call": {"cost_per_contact": 160, "conversion_multiplier": 1.2}}
        self.remaining_budget = 100000
        self.remaining_contacts = 15000
        self.pilots_left = 20
        self.pilot_history = []
        self.negative, self.errors = negative, errors

    def run_pilot(self, target_tariff, channel, n_customers, **filters):
        if self.errors:
            raise RuntimeError("temporary pilot failure")
        assert 10 <= n_customers <= 200
        cost = n_customers*self.channels[channel]["cost_per_contact"]
        assert cost <= self.remaining_budget and n_customers <= self.remaining_contacts
        self.remaining_budget -= cost
        self.remaining_contacts -= n_customers
        self.pilots_left -= 1
        ratio = (-.4 if self.negative else (.4 if target_tariff == "tariff_3" else .1))
        result = {"n_customers": n_customers, "observed_lift_ratio": ratio,
                  "cost": cost, "remaining_budget": self.remaining_budget,
                  "remaining_contacts": self.remaining_contacts}
        self.pilot_history.append(result)
        return result


class AgentTests(unittest.TestCase):
    def check_plan(self, env, agent, plan):
        self.assertTrue(1 <= len(plan) <= 10)
        self.assertLessEqual(agent.report["final_cost"], env.remaining_budget)
        self.assertLessEqual(agent.report["final_contacts"], env.remaining_contacts)
        self.assertEqual(len({p["filter_current_tariff"] for p in plan}), len(plan))
        for p in plan:
            self.assertNotEqual(p["target_tariff"], p["filter_current_tariff"])

    def test_profitable_pilots_and_channel_upgrade(self):
        env, agent = PublicEnv(), Agent()
        plan = agent.act(env)
        self.check_plan(env, agent, plan)
        self.assertGreater(len(env.pilot_history), 0)
        self.assertGreater(agent.report["final_cost"], 0)

    def test_negative_pilots_still_produce_minimum_valid_plan(self):
        env, agent = PublicEnv(negative=True), Agent()
        plan = agent.act(env)
        self.check_plan(env, agent, plan)
        self.assertTrue(agent.report["warnings"])

    def test_failed_pilots_are_bounded(self):
        env, agent = PublicEnv(errors=True), Agent()
        plan = agent.act(env)
        self.check_plan(env, agent, plan)
        self.assertEqual(agent.report["pilot_contacts"], 0)

    def test_reuse_does_not_leak_state(self):
        agent = Agent()
        first = agent.act(PublicEnv())
        second = agent.act(PublicEnv())
        self.assertEqual(first, second)

    def test_dashboard_report_is_serializable_and_balanced(self):
        env, agent = PublicEnv(), Agent()
        agent.act(env)
        json.dumps(agent.report, allow_nan=False)
        r = agent.report["resources"]
        self.assertEqual(r["budget_after_plan"], r["initial_budget"]
                         - agent.report["pilot_cost"] - agent.report["final_cost"])
        self.assertEqual(r["contacts_after_plan"], r["initial_contacts"]
                         - agent.report["pilot_contacts"] - agent.report["final_contacts"])
        self.assertTrue(agent.report["estimates_are_forecasts"])

    def test_reserves_full_campaign_on_small_contact_balance(self):
        env, agent = PublicEnv(), Agent()
        env.remaining_contacts = 320
        plan = agent.act(env)
        self.check_plan(env, agent, plan)
        self.assertTrue(env.pilot_history)
        self.assertLessEqual(agent.report["pilot_contacts"], 20)
        self.assertTrue(all(agent.report["requirements"].values()))

    def test_segments_split_to_fit_pilot_and_final_plan(self):
        env, agent = PublicEnv(), Agent()
        env.customer_profile = env.customer_profile.iloc[:300].copy()
        env.customer_profile.loc[env.customer_profile.index[:150], "data_segment"] = "LITE"
        env.remaining_contacts = 300
        plan = agent.act(env)
        self.assertTrue(plan)
        self.assertTrue(env.pilot_history)
        self.assertLessEqual(agent.report["final_contacts"], env.remaining_contacts)
        self.assertTrue(all("filter_data_segment" in c for c in plan))

    def test_malformed_pilot_keeps_actual_spend_in_report(self):
        env, agent = PublicEnv(), Agent()
        real_pilot = env.run_pilot
        def malformed(**kwargs):
            result = real_pilot(**kwargs)
            del result["observed_lift_ratio"]
            return result
        env.run_pilot = malformed
        plan = agent.act(env)
        self.check_plan(env, agent, plan)
        self.assertEqual(agent.report["pilot_cost"], 100000-env.remaining_budget)
        self.assertEqual(agent.report["pilot_contacts"], 15000-env.remaining_contacts)
        self.assertFalse(agent.report["requirements"]["has_successful_pilot"])
        self.assertTrue(agent.report["pilot_errors"])
        json.dumps(agent.report, allow_nan=False)

    def test_pilot_timeout_does_not_crash_plan(self):
        env, agent = PublicEnv(), Agent()
        def timeout(**kwargs):
            raise TimeoutError("simulated pilot timeout")
        env.run_pilot = timeout
        plan = agent.act(env)
        self.check_plan(env, agent, plan)
        self.assertLessEqual(len(agent.report["pilot_errors"]), 20)

    def test_repeated_sampling_does_not_imply_full_unique_coverage(self):
        env, agent = PublicEnv(), Agent()
        agent.act(env)
        self.assertTrue(agent.report["campaigns"])
        for c in agent.report["campaigns"]:
            self.assertGreater(c["estimated_unexposed_fraction"], 0)
            self.assertLessEqual(c["estimated_unexposed_fraction"], 1)

    def test_zero_contacts_has_explicit_unsatisfied_requirements(self):
        env, agent = PublicEnv(), Agent()
        env.remaining_contacts = 0
        self.assertEqual(agent.act(env), [])
        self.assertFalse(agent.report["requirements"]["has_final_campaign"])
        self.assertTrue(agent.report["requirements"]["within_limits"])
        json.dumps(agent.report, allow_nan=False)

    def test_malformed_count_is_not_truncated_or_accepted(self):
        for count in (10.5, float("inf"), 201, 0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                Agent._pilot_observation({"n_customers":count,"observed_lift_ratio":.1,"cost":0}, 200)

    def test_empty_channels_fails_with_clear_message(self):
        env = PublicEnv()
        env.channels = {}
        with self.assertRaisesRegex(ValueError, "Invalid channel"):
            Agent().act(env)

    def test_history_excludes_infinite_arpu(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"history.csv"
            path.write_text("AVG_ARPU_PREV_3M,AVG_ARPU_NEXT_3M,tariff_plan_code_from,tariff_plan_code_to\n100,120,tariff_1,tariff_2\ninf,100,tariff_1,tariff_2\n100,inf,tariff_1,tariff_2\n", encoding="utf-8")
            original_read = pd.read_csv
            with patch("agent.pd.read_csv", side_effect=lambda _: original_read(path)):
                result = Agent()._history()
            self.assertEqual(result[("tariff_1","LOW","tariff_2")][1], 1)


if __name__ == "__main__":
    unittest.main()
