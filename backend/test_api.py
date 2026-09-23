import csv
import io
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        api.runs.clear()
        self.result = {
            "environment": "mock",
            "campaign_count": 1,
            "campaigns": [{
                "campaign_name": "test_campaign",
                "filter_arpu_segment": "HIGH",
                "filter_data_segment": None,
                "filter_call_segment": None,
                "filter_current_tariff": "tariff_1",
                "target_tariff": "tariff_3",
                "channel": "sms",
            }],
        }

    def create_queued(self):
        with patch.object(api.executor, "submit") as submit:
            run_id = api.create_run()["run_id"]
            submit.assert_called_once_with(api.execute_agent, run_id)
        self.assertEqual(api.get_run_status(run_id)["status"], "queued")
        return run_id

    def test_success_and_csv_use_same_saved_result(self):
        run_id = self.create_queued()
        with patch.object(api, "calculate_result", return_value=self.result) as calculate:
            api.execute_agent(run_id)
            self.assertEqual(api.get_run_status(run_id)["status"], "completed")
            self.assertEqual(api.get_run_result(run_id), self.result)
            first = api.download_submission(run_id)
            second = api.download_submission(run_id)
            self.assertEqual(first.body, second.body)
            calculate.assert_called_once()
        reader = csv.DictReader(io.StringIO(first.body.decode("utf-8")))
        self.assertEqual(reader.fieldnames, api.CAMPAIGN_COLUMNS)
        expected = {k: "" if v is None else v for k, v in self.result["campaigns"][0].items()}
        self.assertEqual(list(reader), [expected])

    def test_failure_preserves_error_and_has_no_result(self):
        run_id = self.create_queued()
        with patch.object(api, "calculate_result", side_effect=RuntimeError("test failure")):
            api.execute_agent(run_id)
        self.assertEqual(api.get_run_status(run_id)["error"], "test failure")
        self.assertEqual(api.get_run_status(run_id)["status"], "failed")
        with self.assertRaises(HTTPException) as error:
            api.get_run_result(run_id)
        self.assertEqual(error.exception.status_code, 409)

    def test_pending_result_and_csv_are_not_available(self):
        run_id = self.create_queued()
        for endpoint in (api.get_run_result, api.download_submission):
            with self.assertRaises(HTTPException) as error:
                endpoint(run_id)
            self.assertEqual(error.exception.status_code, 409)

    def test_unknown_run_returns_404(self):
        for endpoint in (api.get_run_status, api.get_run_result, api.download_submission):
            with self.assertRaises(HTTPException) as error:
                endpoint("missing")
            self.assertEqual(error.exception.status_code, 404)

    def test_data_paths_do_not_depend_on_working_directory(self):
        with patch.object(api, "build_run_report", return_value=self.result) as build:
            self.assertEqual(api.calculate_result(), self.result)
        self.assertEqual(build.call_args.kwargs["data_dir"], str(api.BASE_DIR / "data"))
        self.assertEqual(build.call_args.kwargs["profile_path"], str(api.BASE_DIR / "customer_profile.csv"))


if __name__ == "__main__":
    unittest.main()
