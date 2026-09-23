"""Tests use a public-interface fake; no access to scoring internals."""
import unittest
import pandas as pd
from agent_confirmed import Agent


class PublicEnv:
    def __init__(self, negative=False, errors=False, bad_channels=False):
        self.customer_profile = pd.DataFrame([
            {"ID_NUMBER": i, "current_tariff": "tariff_1" if i < 2000 else "tariff_2",
             "arpu_segment": "HIGH", "data_segment": "HEAVY", "call_segment": "HIGH",
             "predicted_arpu": 8000.} for i in range(4000)])
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
        self.bad_channels = bad_channels

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
        ratio *= self.channels[channel]["conversion_multiplier"]
        if self.bad_channels and channel in ("call", "digital_ads"):
            ratio = -.5
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

    def test_unprofitable_expensive_channel_is_rejected(self):
        env, agent = PublicEnv(bad_channels=True), Agent()
        plan = agent.act(env)
        self.check_plan(env, agent, plan)
        confirmations = [p for p in agent.report["pilots"] if p["phase"] == "confirmation"]
        self.assertTrue(confirmations, "Test must actually exercise channel validation")
        self.assertTrue(all(p["ratio"] < 0 for p in confirmations))
        self.assertTrue(all(p["channel"] in ("push", "sms") for p in plan))

    def test_expensive_final_channels_have_direct_observations(self):
        env, agent = PublicEnv(), Agent()
        agent.act(env)
        expensive = [c for c in agent.report["campaigns"] if c["channel"] in ("call", "digital_ads")]
        self.assertTrue(expensive, "Test must exercise a paid-channel upgrade")
        self.assertTrue(all(c["channel_confirmed"] for c in expensive))
        self.assertGreaterEqual(env.remaining_budget, 0)
        self.assertGreaterEqual(env.remaining_contacts, 0)

    def test_oversized_audience_is_split_by_real_filters(self):
        env, agent = PublicEnv(), Agent()
        one = env.customer_profile.iloc[:2000].copy()
        combined = pd.concat([one.assign(ID_NUMBER=one.ID_NUMBER+i*2000,
                                         data_segment=segment)
                              for i, segment in enumerate(("HEAVY", "LITE", "NON_USER"))])
        cells = agent._cells(combined)
        self.assertEqual(sum(c["n"] for c in cells), 6000)
        self.assertTrue(all(c["n"] <= 5000 for c in cells))
        self.assertEqual(len({c["filters"]["filter_data_segment"] for c in cells}), 3)


if __name__ == "__main__":
    unittest.main()
