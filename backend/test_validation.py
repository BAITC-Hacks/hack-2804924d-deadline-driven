import copy
import unittest
from agent import Agent
from test_agent import PublicEnv
from integration import run_agent
from validation import validate_plan


class ValidationTests(unittest.TestCase):
    def test_integration_is_one_run(self):
        env = PublicEnv()
        result = run_agent(env)
        self.assertEqual(len(env.pilot_history), len(result["report"]["pilots"]))
        self.assertTrue(result["validation"]["disjoint_audiences"])

    def test_unknown_tariff_not_silently_dropped(self):
        env = PublicEnv()
        with self.assertRaisesRegex(ValueError, "Unknown target"):
            validate_plan(env, [{"target_tariff":"missing", "channel":"push"}])

    def test_overlap_is_detected(self):
        env = PublicEnv()
        campaign = {"target_tariff":"tariff_3", "channel":"push"}
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_plan(env, [campaign, campaign])

    def test_wrong_reported_cost_is_detected(self):
        env, agent = PublicEnv(), Agent()
        plan = agent.act(env)
        report = copy.deepcopy(agent.report)
        report["final_cost"] += 1
        with self.assertRaisesRegex(ValueError, "totals"):
            validate_plan(env, plan, report)

    def test_resource_matrix(self):
        # Different public resource limits; no hidden effect tables involved.
        for contacts in (320, 600, 15000):
            for budget in (0, 80, 400, 100000):
                with self.subTest(contacts=contacts, budget=budget):
                    env, agent = PublicEnv(), Agent()
                    env.remaining_contacts, env.remaining_budget = contacts, budget
                    plan = agent.act(env)
                    validate_plan(env, plan, agent.report)


if __name__ == "__main__":
    unittest.main()
