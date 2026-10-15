"""Pinned gcp2 run-first queue; no physics or host lifecycle mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PLAN='experiments/2026-10-16-beampair7/gate-plan.json'
SHORT=(8318711,8318701,8318706,8318700,8318726)
REMOTE=Path('/home/ugrp/ugrp-sim/ops-reviews/beampair7')


def build(source, stage, table, evidence=None, round_id='r1'):
    table=Path(table).resolve()
    if not table.is_file():raise ValueError('existing absolute rejection_table required')
    source=subprocess.check_output(['git','rev-parse','--verify',source+'^{commit}'],cwd=ROOT,text=True).strip()
    data=subprocess.check_output(['git','show',f'{source}:{PLAN}'],cwd=ROOT)
    plan=json.loads(data)
    if len(plan['episodes'])!=40 or len({e['seed'] for e in plan['episodes']})!=40:
        raise ValueError('exact forty distinct certified setups required')
    if any(e.get('scene_profile')!='walls_floor_contrast_v5_indigo110_s80' for e in plan['episodes']):
        raise ValueError('pinned new scene required')
    if stage=='gate':
        if evidence is None:raise ValueError('short raw recount required')
        proof=json.loads(Path(evidence).read_bytes())
        funnel=json.loads(table.read_bytes())
        if (proof.get('source_sha')!=source or proof.get('N')!=len(SHORT)
                or proof.get('n')!=len(SHORT) or proof.get('cap_end_N') or proof.get('incomplete_N')
                or proof.get('HOST_ERROR_N') or proof.get('analysis_incomplete')
                or proof.get('held_world_reads') or proof.get('invisible_measurements')
                or funnel.get('source_sha')!=source
                or len(proof.get('runs',[]))!=len(SHORT)
                or {r['seed'] for r in proof['runs']}!=set(SHORT)
                or any(r['adapter_sha']!=source or r.get('peer_yield')!='beampair_peer_yield_v1'
                    or not r.get('strict_success') or not r.get('visible_eligible')
                    or not r.get('held_object_hidden_v1')
                    or (r.get('audit') or {}).get('enabled') is not True
                    or any((r.get('audit') or {}).get(k)!=0 for k in ('invisible_measurements','held_world_reads'))
                    for r in proof['runs'])):
            raise ValueError('all five exact-source raw successes required')
    episodes=list(enumerate(plan['episodes']))
    if stage=='short':episodes=[next(p for p in episodes if p[1]['seed']==s) for s in SHORT]
    else:episodes.sort(key=lambda p:(p[1]['seed']!=SHORT[0],p[0]))
    runs=[dict(episode=i,seed=e['seed'],candidate='baseline',profile={},
        name=f'beampair7-{stage}-{round_id}-{e["seed"]}-{source[:8]}',source_sha=source,
        approved=True,enabled=True,ready=True,submitted=False,stage=stage) for i,e in episodes]
    digest=hashlib.sha256(table.read_bytes()).hexdigest()
    return dict(kind='beampair',owner='beampair7',stage=stage,round=round_id,source_sha=source,
        host='gcp2',project='ugrp-sim-b-1014',account='changmin5781@gmail.com',max_parallel=16 if stage=='gate' else 4,
        cap_s=60,sentinel_first=stage=='short',runs=runs,ready=True,approved=True,
        review_passed=True,status='APPROVED_PINNED',
        review_detail='REVIEW_SKIPPED_BY_USER (10/15 run-first rule)',
        rejection_table=str(REMOTE/table.name),rejection_table_sha256=digest,
        local_rejection_table=str(table),plan=str(REMOTE/'gate-plan.json'),plan_sha256=hashlib.sha256(data).hexdigest(),
        peer_yield='beampair_peer_yield_v1',training_rgb=False,weld=False,
        held_object_hidden_v1=True,failure_tail_recording=True,
        scene_profile='walls_floor_contrast_v5_indigo110_s80',floor='v1',camera_quality='no_mip_v1',
        pooling='New candidate only; short5, old15/16 and gcp1 excluded from gate40')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--stage',choices=('short','gate'),required=True);p.add_argument('--round',default='r1')
    p.add_argument('--rejection-table',type=Path,required=True);p.add_argument('--evidence',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    q=build(a.source,a.stage,a.rejection_table,a.evidence,a.round)
    with a.output.open('x') as f:f.write(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:q[k] for k in ('status','source_sha','stage','max_parallel','review_detail','rejection_table')}))
