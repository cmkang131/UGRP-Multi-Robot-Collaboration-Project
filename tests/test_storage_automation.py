"""Retention regressions use disposable data; never inspect or delete actual evidence."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
from scripts import storage_automation as auto
from scripts import evidence_prune as prune
from scripts import storage_common as common


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.run = self.base / 's3fix24-batch-r1'
        self.run.mkdir()
        (self.run / 'EXIT').write_text('0')
        (self.run / 'frame.jpg').write_bytes(b'raw')
        self.catalog = {'repo': auto.REPO, 'fetched_at': time.time(), 'prs': [
            {'number': 416, 'state': 'MERGED', 'headRefName': 'codex/s3-no-prior-smoke', 'body': ''}]}

    def tearDown(self):
        self.tmp.cleanup()

    def old(self, days=8):
        stamp = time.time() - days * 86400
        for p in common.files(self.run):
            os.utime(p, (stamp, stamp))

    def meta(self, **kwargs):
        data = {'class': 'dev', 'pr': 416, 'keep': [], **kwargs}
        (self.run / 'RUN_META.json').write_text(json.dumps(data))

    def test_prefix_and_exact_pr_body_and_ambiguous_fallback(self):
        self.assertEqual(auto.infer_meta(self.run, self.catalog)['pr'], 416)
        (self.base / 'unknown').mkdir()
        self.assertEqual(auto.infer_meta(self.base / 'unknown', self.catalog)['pr'], None)
        self.catalog['prs'].append({'number': 432, 'state': 'OPEN', 'headRefName': 'codex/view',
                                  'body': 'outputs/s3fix24-batch-r1'})
        self.assertEqual(auto.infer_meta(self.run, self.catalog)['pr'], 432)

    def test_backfill_preserves_existing_class_inherits_parent_and_does_not_invent_exit(self):
        self.meta(**{'class': 'milestone'})
        child = self.run / 'nested'
        child.mkdir()
        (child / 'EXIT').write_text('1')
        rows = auto.backfill(self.base, self.catalog, True)
        self.assertEqual(json.loads((self.run / 'RUN_META.json').read_text())['class'], 'milestone')
        data = json.loads((child / 'RUN_META.json').read_text())
        self.assertEqual((data['class'], data['pr']), ('milestone', 416))
        unfinished = self.base / 'unknown'
        unfinished.mkdir()
        auto.backfill(self.base, self.catalog, True)
        self.assertFalse((unfinished / 'EXIT').exists())

    def test_recent_housekeeping_does_not_restart_seven_day_age(self):
        self.old()
        self.meta(pr=None)
        self.assertEqual(prune.plan(self.run, None, idle_hours=24)['bytes'], 3)
        (self.run / 'ALL-hashes.tsv').write_text('housekeeping')
        self.assertEqual(prune.plan(self.run, None, idle_hours=24)['bytes'], 3)
        (self.run / 'frame.jpg').write_bytes(b'new')
        self.assertEqual(prune.plan(self.run, None, idle_hours=24)['bytes'], 0)

    def test_stale_catalog_and_same_branch_open_refuse(self):
        self.catalog['fetched_at'] -= 301
        with self.assertRaises(ValueError):
            auto.catalog_pr(self.catalog, 416)
        self.catalog['fetched_at'] = time.time()
        self.catalog['prs'].append({**self.catalog['prs'][0], 'number': 417, 'state': 'OPEN'})
        with self.assertRaises(ValueError):
            auto.catalog_pr(self.catalog, 416)

    def test_orphan_branch_open_preserved(self):
        self.old()
        self.meta(pr=None, branch='codex/s3-no-prior-smoke')
        self.catalog['prs'][0]['state'] = 'OPEN'
        self.assertIn('open PR', auto.eligible(self.run, self.catalog, None))

    def test_24h_and_representative_video_with_data_survive(self):
        self.meta()
        self.assertEqual(prune.plan(self.run, 416, idle_hours=24)['bytes'], 0)
        self.old(2)
        (self.run / 'overview.mp4').write_bytes(b'mp4')
        (self.run / 'trace.jsonl').write_bytes(b'x' * 100000)
        (self.run / 'video-data.npz').write_bytes(b'npz')
        self.old(2)
        row = prune.plan(self.run, 416, idle_hours=24)
        self.assertEqual([r['path'] for r in row['candidates']], ['frame.jpg'])

    def test_prless_execute_records_hash_before_delete_and_protected_class(self):
        self.old()
        self.meta(pr=None)
        records = self.base / 'records'
        with mock.patch.object(prune, 'refuse_if_in_use'), mock.patch.object(prune.sys, 'platform', 'linux'):
            prune.execute(self.run, None, records, catalog=self.catalog, idle_hours=24)
        self.assertFalse((self.run / 'frame.jpg').exists())
        self.assertIn('frame.jpg', (self.run / 'ALL-hashes.tsv').read_text())
        receipt = json.loads(next(records.glob('*.json')).read_text())
        self.assertEqual(receipt['status'], 'done')
        self.meta(pr=None, **{'class': 'study'})
        self.assertIn('skipped', prune.plan(self.run, None))

    def test_pressure_stages_order_and_no_orphan_without_pressure(self):
        self.old()
        self.meta(pr=None)
        with mock.patch.object(auto, 'persistent'), mock.patch.object(auto.shutil, 'disk_usage',
                return_value=mock.Mock(free=40 * auto.GIB)):
            row = auto.maintenance(self.base, 'arm', self.catalog, self.base / 'records')
        self.assertNotIn('a_compress', [s['stage'] for s in row['stages']])
        self.assertIn('skipped', row['stages'][-1])
        with mock.patch.object(auto, 'persistent'), mock.patch.object(auto.shutil, 'disk_usage',
                return_value=mock.Mock(free=30 * auto.GIB)):
            row = auto.maintenance(self.base, 'arm', self.catalog, self.base / 'records')
        self.assertEqual([s['stage'] for s in row['stages']],
                         ['a_compress', 'b_closed_dev', 'c_prless_dev_7d'])
        self.assertTrue((self.run / 'frame.jpg').exists())

    def test_post_run_warns_and_preserves_compression_failure(self):
        self.meta()
        with mock.patch.object(auto, 'files', return_value=[mock.Mock(stat=lambda: mock.Mock(st_size=301*2**20))]), \
                mock.patch.object(auto, 'compress_run', side_effect=ValueError('busy')):
            row = auto.post_run(self.run)
        self.assertTrue(row['over_300mb'])
        self.assertEqual(row['compression_error'], 'busy')
        self.assertTrue((self.run / 'frame.jpg').exists())

if __name__ == '__main__':
    unittest.main()
