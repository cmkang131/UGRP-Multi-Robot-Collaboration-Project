"""Saved carry6 proposal/clock replay only. GT is joined AFTER decisions."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np
from sim.solo_carry7 import correction_gate, innovation_gate
from sim.active_lookaround import wrap

ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/Users/changmin/projects/ugrp/outputs')
OUT=ROOT/'experiments/2026-10-15-map-carry-zone'
SEEDS=(93261,93262,93266)


def read(path):
    p=Path(path)
    if not p.exists(): p=Path(str(p)+'.zst')
    data=subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
    manifest=p.parent.parent/'SHA256SUMS'
    lines={Path(line.split()[-1]).name:line.split()[0] for line in manifest.read_text().splitlines()}
    name=p.name if p.name in lines else p.name.removesuffix('.zst')
    payload=p.read_bytes() if name==p.name else data
    if lines.get(name)!=hashlib.sha256(payload).hexdigest():
        raise ValueError('original manifest mismatch: '+str(p))
    return data,dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                     decompressed_sha256=hashlib.sha256(data).hexdigest(),original_manifest_verified=True)


def audit():
    runs=[];inputs=[];fixture=[]
    for seed in SEEDS:
        raw=BASE/f'gcp1-runs/solo-carry-{seed}-d9e0073f/raw'
        content,receipt=read(raw/'result.json');inputs.append(receipt);result=json.loads(content)
        assert (raw.parent/'SOURCE_SHA').read_text().strip()==result['source_sha']=='d9e0073f5db51cde78f571aeb1ce91ad44d23eaa'
        content,receipt=read(raw/'teacher-commands.jsonl');inputs.append(receipt)
        commands=[json.loads(x) for x in content.splitlines()]
        content,receipt=read(raw/'eval-only.jsonl');inputs.append(receipt)
        evaluations=[json.loads(x) for x in content.splitlines()]
        content,receipt=read(raw/'carry-static-map.json');inputs.append(receipt)
        look=result['lookaround']['localizer'];views=look['localizer']['views']
        scored={round(e['t'],1):e for e in result['lookaround']['evaluation']['views']}
        proposals=[]
        for v in views:
            if 'grid' not in v: continue
            prior=np.asarray(v['prior']);P=np.diag(np.square(v['prior_sigma']))
            proposal=prior+np.asarray(v['grid']['shift']);proposal[2]=wrap(proposal[2])
            # Deliberately no GT in these calls. Old ledgers do not contain
            # wall endpoints or the uncollapsed likelihood surface.
            gate=correction_gate(prior,P,proposal,v.get('sensor_modes'))
            old=v.get('fix_acceptance',{});partial=v.get('partial_update',{}).get('applied',False)
            row=dict(seed=seed,t=v['t'],prior=v['prior'],prior_sigma=v['prior_sigma'],proposal=proposal.tolist(),
                old_full=old.get('accepted',False),old_partial=partial,carry7=gate,
                old_innovation_chi2=old.get('innovation_chi2'),
                wall_endpoint_replay_available='wall_endpoints' in v)
            fixture.append({k:row[k] for k in ('seed','t','prior','prior_sigma','proposal','old_full','old_partial')})
            # Evaluation-only join follows all acceptance decisions.
            e=scored[round(v['t'],1)];truth=e['truth']
            def error(x):
                return dict(xy_m=math.dist(x[:2],truth[:2]),yaw_deg=math.degrees(wrap(x[2]-truth[2])))
            row['evaluation_only']=dict(prior_error=error(prior),old_applied_error=error(v['posterior']),
                                         rejected_proposal_error=error(proposal),
                                         rollback_error=error(prior))
            proposals.append(row)
        phases=[]
        for r in commands:
            if not phases or phases[-1]['phase']!=r['phase']:
                phases.append(dict(t=r['t'],phase=r['phase'],pan_pulse=r['command']['pwm']['6']))
        reacquire=[r for r in commands if r['phase']=='carry_reacquire']
        reobserve=[r for r in commands if r['phase']=='carry_reobserve']
        starts=[e for e in look['events'] if e['event']=='start']
        review=BASE/f'e2e18-admin/gcp-reports/solo-carry-d9e0073f-ops/solo-carry-{seed}-d9e0073f-review'
        selection=json.loads((review/'selection.json').read_text());visual=[]
        for selected in selection['rows']:
            for camera in ('top','own'):
                p=review/camera/Path(selected[camera]['path']).name
                assert hashlib.sha256(p.read_bytes()).hexdigest()==selected[camera]['sha256']
                visual.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                   sim_s=selected[camera]['sim_s'],camera=camera,evaluation_only=camera=='top'))
        runs.append(dict(seed=seed,status=result['status'],termination=result['termination_reason'],
            source_sha=result['source_sha'],proposals=proposals,phases=phases,
            old_full_fixes=sum(p['old_full'] for p in proposals),
            old_partial_updates=sum(p['old_partial'] for p in proposals),
            prediction_gate_rejects=sum(not innovation_gate(p['prior'],np.diag(np.square(p['prior_sigma'])),p['proposal'])['accepted']
                                        for p in proposals if p['old_full'] or p['old_partial']),
            carry7_full_adoptions=sum(p['old_full'] and p['carry7']['accepted'] for p in proposals),
            reacquire_ticks=len(reacquire),reacquire_visible_ticks=sum(r['visible_target'] is not None for r in reacquire),
            reacquire_pan_range=[min(r['command']['pwm']['6'] for r in reacquire),max(r['command']['pwm']['6'] for r in reacquire)] if reacquire else None,
            reacquire_body_motion_ticks=sum(any(r['command']['wheels']) for r in reacquire),
            reobserve_elapsed_s=reobserve[-1]['t']-reobserve[0]['t'] if reobserve else None,
            scan_starts=[dict(t=e['t'],views=e.get('plan_views'),robust=e.get('rank_aware',{}).get('robust_feasible')) for e in starts],
            visual_review=visual,
            visual_findings='7 timestamps start/middle/end; no peer blocks r1 in selected overview frames; cargo stays on floor; own late views floor/wall. r2 own RGB unavailable.',
            eval_rows=len(evaluations)))
    return dict(schema='ugrp.carry7_offline.v1',research_result=False,student_execution=False,
        new_simulation_runs=0,source_baseline='d9e0073f5db51cde78f571aeb1ce91ad44d23eaa',
        scope='proposal decisions conditioned on carry6 priors; not counterfactual trajectory replay or transport success',
        missing='old wall endpoints/raw capture images/uncollapsed mode weights unavailable locally; ambiguity unknown, fail closed. Sampled review images are not localisation captures.',
        pooling_previous_results=False,runs=runs,inputs=inputs),fixture


def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture-out',type=Path);a=p.parse_args()
    value,fixture=audit()
    (OUT/'carry7-replay.json').write_text(json.dumps(value,indent=2)+'\n')
    if a.fixture_out: a.fixture_out.write_text(json.dumps(dict(schema='carry6_saved_proposals.v1',rows=fixture),indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('seed','old_full_fixes','old_partial_updates','prediction_gate_rejects','carry7_full_adoptions','reacquire_ticks','reacquire_visible_ticks','reobserve_elapsed_s')} for r in value['runs']],indent=2))

if __name__=='__main__': main()
