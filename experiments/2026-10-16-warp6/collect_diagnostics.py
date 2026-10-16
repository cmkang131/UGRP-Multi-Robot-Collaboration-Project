"""Read-only accounting of isolated attempts; incomplete is never a failure trial."""
import argparse
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path


def read(path, fallback=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback if fallback is not None else {}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('/home/ugrp/ugrp-sim/runs/warp6'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    attempts = []
    manifest = {}
    for command in sorted(a.root.glob('*.command.json')):
        name = command.name.removesuffix('.command.json')
        run = a.root / name
        cmd = read(command)
        receipt = read(a.root / (name + '.receipt.json'))
        summary = read(run / 'summary.json')
        stop = read(run / 'SUPERVISOR_STOP.json')
        progress = read(run / 'progress.json')
        trace = []
        try:
            for line in (run / 'workspace-trace.jsonl').read_text().splitlines():
                try: trace.append(json.loads(line))
                except json.JSONDecodeError: pass
        except FileNotFoundError:
            pass
        worlds = summary.get('worlds', [])
        audits=[]
        admissions=[]
        for world in sorted(run.glob('world-*')):
            if not world.is_dir():continue
            admission=read(world/'placement-admission.json')
            if admission:admissions.append(dict(world=world.name,**admission))
            result=read(world/'raw/result.json')
            if result.get('input_audit') is not None:
                audits.append(dict(world=world.name,input_audit=result['input_audit'],
                    scope='saved prefix only' if summary.get('status')!='complete' else 'completed result'))
        n = cmd['planned_world_N']
        completed = len(worlds)
        category = (stop.get('category','DIAGNOSTIC_SUPERVISOR_STOP') if stop else summary.get('error_type') or
                    ('NATIVE_PROCESS_EXIT' if receipt.get('exit_code', 0) else 'running'))
        if stop and category=='HOST_ERROR':category='DIAGNOSTIC_INSTRUMENTATION_STOP'
        terminal=bool(receipt)
        prefix_complete=summary.get('status')=='diagnostic_prefix_complete'
        counts = Counter('cap_end' if w.get('cap_end') else 'teacher_failure'
                         for w in worlds if not w.get('success'))
        if receipt and receipt['exit_code'] != 0:
            counts[category] += n - completed
        funnel = dict(raw=str(run), reproduce=cmd['command'], host='gcp3',
            source_sha=summary.get('source_sha', cmd['source_sha']),
            funnel=[dict(stage='requested', passed_cumulative_N=n, rejected_N=0),
                    dict(stage='native_setup', passed_cumulative_N=summary.get('started_N', 0),
                         rejected_N=n-summary.get('started_N', 0) if terminal else 0),
                    dict(stage='completed_teacher', passed_cumulative_N=completed,
                         rejected_N=n-completed if terminal and not prefix_complete else 0,
                         pending_N=0 if terminal else n-completed,
                         not_requested_N=n-completed if prefix_complete else 0),
                    dict(stage='success', passed_cumulative_N=sum(bool(w.get('success')) for w in worlds),
                         rejected_N=sum(not w.get('success') for w in worlds))],
            rejections=[dict(reason_category=k, blocked_object='software:diagnostic' if receipt.get('exit_code',0) else 'none:unclassified',
                             min_gap_m=None, count=v, gap_scope='nongeometric diagnostic error; no geometric claim')
                        for k,v in counts.most_common()],
            cap_end_N=sum(bool(w.get('cap_end')) for w in worlds),
            HOST_ERROR_world_N=n-completed if receipt.get('exit_code',0) else 0,
            incomplete_world_N=n-completed, worlds=worlds)
        if prefix_complete:
            funnel['funnel'].insert(2,dict(stage='requested_diagnostic_prefix',passed_cumulative_N=n,rejected_N=0))
        attempts.append(dict(name=name, command=cmd, receipt=receipt, supervisor_stop=stop,
            status='HOST_ERROR' if receipt.get('exit_code',0) else summary.get('status','not_started'),
            original_summary_status=summary.get('status'),progress=progress,
            capacities=summary.get('capacities'), trace_rows=len(trace),
            first_overflow=next((r for r in trace if any(r['overflow'])),None),
            max_nacon=max((max(r['nacon']) for r in trace),default=None),
            max_nefc=max((max(r['nefc']) for r in trace),default=None),
            max_awake_dofs=max((max(r['awake_dofs']) for r in trace),default=None),
            input_audits=audits,placement_admissions=admissions,
            placement_accepted_N=sum(bool(v['accepted']) for v in admissions),
            placement_rejected_N=sum(not v['accepted'] for v in admissions),funnel=funnel))
    for path in sorted(a.root.rglob('*')):
        if path.is_file() and path.suffix not in ('.bundle','.tgz'):
            with path.open('rb') as f:
                sha=hashlib.file_digest(f,'sha256').hexdigest()
            manifest[str(path)]=dict(bytes=path.stat().st_size,sha256=sha)
    def write(name,value):
        (a.out/name).write_text(json.dumps(value,indent=2)+'\n')
    write('raw-sha256.json',manifest)
    write('rejection_table.json',dict(populations='attempts kept separate; no trial pooling',
        attempts=[v['funnel'] for v in attempts]))
    write('summary.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='DIAGNOSIS_ONLY', host='gcp3',project='ugrp-sim-c-1016', attempts=attempts,
        gate_submitted=dict(beampair=0,release_A=0,release_B=0), CPU_results_pooled=False,
        raw_file_N=len(manifest),raw_bytes=sum(v['bytes'] for v in manifest.values()),
        rejection_table=str(a.out/'rejection_table.json')))
    print(json.dumps(dict(attempts=len(attempts),files=len(manifest),out=str(a.out))))


if __name__ == '__main__':
    main()
