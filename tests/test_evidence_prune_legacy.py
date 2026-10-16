"""Legacy cleanup regressions on disposable files; no simulations or providers."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from scripts import evidence_prune as prune


class LegacyPruneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / 'run'
        self.root.mkdir()
        (self.root / 'RUN_META.json').write_text(json.dumps({'class': 'dev', 'pr': 1,
                                                            'retrospective': True}))
        (self.root / 'frame.jpg').write_bytes(b'frame')
        old = time.time() - 8 * 86400
        os.utime(self.root / 'frame.jpg', (old, old))

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_requires_opt_in_age_and_process_check_and_records_basis(self):
        self.assertIn('skipped', prune.plan(self.root, 1))
        records = self.root.parent / 'records'
        with mock.patch.object(prune, 'refuse_if_in_use', side_effect=prune.Refused('busy')):
            with self.assertRaises(prune.Refused):
                prune.plan(self.root, 1, allow_legacy_completed=True)
        with mock.patch.object(prune, 'refuse_if_in_use'), \
                mock.patch.object(prune, 'pr_info', return_value={'number': 1, 'state': 'MERGED'}), \
                mock.patch.object(prune.sys, 'platform', 'linux'):
            row = prune.execute(self.root, 1, records, allow_legacy_completed=True)
        self.assertEqual(row['bytes'], 5)
        receipt = json.loads(next(records.glob('*.json')).read_text())
        self.assertIn('retrospective:true', receipt['completion_basis'])
        self.assertFalse((self.root / 'EXIT').exists())
        (self.root / 'new.jpg').write_bytes(b'new')
        self.assertIn('skipped', prune.plan(self.root, 1, allow_legacy_completed=True))

    def test_nested_ownership_different_pr_parent_keep_and_protected_class(self):
        (self.root / 'EXIT').write_text('0')
        (self.root / 'old-trace.json.zst').write_bytes(b'old')
        (self.root / 'COMPRESSED.jsonl').write_text(json.dumps({
            'compressed': 'old-trace.json.zst', 'verified': True}) + '\n')
        child = self.root / 'nested'
        child.mkdir()
        (child / 'RUN_META.json').write_text('{"class":"dev","pr":2}')
        (child / 'EXIT').write_text('1')
        (child / 'frame.jpg').write_bytes(b'child')
        self.assertEqual([r['path'] for r in prune.plan(self.root, 1)['candidates']], ['frame.jpg'])
        self.assertEqual(prune.plan(self.root, 1)['unknown_original_sizes'], ['old-trace.json.zst'])
        self.assertEqual(prune.plan(child, 2)['bytes'], 5)
        (self.root / 'RUN_META.json').write_text('{"class":"dev","pr":1,"keep":["nested"]}')
        self.assertEqual(prune.plan(child, 2)['bytes'], 0)
        (self.root / 'RUN_META.json').write_text('{"class":"study","pr":1}')
        self.assertIn('protected parent', prune.plan(child, 2)['skipped'])

    def test_active_recent_and_prless_age_are_preserved(self):
        for meta in ({'active': True}, {'in_use': True}):
            (self.root / 'RUN_META.json').write_text(json.dumps({'class': 'dev', 'pr': 1, **meta}))
            self.assertIn('skipped', prune.plan(self.root, 1, allow_legacy_completed=True))
        (self.root / 'RUN_META.json').write_text('{"class":"dev","pr":null}')
        young = time.time() - 2 * 86400
        os.utime(self.root / 'frame.jpg', (young, young))
        with mock.patch.object(prune, 'refuse_if_in_use'):
            self.assertIn('7 days', prune.plan(self.root, None, allow_legacy_completed=True)['skipped'])
        (self.root / '.TEST_IN_USE').touch()
        self.assertIn('skipped', prune.plan(self.root, None, allow_legacy_completed=True))
