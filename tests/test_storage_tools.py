"""Storage loss/over-budget regressions; only disposable temporary directories."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import compress_json_traces as compress
from scripts import evidence_prune as prune
from scripts import storage_budget as budget
from scripts import storage_common as common
from scripts import ugrp_session as session


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # macOS /var is itself a symlink; use the actual temporary directory.
        self.root = Path(self.tmp.name).resolve() / 'run'
        self.root.mkdir()
        (self.root / 'EXIT').write_text('0\n')
        (self.root / 'RUN_META.json').write_text(json.dumps({
            'class': 'dev', 'pr': 123, 'branch': 'codex/test', 'sha': 'a' * 40,
            'batch': 'test', 'keep': ['representative-data', 'special.npz']}))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, size=100):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'x' * size)
        return target

    def test_projected_floor_exact_boundary_and_pending_output(self):
        for host, floor in budget.FLOORS.items():
            free = floor * budget.GIB + 5 * 2**20
            self.assertTrue(budget.check(host, free, 5, 2**20)['ok'])
            self.assertFalse(budget.check(host, free, 5, 2**20, 1)['ok'])
        self.assertTrue(budget.check('mac', 16 * budget.GIB, 0, 0, alert=True)['ok'])
        self.assertFalse(budget.check('mac', 16 * budget.GIB, 0, 0)['ok'])

    def test_remote_query_preserves_shell_metacharacters_as_data(self):
        result = mock.Mock(stdout=str(50 * budget.GIB))
        with mock.patch.object(budget.subprocess, 'run', return_value=result) as run:
            budget.free_bytes('~/runs;touch /bad', 'oracle')
        command = run.call_args.args[0][-1]
        import shlex
        parsed = shlex.split(command)
        self.assertEqual(parsed[:2], ['python3', '-c'])
        self.assertIn("'~/runs;touch /bad'", parsed[2])

    def test_cross_host_gate_fails_when_arm_would_fill(self):
        with mock.patch.object(budget, 'free_bytes', side_effect=[30 * budget.GIB, 25 * budget.GIB, 50 * budget.GIB]):
            self.assertEqual(budget.main(['--all-hosts', '--runs', '36', '--per-run-mb', '430',
                                          '--mac-per-run-mb', '5']), 1)

    def test_lookup_error_and_bad_estimates_fail_closed(self):
        with mock.patch.object(budget, 'free_bytes', side_effect=OSError('offline')):
            self.assertEqual(budget.main(['--host', 'arm', '--runs', '1', '--per-run-mb', '1']), 1)
        for value in ('nan', '-1', 'inf'):
            self.assertEqual(budget.main(['--host', 'arm', '--runs', '1', '--per-run-mb', value]), 1)

    def test_low_space_alarm_returns_failure(self):
        with mock.patch.object(budget, 'free_bytes', return_value=14 * budget.GIB):
            self.assertEqual(budget.main(['--host', 'mac', '--alert-only']), 1)

    def test_compressed_legacy_estimate_without_original_size_refuses(self):
        self.write('trace.json.zst', 20)
        with self.assertRaises(ValueError):
            budget.estimate(self.root, 1)

    def test_legacy_estimate_requires_denominator_and_completion(self):
        self.write('trace.jsonl', 80000)
        (self.root / 'RUN_META.json').unlink()
        with self.assertRaises(ValueError):
            budget.estimate(self.root, None)
        self.assertEqual(budget.estimate(self.root, 4), 25001)
        (self.root / 'EXIT').unlink()
        with self.assertRaises(ValueError):
            budget.estimate(self.root, 4)

    def test_raw_cannot_use_ephemeral_or_tmpfs(self):
        with self.assertRaises(ValueError):
            common.persistent(Path('/dev/shm/evidence'))
        with self.assertRaises(ValueError):
            common.persistent(Path('/tmp/evidence'))
        if Path('/proc/self/mountinfo').exists():
            with mock.patch.object(common.subprocess, 'run', return_value=mock.Mock(stdout='tmpfs\n')):
                with self.assertRaises(ValueError):
                    common.persistent(Path('/home'))

    def test_pr_open_or_lookup_failure_never_authorizes_pruning(self):
        with mock.patch.object(prune.subprocess, 'run', return_value=mock.Mock(stdout='{"number":123,"state":"OPEN"}')):
            with self.assertRaises(ValueError):
                prune.pr_info(123)
        with mock.patch.object(prune.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'gh')):
            self.assertEqual(prune.main(['--pr', '123', str(self.root)]), 1)

    def test_another_open_pr_on_same_branch_blocks(self):
        with mock.patch.object(prune.subprocess, 'run', side_effect=[
                mock.Mock(stdout='{"number":123,"state":"MERGED","headRefName":"codex/test"}'),
                mock.Mock(stdout='[{"number":456}]')]):
            with self.assertRaises(ValueError):
                prune.pr_info(123)

    def test_dry_run_preserves_media_text_keep_and_hashes(self):
        self.write('frames/a.jpg')
        self.write('array.npz')
        self.write('trace.jsonl', 70000)
        for name in ('representative.mp4', 'representative-data/frames.jpg', 'special.npz',
                     'llm-request.json', 'pair-commands.jsonl', 'summary.json', 'small-trace.jsonl'):
            self.write(name, 70000 if 'json' in name and 'small' not in name else 10)
        original = {p: p.read_bytes() for p in common.files(self.root)}
        planned = prune.plan(self.root, 123)
        self.assertEqual({r['path'] for r in planned['candidates']}, {'frames/a.jpg', 'array.npz', 'trace.jsonl'})
        self.assertEqual(original, {p: p.read_bytes() for p in common.files(self.root)})
        self.assertFalse((self.root / 'PRUNED-hashes.tsv').exists())

    def test_compressed_large_trace_still_prunable_when_small(self):
        self.write('trace.jsonl.zst', 20)
        (self.root / 'COMPRESSED.jsonl').write_text(json.dumps({
            'compressed_path': 'trace.jsonl.zst', 'bytes': 100000}) + '\n')
        self.assertEqual(prune.plan(self.root, 123)['bytes'], 20)
        self.assertGreaterEqual(budget.estimate(self.root, None), 125000)

    def test_llm_records_survive_every_size_and_compressed_form(self):
        originals = {}
        manifest = []
        for word in ('ledger', 'llm', 'model', 'prompt', 'request', 'response',
                     'message', 'dialogue', 'episode'):
            for suffix in ('.json', '.jsonl', '.json.zst', '.jsonl.zst'):
                for size in (20, common.TRACE_LIMIT + 1):
                    name = f'{size}/robot-{word.upper()}-history{suffix}'
                    path = self.write(name, size)
                    originals[path] = path.read_bytes()
                    if suffix.endswith('.zst'):
                        manifest.append({'compressed_path': name, 'bytes': 10**9})
        episode = self.write('episode.jsonl', common.TRACE_LIMIT + 1)
        originals[episode] = episode.read_bytes()
        (self.root / 'COMPRESSED.jsonl').write_text(
            ''.join(json.dumps(row) + '\n' for row in manifest))
        media = self.write('frame.jpg')
        with mock.patch.object(prune, 'pr_info', return_value={'number': 123, 'state': 'MERGED'}), \
                mock.patch.object(prune, 'refuse_if_in_use'), mock.patch.object(prune.sys, 'platform', 'linux'):
            planned = prune.execute(self.root, 123, self.root.parent / 'records')
        self.assertEqual([row['path'] for row in planned['candidates']], ['frame.jpg'])
        self.assertFalse(media.exists())
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})

    def test_walkers_skip_nested_directory_links_and_linked_ancestors(self):
        self.write('nested/frame.jpg')
        linked = self.root.parent / 'linked'
        linked.symlink_to(self.root, target_is_directory=True)
        (self.root / 'nested/link').symlink_to(self.root, target_is_directory=True)
        (self.root / 'nested/outside').symlink_to(self.root.parent, target_is_directory=True)
        self.assertEqual({p.relative_to(self.root).as_posix() for p in common.files(self.root)},
                         {'EXIT', 'RUN_META.json', 'nested/frame.jpg'})
        self.assertEqual(list(common.run_dirs(self.root)), [self.root])
        for root in (linked, linked / 'nested'):
            with self.subTest(root=root):
                self.assertEqual(list(common.files(root)), [])
                self.assertEqual(list(common.run_dirs(root)), [])
                self.assertIn('symlink', common.idle_reason(root))
                self.assertIn('symlink', compress.compress_run(root, execute=True)['skipped'])
                with self.assertRaises(ValueError):
                    prune.execute(root, 123, self.root.parent / 'records')
        self.assertFalse((self.root / '.evidence.lock').exists())
        self.assertFalse(common.safe_path(self.root.parent / 'outside.jpg', self.root))
        self.assertFalse(common.safe_path(self.root / 'nested/link/EXIT', self.root))

    def test_execute_rechecks_parent_link_before_removal(self):
        media = self.write('frames/frame.jpg')
        outside = self.root.parent / 'outside-frames'

        def replace_parent_after_inventory(path, root):
            safe = common.safe_path(path, root)
            if path == media and safe:
                # Same inode/stat via the link: snapshots alone cannot detect it.
                media.parent.rename(outside)
                media.parent.symlink_to(outside, target_is_directory=True)
            return safe

        with mock.patch.object(prune, 'pr_info', return_value={'number': 123, 'state': 'MERGED'}), \
                mock.patch.object(prune, 'refuse_if_in_use'), \
                mock.patch.object(prune, 'safe_path', side_effect=replace_parent_after_inventory), \
                mock.patch.object(prune.sys, 'platform', 'linux'):
            with self.assertRaisesRegex(ValueError, 'run/file changed before pruning'):
                prune.execute(self.root, 123, self.root.parent / 'records')
        self.assertEqual((outside / 'frame.jpg').read_bytes(), b'x' * 100)

    def test_compression_manifest_is_never_compressed_recursively(self):
        self.write('COMPRESSED.jsonl', 70000)
        self.assertEqual(compress.compress_run(self.root)['files'], 0)

    def test_classes_unfinished_active_and_parent_study_are_preserved(self):
        self.write('frame.png')
        for change in ({'class': 'milestone'}, {'class': 'study'}, {'active': True}, {'in_use': True}, {'pr': 999}):
            (self.root / 'RUN_META.json').write_text(json.dumps({'class': 'dev', 'pr': 123, **change}))
            self.assertEqual(prune.plan(self.root, 123)['bytes'], 0)
        (self.root / 'RUN_META.json').write_text('{"class":"dev","pr":123}')
        (self.root / 'EXIT').unlink()
        self.assertEqual(prune.plan(self.root, 123)['bytes'], 0)
        (self.root / 'EXIT').touch()
        (self.root.parent / 'RUN_META.json').write_text('{"class":"study"}')
        self.assertEqual(prune.plan(self.root, 123)['bytes'], 0)

    def test_nested_runs_and_symlinks_are_not_deleted(self):
        target = Path(self.tmp.name) / 'outside.jpg'
        target.write_bytes(b'outside')
        (self.root / 'linked.jpg').symlink_to(target)
        self.assertEqual(prune.plan(self.root, 123)['bytes'], 0)
        self.write('nested/RUN_META.json', 0).write_text('{"class":"study"}')
        self.write('nested/frame.jpg')
        self.assertIn('nested', prune.plan(self.root, 123)['skipped'])
        self.assertEqual(target.read_bytes(), b'outside')

    def test_invalid_keep_path_refuses(self):
        (self.root / 'RUN_META.json').write_text('{"class":"dev","pr":123,"keep":["../outside"]}')
        with self.assertRaises(ValueError):
            prune.plan(self.root, 123)

    def test_execute_temp_run_writes_full_inventory_before_removal(self):
        media = self.write('frame.jpg')
        self.write('commands.jsonl')
        records = Path(self.tmp.name) / 'outputs' / 'cleanup-records'
        with mock.patch.object(prune, 'pr_info', return_value={'number': 123, 'state': 'MERGED'}), \
                mock.patch.object(prune, 'refuse_if_in_use'), mock.patch.object(prune.sys, 'platform', 'linux'):
            row = prune.execute(self.root, 123, records)
        self.assertEqual(row['bytes'], 100)
        self.assertFalse(media.exists())
        self.assertIn('commands.jsonl', (self.root / 'ALL-hashes.tsv').read_text())
        self.assertIn('frame.jpg', (self.root / 'PRUNED-hashes.tsv').read_text())
        self.assertEqual(json.loads(next(records.glob('*.json')).read_text())['status'], 'done')

    def test_execute_refuses_busy_process_before_hash_or_removal(self):
        media = self.write('frame.jpg')
        with mock.patch.object(prune, 'refuse_if_in_use', side_effect=prune.Refused('busy')):
            with self.assertRaises(prune.Refused):
                prune.execute(self.root, 123, Path(self.tmp.name) / 'records')
        self.assertTrue(media.exists())
        self.assertFalse((self.root / 'PRUNED-hashes.tsv').exists())

    @unittest.skipUnless(shutil.which('zstd'), 'zstd CLI needed')
    def test_real_zstd_roundtrip_and_manifest_keep_original_sha(self):
        source = self.write('trace.jsonl', 100000)
        digest = common.sha256(source)
        with mock.patch.object(compress, 'refuse_if_in_use'):
            self.assertEqual(compress.compress_run(self.root, execute=True)['files'], 1)
            before = (self.root / 'ALL-hashes.tsv').read_text()
            self.assertEqual(compress.compress_run(self.root, execute=True)['files'], 0)
        self.assertFalse(source.exists())
        self.assertEqual(compress.decompressed_hash(self.root / 'trace.jsonl.zst'), digest)
        self.assertIn(before, (self.root / 'ALL-hashes.tsv').read_text())
        record = json.loads((self.root / 'COMPRESSED.jsonl').read_text())
        self.assertEqual(record['sha256'], digest)

    @unittest.skipUnless(shutil.which('zstd'), 'zstd CLI needed')
    def test_mismatch_leaves_original_and_no_published_target(self):
        source = self.write('trace.jsonl', 70000)
        with mock.patch.object(compress, 'decompressed_hash', return_value='wrong'), \
                mock.patch.object(compress, 'refuse_if_in_use'):
            with self.assertRaises(ValueError):
                compress.compress_run(self.root, execute=True)
        self.assertTrue(source.exists())
        self.assertFalse((self.root / 'trace.jsonl.zst').exists())

    def test_compression_skips_unfinished_and_does_not_overwrite(self):
        source = self.write('trace.jsonl', 70000)
        (self.root / 'EXIT').unlink()
        self.assertIn('skipped', compress.compress_run(self.root, execute=True))
        self.assertTrue(source.exists())
        (self.root / 'EXIT').touch()
        target = self.write('trace.jsonl.zst', 20)
        with mock.patch.object(compress, 'refuse_if_in_use'):
            with self.assertRaises(ValueError):
                compress.compress_run(self.root, execute=True)
        self.assertEqual(target.read_bytes(), b'x' * 20)
        self.assertTrue(source.exists())

    def test_missing_metadata_multiple_roots_are_dry_run_no_write(self):
        (self.root / 'RUN_META.json').unlink()
        self.write('frame.jpg')
        with mock.patch.object(prune, 'pr_info', return_value={'number': 123, 'state': 'CLOSED'}):
            self.assertEqual(prune.main(['--pr', '123', str(self.root), str(self.root.parent)]), 0)
        self.assertTrue((self.root / 'frame.jpg').exists())
        self.assertFalse((self.root / 'ALL-hashes.tsv').exists())

    def test_metadata_wrapper_defaults_dev_and_marks_completion(self):
        root = self.root.parent / 'new'
        args = argparse.Namespace(evidence_dir=root, evidence_class='dev', pr=123,
                                  batch='batch', name='meta', keep=['representative.mp4'],
                                  storage_host='mac', expected_mb=1, grace=0)
        with mock.patch.object(common, 'persistent'), \
                mock.patch.object(session.shutil, 'disk_usage', return_value=mock.Mock(free=30 * budget.GIB)), \
                mock.patch.object(session.subprocess, 'run', side_effect=[
                    mock.Mock(stdout='codex/test\n'), mock.Mock(stdout='a' * 40), mock.Mock(stdout='')]), \
                mock.patch.object(session, 'run_session', return_value=0):
            self.assertEqual(session.run_evidence_session(args, ['true']), 0)
            with self.assertRaises(ValueError):
                session.run_evidence_session(args, ['true'])
        meta = json.loads((root / 'RUN_META.json').read_text())
        self.assertEqual((meta['class'], meta['pr'], meta['batch'], meta['active']), ('dev', 123, 'batch', False))
        self.assertEqual((root / 'EXIT').read_text(), '0\n')

    def test_archive_dry_run_skips_unfinished_and_unevaluated(self):
        import time
        base = Path(self.tmp.name)
        runs, tools, archive, commands = [base / s for s in ('runs', 'tools', 'archive', 'bin')]
        for p in (runs, tools / 'scripts', archive, commands):
            p.mkdir(parents=True)
        for executable in ('mountpoint', 'flock'):
            p = commands / executable
            p.write_text('#!/bin/sh\nexit 0\n')
            p.chmod(0o755)
        (tools / 'scripts/compress_json_traces.py').write_text('import sys; print(sys.argv[1])\n')
        for name in ('unfinished', 'unevaluated', 'complete'):
            root = runs / name
            root.mkdir()
            if name != 'unfinished':
                (root / 'EXIT').touch()
            if name == 'complete':
                (root / 'summary.json').write_text('{}')
            for p in [*root.iterdir(), root]:
                os.utime(p, (time.time()-1800, time.time()-1800))
        script = Path(__file__).resolve().parents[1] / 'scripts/ugrp_auto_archive.sh'
        result = subprocess.run(['bash', str(script), '--dry-run'], capture_output=True, text=True,
                                env={**os.environ, 'PATH': str(commands) + os.pathsep + os.environ['PATH'],
                                     'UGRP_RUNS': str(runs), 'UGRP_ARCHIVE': str(archive),
                                     'UGRP_STORAGE_TOOLS': str(tools), 'UGRP_ARCHIVE_LOCK': str(base / 'archive.lock')})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(runs / 'complete'), result.stdout)
        self.assertNotIn(str(runs / 'unfinished'), result.stdout)
        self.assertNotIn(str(runs / 'unevaluated'), result.stdout)
        self.assertTrue((runs / 'complete').is_dir())


if __name__ == '__main__':
    unittest.main()
