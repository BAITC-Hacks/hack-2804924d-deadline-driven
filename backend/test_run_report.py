import csv
import io
import json
import math
import unittest

from agent import Agent
from local_eval import evaluate_agent
from make_submission import build_submission
from run_report import build_run_report


class ReportTests(unittest.TestCase):
    def test_matches_evaluator_and_submission(self):
        class CountingAgent(Agent):
            calls = 0
            def act(self, env):
                self.calls += 1
                return super().act(env)
        agent = CountingAgent()
        report = build_run_report(agent, seed=42)
        self.assertEqual(agent.calls, 1)
        expected = evaluate_agent(Agent(), seed=42, verbose=False)
        for key in ('net_arpu_gain', 'total_cost', 'total_contacts', 'unique_customers_targeted'):
            self.assertTrue(math.isclose(report['metrics'][key], expected[key], rel_tol=1e-12))
        self.assertEqual(report['campaigns'], json.loads(build_submission(Agent(), seed=42).to_json(orient='records')))
        self.assertEqual(report['metrics']['remaining_budget'], 100000 - expected['total_cost'])
        self.assertEqual(len(report['pilots']), expected['n_pilots'])
        json.dumps(report, allow_nan=False)
        import api
        api.runs['test'] = {'status': 'completed', 'result': report, 'error': None}
        response = api.download_submission('test')
        rows = list(csv.DictReader(io.StringIO(response.body.decode())))
        self.assertEqual(len(rows), report['campaign_count'])
        self.assertEqual(rows[0]['campaign_name'], report['campaigns'][0]['campaign_name'])

    def test_empty_and_free_campaign_json(self):
        class EmptyAgent:
            def act(self, env):
                return []
        report = build_run_report(EmptyAgent())
        self.assertEqual(report['metrics']['total_cost'], 0)
        self.assertIsNone(report['metrics']['roi'])
        self.assertEqual(report['metrics']['remaining_budget'], 100000)
        json.dumps(report, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
