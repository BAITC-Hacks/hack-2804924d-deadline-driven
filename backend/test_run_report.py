import json
import os
from pathlib import Path
import unittest

from agent import Agent
from local_eval import evaluate_agent
from make_submission import build_submission
from run_report import build_run_report


BASE_DIR = Path(__file__).resolve().parent


class CountingAgent:
    def __init__(self):
        self.calls = 0
        self.agent = Agent()

    def act(self, env):
        self.calls += 1
        return self.agent.act(env)


class RunReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = CountingAgent()
        cls.result = build_run_report(
            cls.agent, data_dir=BASE_DIR / "data",
            profile_path=BASE_DIR / "customer_profile.csv", seed=42,
        )

    def test_one_run_and_json_safe_public_history(self):
        self.assertEqual(self.agent.calls, 1)
        json.dumps(self.result, allow_nan=False)
        self.assertGreater(len(self.result["pilots"]), 0)
        self.assertEqual(len(self.result["pilots"]), len(self.agent.agent.report["pilots"]))
        for pilot in self.result["pilots"]:
            self.assertNotIn("explicit_ids", pilot)
            self.assertNotIn("ID_NUMBER", pilot)

    def test_same_plan_as_submission_generator(self):
        expected = build_submission(
            Agent(), seed=42, data_dir=str(BASE_DIR / "data"),
            profile_path=str(BASE_DIR / "customer_profile.csv"),
        )
        expected = expected.astype(object).where(expected.notna(), None)
        self.assertEqual(self.result["campaigns"], expected.to_dict(orient="records"))
        self.assertEqual(self.result["campaign_count"], len(expected))

    def test_score_matches_official_local_evaluation(self):
        # The supplied CLI evaluator resolves its data relative to the cwd.
        previous = Path.cwd()
        try:
            os.chdir(BASE_DIR)
            expected = evaluate_agent(Agent(), seed=42, verbose=False)
        finally:
            os.chdir(previous)
        metrics = self.result["metrics"]
        self.assertAlmostEqual(metrics["net_arpu_gain"], expected["net_arpu_gain"])
        self.assertAlmostEqual(metrics["total_cost"], expected["total_cost"])
        self.assertEqual(len(self.result["pilots"]), expected["n_pilots"])

    def test_budget_includes_pilots_and_final_campaigns(self):
        metrics = self.result["metrics"]
        report = self.agent.agent.report
        self.assertAlmostEqual(metrics["total_cost"], report["pilot_cost"] + report["final_cost"])
        self.assertAlmostEqual(metrics["remaining_budget"], metrics["total_budget"] - metrics["total_cost"])
        self.assertGreaterEqual(metrics["remaining_budget"], 0)
        self.assertAlmostEqual(sum(p["cost"] for p in self.result["pilots"]), report["pilot_cost"])

    def test_empty_report_does_not_invent_metrics_or_pilots(self):
        class EmptyAgent:
            def act(self, env):
                return []

        result = build_run_report(
            EmptyAgent(), data_dir=BASE_DIR / "data",
            profile_path=BASE_DIR / "customer_profile.csv",
        )
        self.assertEqual(result["campaign_count"], 0)
        self.assertEqual(result["pilots"], [])
        self.assertEqual(result["metrics"]["net_arpu_gain"], 0)
        self.assertEqual(result["metrics"]["total_cost"], 0)
        self.assertEqual(result["metrics"]["remaining_budget"], result["metrics"]["total_budget"])

    def test_agent_failure_is_not_replaced_with_fake_success(self):
        class BrokenAgent:
            def act(self, env):
                raise RuntimeError("broken agent")

        with self.assertRaisesRegex(RuntimeError, "broken agent"):
            build_run_report(
                BrokenAgent(), data_dir=BASE_DIR / "data",
                profile_path=BASE_DIR / "customer_profile.csv",
            )


if __name__ == "__main__":
    unittest.main()
