import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from run_storage import RunStore


class StorageTests(unittest.TestCase):
    def test_completed_result_and_csv_survive_reload(self):
        import api
        from run_report import build_run_report
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(directory)
            run_id = str(uuid4())
            with patch.object(api, 'store', store), patch.object(api, 'runs', {}):
                api.runs[run_id] = dict(status='queued', result=None, error=None)
                api.execute_agent(run_id)
                expected = api.get_run_result(run_id)
                csv_before = api.download_submission(run_id).body
                api.runs = RunStore(directory).load()
                self.assertEqual(api.get_run_status(run_id)['status'], 'completed')
                self.assertEqual(api.get_run_result(run_id), expected)
                self.assertEqual(api.download_submission(run_id).body, csv_before)

    def test_interrupted_and_corrupt_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(directory)
            ids = [str(uuid4()), str(uuid4())]
            for run_id, status in zip(ids, ['queued', 'running']):
                store.save(run_id, dict(status=status, result=None, error=None))
            (Path(directory) / f'{uuid4()}.json').write_text('{broken')
            with self.assertLogs(level='ERROR'):
                records = store.load()
            for run_id in ids:
                self.assertEqual(records[run_id]['status'], 'failed')
                self.assertTrue(records[run_id]['error'])

    def test_failed_write_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(directory)
            run_id = str(uuid4())
            record = dict(status='failed', result=None, error='test')
            store.save(run_id, record)
            with patch('run_storage.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    store.save(run_id, dict(status='completed', result={}, error=None))
            self.assertEqual(store.load()[run_id], record)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
