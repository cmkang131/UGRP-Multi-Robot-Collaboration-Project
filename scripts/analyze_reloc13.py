"""GCP-only saved-evidence funnel. Ground truth is scoring-only, never control."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scripts.analyze_reloc11_selfmap import rows, obj
from harness.natural_floor_slam import compose
from harness.selfmap4_geometry import inverse


def distribution(values):
    return dict(N=len(values), **({k: float(v) for k, v in zip(
        ('min', 'p50', 'p90', 'p95', 'p99', 'max'),
        np.percentile(values, [0, 50, 90, 95, 99, 100]))} if values else {}))


def analyze(folder):
    raw = folder/'raw'
    trace = rows(raw/'trace.jsonl')
    truth = {round(r['t'], 6): r for r in rows(raw/'eval_only/trajectory.jsonl')}
    result = obj(raw/'result.json')
    gates = Counter(); rejects = Counter(); classes = Counter(); errors = []; bad = []
    r7 = Counter(); geom = []; events = []; prior_registered = False
    for r in trace:
        s = r.get('static_registration', {})
        registered = bool(s.get('registered'))
        emitted = registered and len(r.get('pose', [])) == 3
        gates['fresh_static_fix_independent'] += registered and r.get('pose_source') == 'visual_relocalized' and r.get('visual_reason') == 'selfmap4_static_lines'
        inserted = bool(r.get('map_updated'))
        # Actual drive authorization, not merely the presence of a pose.
        used = r.get('stage') in ('frontier_drive', 'frontier', 'drive') or r.get('issued_command', {}).get('kind') in ('drive', 'move')
        cumulative = True
        for name, ok in [('frames', True), ('registered', registered), ('execution_pose_delivered', emitted),
                         ('map_inserted', inserted), ('control_drive_used', used)]:
            if cumulative and not ok:
                reason = (';'.join(r.get('insertion_blockers', [])) if name == 'map_inserted' else
                          str(r.get('correction_admission') or r.get('frontier_reason') or r.get('stage') or name))
                rejects[name+':'+(reason or 'unknown_requires_review')] += 1
            cumulative = cumulative and ok
            gates[name] += cumulative
            gates[name+'_independent'] += ok
        if registered:
            rejects.update('insertion:'+x for x in r.get('insertion_blockers', []))
        a = s.get('geometry', {}).get('ambiguity', {})
        rej = s.get('reloc10_diagnostics', {}).get('rejection_reasons', [])
        r7['ambiguity_evaluated'] += bool(a.get('evaluated'))
        r7['unique'] += bool(a.get('evaluated') and a.get('unique'))
        r7['pf_agreement_reliable'] += bool(s.get('resolved'))
        r7['three_confirmations'] += s.get('confirmations', 0) >= 3
        r7.update('reject:'+x for x in rej)
        replay = s.get('reloc12', {})
        t = truth.get(round(r['t'], 6))
        if t and registered and replay.get('registered_world_pose') is not None:
            anchor = np.asarray(replay['map_from_execution']) if replay.get('execution_frame_v1') else compose(replay['registered_world_pose'], inverse(replay['replay']['own_odometry_pose']))
            p = compose(anchor, r['pose'])
            xy = math.dist(p[:2], t['robot_xyz_m'][:2])
            yaw = abs(math.degrees(math.atan2(math.sin(p[2]-t['robot_yaw_rad']), math.cos(p[2]-t['robot_yaw_rad']))))
            e = dict(t=r['t'], xy_m=xy, yaw_deg=yaw, source=r.get('pose_source'),
                     visual_reason=r.get('visual_reason'), updated=s.get('updated'),
                     correction=r.get('correction_admission'), stage=r.get('stage'),
                     matches=r.get('matches'), inliers=r.get('inliers'))
            errors.append(e)
            if xy > .1 or yaw > 5:
                category = ('xy_and_yaw' if xy > .1 and yaw > 5 else 'xy_only' if xy > .1 else 'yaw_only')
                # Descriptive causal seam; no truth is sent back into runtime.
                category += ':'+str(e['source'])+':'+str(e['visual_reason'])
                classes[category] += 1; bad.append(e)
            if not prior_registered:
                p=np.asarray(s['world_pose']);exy=math.dist(p[:2],t['robot_xyz_m'][:2]);eya=abs(math.degrees(math.atan2(math.sin(p[2]-t['robot_yaw_rad']),math.cos(p[2]-t['robot_yaw_rad']))))
                events.append(dict(t=r['t'],xy_m=exy,yaw_deg=eya,false=exy>.1 or eya>5))
        prior_registered = registered
        if s.get('updated'):
            geom.append(dict(t=r['t'], geo=s.get('geometry'), inliers=r.get('inliers'), matches=r.get('matches')))
    return dict(run=folder.name, raw=str(raw), source_sha=result.get('source_sha'),
        unit='ordered trace frames; events separately counted; temporal correlation retained',
        funnel=dict(gates), rejections=[dict(category=k, N=n, blocked_object='static_registration_or_map_evidence',
            minimum_gap_m=None, gap_status='not_applicable_localization_gate') for k,n in rejects.most_common()],
        R7=dict(r7), registration_events=events, false_registration_events=sum(e['false'] for e in events),
        registered_errors=dict(N=len(errors), bad_N=len(bad), xy_m=distribution([e['xy_m'] for e in errors]),
                               yaw_deg=distribution([e['yaw_deg'] for e in errors])),
        bad_errors=dict(N=len(bad), xy_m=distribution([e['xy_m'] for e in bad]), yaw_deg=distribution([e['yaw_deg'] for e in bad]),
                        classification=dict(classes), frames=bad),
        termination=dict(status=result.get('status'), category=result.get('termination_category'),
                         reason=result.get('stop_reason') or result.get('error'), elapsed_sim_s=result.get('elapsed_sim_s'),
                         supervisor_stop=obj(folder/'SUPERVISOR_STOP.json'),
                         code_vs_host='controller_budget_exhaustion' if result.get('stop_reason') == 'selfmap4_relocalization_exhausted' else 'see_reason'),
        first30=obj(raw/'first30.json'), input_audit=result.get('input_audit'),
        final_frame={k:trace[-1].get(k) for k in ('t','stage','executor_stop_reason','insertion_blockers','frontier_reason')} if trace else {},
        sha256={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (raw/'result.json',raw/'trace.jsonl.zst',raw/'eval_only/trajectory.jsonl.zst',folder/'EXIT') if p.exists()})


def main():
    p=argparse.ArgumentParser(); p.add_argument('folders', nargs='+', type=Path); p.add_argument('--output', type=Path, required=True)
    a=p.parse_args(); data=[analyze(f) for f in a.folders]
    a.output.write_text(json.dumps(dict(schema='ugrp.reloc13.funnel.v1', analysis_host='gcp1',
        reproduce='PYTHONPATH=. .venv-sim/bin/python scripts/analyze_reloc13.py <folders> --output <file>',
        runs=data), indent=2, allow_nan=False)+'\n')
    for r in data:
        print(json.dumps({k:r[k] for k in ('run','funnel','R7','registered_errors','termination','false_registration_events')}))


if __name__ == '__main__': main()
