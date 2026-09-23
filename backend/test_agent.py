"""Tests use a public-interface fake; no access to scoring internals."""
import unittest
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


if __name__ == "__main__":
    unittest.main()
