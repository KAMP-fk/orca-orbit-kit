"""Persistence regressions with concurrent publishers and injected IO failures."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents/team/lib'))
import state_io
from task_session import save


class StateIOTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'record.json'

    def assert_no_temporary_files(self):
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ['record.json'])

    def test_competing_receipts_publish_once_without_replacing_the_winner(self):
        def publish(number):
            try:
                state_io.publish_json(self.path, {'writer': number, 'body': '返答' * 100})
                return number
            except FileExistsError:
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            winners = [value for value in pool.map(publish, range(32)) if value is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(json.loads(self.path.read_text()), {'writer': winners[0], 'body': '返答' * 100})
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assert_no_temporary_files()

    def test_concurrent_session_updates_are_complete_and_do_not_share_a_temporary_path(self):
        save(self.path, {'writer': -1, 'body': '記録' * 1000})
        barrier = threading.Barrier(8)

        def replace(number):
            barrier.wait(timeout=5)
            for _ in range(8):
                save(self.path, {'writer': number, 'body': '記録' * 1000})
                value = json.loads(self.path.read_text())
                self.assertEqual(value['body'], '記録' * 1000)
                self.assertIn(value['writer'], range(-1, 8))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(replace, range(8)))
        raw = self.path.read_text()
        self.assertIn('記録', raw)
        self.assertFalse(raw.endswith('\n'))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assert_no_temporary_files()

    def test_serialization_failure_preserves_the_old_record_and_removes_partial_output(self):
        self.path.write_bytes(b'{"writer": "original"}')
        for publish in (state_io.write_json, state_io.publish_json):
            with self.assertRaises(TypeError):
                publish(self.path, {'partial': 'text', 'invalid': object()})
            self.assertEqual(self.path.read_bytes(), b'{"writer": "original"}')
            self.assert_no_temporary_files()

    def test_replace_failure_preserves_the_old_record_and_removes_temporary_output(self):
        self.path.write_bytes(b'{"writer": "original"}')
        with patch.object(state_io.os, 'replace', side_effect=OSError('fixture replace failure')):
            with self.assertRaises(OSError):
                state_io.write_json(self.path, {'writer': 'replacement'})
        self.assertEqual(self.path.read_bytes(), b'{"writer": "original"}')
        self.assert_no_temporary_files()

    def test_file_sync_failure_cannot_publish_either_kind_of_record(self):
        with patch.object(state_io.os, 'fsync', side_effect=OSError('fixture sync failure')):
            for publish in (state_io.write_json, state_io.publish_json):
                with self.assertRaises(OSError):
                    publish(self.path, {'writer': 'unconfirmed'})
                self.assertEqual(list(self.root.iterdir()), [])

    def test_directory_sync_occurs_after_publication_and_failures_are_reported(self):
        original_sync = os.fsync
        synced = []

        def sync(fd):
            is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
            synced.append(is_directory)
            if is_directory:
                self.assertEqual(json.loads(self.path.read_text()), {'writer': 'persisted'})
                raise OSError('fixture directory sync failure')
            original_sync(fd)

        with patch.object(state_io.os, 'fsync', side_effect=sync):
            with self.assertRaises(OSError):
                state_io.write_json(self.path, {'writer': 'persisted'}, sync_directory=True)
        self.assertEqual(synced, [False, True])
        self.assert_no_temporary_files()

    def test_callers_own_directory_creation(self):
        missing = self.root / 'absent'
        for publish in (state_io.write_json, state_io.publish_json):
            with self.assertRaises(FileNotFoundError):
                publish(missing / 'record.json', {'writer': 1})
            self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
