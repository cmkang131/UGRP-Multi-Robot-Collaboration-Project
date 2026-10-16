#!/usr/bin/env python3
"""Verify measurements without loading UGRP runtime or running simulations."""
import ast
import csv
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).parent.resolve()
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from analyze import stats


def read(name):return json.loads((HERE/'data'/name).read_text())


class MeasurementChecks(unittest.TestCase):
    def test_complete_pr_universe_and_diff_coverage(self):
        prs=read('prs.json')
        self.assertEqual([p['number'] for p in prs],list(range(256,295)))
        self.assertEqual(len({p['headRefName'] for p in prs}),39)
        self.assertEqual(sum(bool(p['mergedAt']) for p in prs),36)
        for p in prs:
            files=p.get('git_file_stats',p['files'])
            self.assertEqual(sum(f['additions'] for f in files),p['additions'],p['number'])
            self.assertEqual(sum(f['deletions'] for f in files),p['deletions'],p['number'])
        p=next(p for p in prs if p['number']==285)
        self.assertEqual(len(p['files']),113)
        self.assertEqual(sum(f['additions'] for f in p['git_file_stats'])-sum(f['additions'] for f in p['files']),12233)

    def test_censoring_and_independent_clock_example(self):
        with (HERE/'derived/prs.csv').open() as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual([int(r['pr']) for r in rows if not r['open_to_merge_s']],[285,292,293])
        # 04:32:08 -> 19:19:02 is 14:46:54, independently calculated.
        row=next(r for r in rows if r['pr']=='256')
        self.assertEqual(float(row['open_to_merge_s']),14*3600+46*60+54)
        self.assertEqual(stats([1,2,3,4,5,6,7,8,9,10])['p90_nearest_rank'],9)
        self.assertIsNone(stats([])['median'])

    def test_ci_attempt_coverage_and_job_clocks(self):
        ids=set()
        for r in read('runs.json'):
            self.assertNotIn(r['id'],ids);ids.add(r['id'])
            snap=read(f'jobs_{r["id"]}.json')
            self.assertEqual([a['attempt'] for a in snap['attempts']],list(range(1,r['run_attempt']+1)))
            for a in snap['attempts']:
                self.assertEqual(len(a['jobs']),len({j['id'] for j in a['jobs']}))
                for j in a['jobs']:
                    if j['started_at'] and j['completed_at']:
                        self.assertLessEqual(j['started_at'],j['completed_at'])
        self.assertEqual(len(ids),152)
        summary=json.loads((HERE/'derived/summary.json').read_text())
        self.assertEqual(sum(summary['ci']['associated_conclusions'].values()),95)
        self.assertEqual(summary['ci']['associated_rerun_attempts'],4)

    def test_shard_partition_without_test_execution(self):
        d=json.loads((HERE/'data/current_shards.txt').read_text())
        files=[f for shard in d['shards'] for f in shard]
        self.assertEqual(len(files),328)
        self.assertEqual(len(files),len(set(files)))
        self.assertEqual(len(d['shards']),8)
        self.assertTrue(d['coverage_verified'])

    def test_reproducible_derivations(self):
        with tempfile.TemporaryDirectory(prefix='ugrp-process-verify-') as tmp:
            out=Path(tmp)
            subprocess.run([sys.executable,str(HERE/'analyze.py'),'--out',str(out)],check=True,stdout=subprocess.DEVNULL)
            subprocess.run([sys.executable,str(HERE/'git_metrics.py'),'--out',str(out)],check=True,stdout=subprocess.DEVNULL)
            for path in out.iterdir():
                self.assertEqual(path.read_bytes(),(HERE/'derived'/path.name).read_bytes(),path.name)

    def test_local_links_sizes_and_script_syntax(self):
        for p in HERE.glob('*.py'):ast.parse(p.read_text())
        for p in HERE.glob('*.md'):
            for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
                if '://' in link or link.startswith('#'):continue
                path=link.split('#')[0]
                self.assertTrue((p.parent/path).exists(),f'{p.name}: {link}')
        files=[p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        self.assertTrue(all(p.stat().st_size<=1024**2 for p in files))
        self.assertLess(sum(p.stat().st_size for p in files),5*1024**2)
        # Private transcript outputs are aggregate only, never message records.
        t=read('transcript_aggregate.json')
        self.assertEqual(t['unique_assistant_message_ids'],875)
        self.assertNotIn('messages',t)
        self.assertNotIn('content',t)

if __name__=='__main__':unittest.main(verbosity=2)
