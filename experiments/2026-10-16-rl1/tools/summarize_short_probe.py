"""gcp2 CPU-only finite rl1b audit; no model, simulation or renderer imports."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from simalt_host import gcp2_identity


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def rows(path):
    if path.exists():s=path.read_text()
    else:s=subprocess.check_output(['zstd','-dc',str(path)+'.zst'],text=True)
    return [json.loads(line) for line in s.splitlines() if line]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('raw','actor-source','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();host=gcp2_identity()
    if host['instance']!='ugrp-sim-gcp2':p.error('analysis stays on CPU gcp2')
    a.out.mkdir(parents=True,exist_ok=False)
    if subprocess.check_output(['git','-C',str(a.actor_source),'rev-parse','HEAD'],text=True).strip()!='b4db8ba2fb155ad53b210b48f645fcc759157e7b':p.error('exact ACT15 source required')
    sys.path.insert(0,str(a.actor_source))
    from harness import grasp_act_contract as c
    original=Path('/home/ugrp/ugrp-sim/runs/rl1b-gpu-8fc9d826')
    phases={}
    for name in ('probe-r1','probe-r2','probe-r3','probe-r4-reset-only'):
        path=a.raw/name/'summary.json';j=json.loads(path.read_text())
        phases[name]=dict(summary=j,sha256=sha(path),raw=str(original/name))
    actor=rows(a.raw/'probe-r3/actor-inputs.jsonl')
    issued=rows(a.raw/'probe-r3/client/owner/commands.jsonl')
    if len(actor)!=64 or len(issued)!=64:raise ValueError('expected64 probe commands')
    matches=0;image_refs=0;image_paths=set()
    for own,actual in zip(actor,issued):
        if set(own)!={'world','generation','input_root','observation','command','done'}:raise ValueError('actor record whitelist')
        c.validate_observation(own['observation']);c.command(own['command'])
        left={k:own[k] for k in ('command','done')};right={k:actual[k] for k in ('command','done')}
        matches+=int(json.dumps(left,sort_keys=True,separators=(',',':'))==json.dumps(right,sort_keys=True,separators=(',',':')) and own['world']==actual['world'] and own['observation']['t']==actual['t'])
        root=a.raw/Path(own['input_root']).relative_to(original)
        for ref in own['observation']['rgb']:
            img=root/ref['path'];image_refs+=1;image_paths.add(str(img))
            if sha(img)!=ref['sha256']:raise ValueError('actual actor RGB SHA mismatch')
    ev=rows(a.raw/'probe-r3/client/owner/evaluation.jsonl')
    latest={};first={}
    for row in ev:
        if not row['score_sampled']:continue
        latest[row['world']]=row;first.setdefault(row['world'],row)
    gates={k:sum(bool(r['funnel'].get(k)) for r in latest.values()) for k in ('approach','alignment','grasp','lift_confirmation')}
    reset_path=next((a.raw/'probe-r4-reset-only/client/owner').glob('reset-audit-*.json'))
    reset=json.loads(reset_path.read_text())
    owner=json.loads((a.raw/'probe-r4-reset-only/client/owner/owner-summary.json').read_text())
    first_state=json.loads((a.raw/'probe-r3/client/owner/initial-state-audit.json').read_text())
    speed=phases['probe-r3']['summary']
    public=dict(commands=64,canonical_actor_owner_command_matches=matches,validated_observations=len(actor),
        rgb_references=image_refs,distinct_rgb_files=len(image_paths),rgb_hash_mismatches=0,
        evaluation_rpc='client rejects training/private lane; no rejection during64 commands',
        forbidden_loaded_modules=[m for m in ('torch','mujoco','mujoco_warp','scripts.rl_act_learning','scripts.rl_act_reward') if m in sys.modules])
    funnel=dict(scope='probe training-start slots only; not the held-out evaluation, not completed missions',
        slots=8,distinct_initial_translations=first_state['distinct_expected_translations'],task_ticks=8,
        per_world_sim_s=.8,aggregate_sim_s=6.4,issued_commands=64,completed_missions=0,
        gates=gates,station_error_change_m={str(i):latest[i]['station_error_m']-first[i]['station_error_m'] for i in latest},
        causes=[dict(category='frozen_helper_import',attempt='probe-r1',count=1,blocking_object='not_applicable_software_import',minimum_gap_m=None),
            dict(category='static_model_mismatch',attempt='probe-r2',count=1,blocking_object='warehouse_oak_plank/warehouse_steel_pipe/warehouse_wood_crate',minimum_gap_m=None),
            dict(category='result_field_collision',attempt='probe-r3',count=1,blocking_object='not_applicable_recording',minimum_gap_m=None),
            dict(category='preliminary_speed_block',attempt='probe-r3/r4',count=1,blocking_object='not_attributed_shared_GPU_or_backend',minimum_gap_m=None)],
        reproduce=sys.argv,raw=str(original))
    report=dict(status='BLOCKED',verdict='BLOCKED',host=host,phases=phases,public_actor_audit=public,probe_funnel=funnel,
        first_state_audit=first_state,reset_audit=reset,reset_scope='immediate initialization-state reset only; moving reset and subsequent dynamics unverified',
        recording_fix=dict(source_sha=phases['probe-r4-reset-only']['summary']['source_sha'],close_errors=owner['close_errors'],
            qpos_archive_sha256=sha(a.raw/'probe-r4-reset-only/client/owner/warp-qpos.npz'),ring_bytes=owner['recording_ring_bytes']),
        speed=dict(scope='8-tick end-to-end probe on shared L4; formal30SIM gate unmeasured',
            wall_per_sim_median=speed['wall_per_sim_median'],aggregate_sim_s_per_wall_s=speed['aggregate_sim_s_per_wall_s'],
            component_timing='probe-r3 close failure prevented owner timing archive; no physics/render/contention attribution'),
        training=dict(new_transitions=0,optimizer_steps=0,checkpoint_produced=False),
        evaluation=dict(baseline_n=0,residual_n=0,paired=False,baseline_success=None,residual_success=None),
        heuristic_effects={k:'unmeasured; learning not submitted' for k in ('h1','h2','h3','h4')},h5='not used; separate ACT work',
        gpu_usage=json.loads((a.raw/'gpu-usage.json').read_text()),
        playback=json.loads((a.raw/'playback/review-summary.json').read_text()))
    for name,j in (('pilot-result.json',report),('runtime-funnel.json',funnel),('public-actor-audit.json',public)):
        (a.out/name).write_text(json.dumps(j,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status='BLOCKED',public=public,probe_gates=gates,speed=report['speed'],gpu=report['gpu_usage']),indent=2))


if __name__=='__main__':main()
