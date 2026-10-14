"""Register coordinator-only diagnostic/gate work after a verified push.

Does not submit simulations. Keeps the old queue and a hash-verified backup.
"""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
OLD='e14fa729d1bbb80acb7706d4d53e99b19fe122ba'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    if branch!='claude/grasp-act-probes' or sha==OLD:raise ValueError('new committed probes source required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True):raise ValueError('clean source required')
    remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/'+branch],cwd=ROOT,text=True).split()[0]
    if sha!=remote:raise ValueError('remote SHA mismatch')
    validation=json.loads((BASE/'release-global-offline-summary.json').read_text())
    if validation['tests']['passed']!=80 or validation['tests']['failures'] or validation['tests']['errors']:
        raise ValueError('related tests must pass')
    oldpath=QUEUE/f'20261014-release-gate-{OLD[:8]}.json';original=oldpath.read_bytes()
    source=json.loads(original)
    def replace(value):
        if isinstance(value,str):
            for before,after in ((OLD,sha),(OLD[:8],sha[:8]),('release-center-','release-global-'),
                                 ('setdown_lookaround_v2','setdown_global_v1'),('zone_center_rgb_v1','global_localized_release_v1')):
                value=value.replace(before,after)
            return value
        if isinstance(value,list):return [replace(v) for v in value]
        if isinstance(value,dict):return {replace(k):replace(v) for k,v in value.items()}
        return value
    q=replace(source)
    for key in ('blocked_at','blocked_reason','blocked_evidence','pre_block_backup'):
        q.pop(key,None)
    q.update(sha=sha,created_local=datetime.datetime.now().astimezone().isoformat(),ready=True,status='ready_diagnostic',
             stage_ready=dict(diagnostic=True,gate=False),supersedes_source_sha=OLD,
             remote_source_verification=dict(local_head=sha,remote_head=remote,matches=True),
             offline_validation=validation,
             expected_sim_s_per_run='unmeasured candidate; finite total cap 180 s, prefix cap 35 s')
    q['profile'].update(lookaround='setdown_global_v1',placement='global_localized_release_v1')
    q['plan_sha256']={str((BASE/f'release-global-{stage}-plan.json').relative_to(ROOT)):digest(BASE/f'release-global-{stage}-plan.json') for stage in ('diagnostic','gate')}
    q['preconditions']=[
        'Verify exact pushed SHA, clean immutable source and both plan hashes before each stage.',
        'Coordinator must confirm 74200-74239 were not executed or allocated remotely; no remote history scan by author.',
        'Check disk/cost budgets, idle20m and 8h stop guards before submission.',
        'Diagnostics must pass 7/7 and first-30-SIM/source/input/video review before opening gate 40; EXIT 0 is insufficient.',
        'Review >=6 evenly spaced frames and >=1 per 60 SIM s; own/overview, opposite ends, recovery motion and regrasp.',
        'Unknown map pose may become known ONLY by accepted own-RGB global consensus. No truth anchor, Eyes scan, held-object pose or partner image/pose input.',
        'Inspect every localization decision including rejected hypotheses, residuals, input SHA and map-pose errors from separate evaluation.',
        'Inspect own_rgb_localization_inputs denominators; zero violations with zero observations is not an input audit pass.',
        'Inspect active_observation stage order and skipped-clearance reasons; no claim that command distance/yaw equals realized motion.',
        'Confirmed control/physical/input defect: stop affected owned running/waiting jobs, preserve raw, fix before new measurement.',
        'Keep every result including failure/HOST_ERROR/missing with paths/hashes; do not pool diagnostics or older versions.']
    q['report_needed']='Per-run center distance, all-run n/median/max including failures, farthest-stratum n/N, input frame counts/hashes, localization n/N/residual/map error, active motion, pair margins, shift_steps, statuses/EXIT/raw/SHA256.'
    q['seed_reservation']['evidence']=str((BASE/'release-global-seed-reservation.json').relative_to(ROOT))
    q['order']='diagnostic 7 -> coordinator source/first-30-SIM/video/input/global-pose review -> fresh gate 40'
    for row in q['runs']:
        command=row['command'];command[command.index('--cap-s')+1]='180'
        if row['stage']=='gate':row['condition']='All 7 diagnostics pass and coordinator opens gate after source/input/video/global-pose review. Never auto-run on EXIT 0.'
    out=QUEUE/f'20261014-release-gate-{sha[:8]}.json'
    if out.exists():raise FileExistsError(out)
    # Keep operational queue below 64 KiB without altering its consumer schema.
    encoded=(json.dumps(q,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    out.write_bytes(encoded)
    assert json.loads(out.read_bytes())['sha']==remote
    backup=QUEUE/f'20261014-release-gate-{OLD[:8]}.before-{sha[:8]}.json'
    backup.write_bytes(original)
    assert digest(backup)==hashlib.sha256(original).hexdigest()
    source.update(ready=False,status='superseded',superseded_by_sha=sha,superseded_by_queue=str(out),
                  stage_ready=dict(diagnostic=False,gate=False),superseded_at=q['created_local'])
    oldpath.write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n')
    assert json.loads(oldpath.read_text())['status']=='superseded'
    print(json.dumps(dict(queue=str(out),sha=sha,ready=True,bytes=len(encoded),runs=len(q['runs']),
                         old_status='superseded',backup_sha256=digest(backup)),ensure_ascii=False))


if __name__=='__main__':main()
