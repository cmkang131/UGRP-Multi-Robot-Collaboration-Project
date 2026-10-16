"""Finite shared-L4 DEV dispatcher. No credentials, no VM lifecycle changes."""
import argparse,copy,datetime,hashlib,json,os,platform,re,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE=Path('/home/ugrp/ugrp-sim');RUN=BASE/'runs/warp7'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='r1');args=parser.parse_args()
    if not re.fullmatch(r'r[1-3][a-z]?',args.attempt):raise ValueError('finite attempt name required')
    name='n16-'+args.attempt
    assert platform.node().startswith('ugrp-act-l4-gcp2')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT)
    source=json.loads((ROOT/'experiments/2026-10-15-reloc14/carry-texture-v7-plan-final.json').read_text())['episodes']
    templates={seed:json.loads((RUN/f'prior-plan-{seed}.json').read_text())['episodes'][0] for seed in (93266,93315)}
    runs=[]
    options=dict(profile='solo_visible_only_v1',hidden=True,look=True,cap_s=300.,teacher_stability='align_relook_v1',
        reach_mode='pad_window_v2',rgb_lift_mode='solo_lift_lookback_v1',solo_lift_lookback_margin_v1=True,
        solo_truth_free_lookaround_v1=True,solo_carry_to_zone_v1=True,failure_rgb_buffer=True,review_playback=True)
    source=sorted(source,key=lambda e:(0 if e['seed']==93266 else 1 if e['seed']==93315 else 2,e['seed']))
    for episode in source:
        ep=copy.deepcopy(episode)
        template=templates.get(ep['seed'],templates[93266])
        for key,value in template.items():
            if key.endswith(('_v1','_profile','_option')) or key in ('render_profile','scene_version','trim_calibration','active_relocalization'):
                ep[key]=copy.deepcopy(value)
        if ep['seed'] in templates:ep=copy.deepcopy(templates[ep['seed']])
        ep.update(batch='warp7-n16-r1',pr=550,reloc21_route_progress_v1=False,reloc21_complete_plan_v1=False)
        runs.append(dict(kind='carry',condition='reloc20_default_progress_off',seed=ep['seed'],plan=ep,kwargs=options))
    # Five paired diagnostics exercise the corrected removal implementation.
    # These are separate conditions, not sixteen independent baseline trials.
    for prior in runs[:5]:
        trial=copy.deepcopy(prior);trial['condition']='reloc21_removal_diagnostic_only'
        trial['plan']['reloc21_route_progress_v1']=True;runs.append(trial)
    assert len(runs)==16 and len({t['seed'] for t in runs})==11
    cal=ROOT/'experiments/2026-10-16-warp7/paint-calibration.json'
    env=dict(UGRP_SCENE_COLOUR_BOUNDARY='scene_colour_transition_v2',
        UGRP_SCENE_RENDER_PROFILE='walls_floor_contrast_v5_indigo110_s80',
        UGRP_SCENE_COLOUR_CALIBRATION=str(ROOT/'experiments/2026-10-16-reloc16/colour-calibration.json'),
        UGRP_RELOC16_FLOOR_LANDMARK_MASK='scene_floor_landmark_mask_v1',
        UGRP_WARP7_PERCEPTION='rendered_hsv_v1',UGRP_WARP7_CALIBRATION=str(cal),
        UGRP_WARP7_CALIBRATION_SHA256=hashlib.sha256(cal.read_bytes()).hexdigest())
    env['UGRP_SCENE_COLOUR_CALIBRATION_SHA256']=hashlib.sha256(Path(env['UGRP_SCENE_COLOUR_CALIBRATION']).read_bytes()).hexdigest()
    q=dict(task='warp7',source_sha=sha,rejection_table=str(ROOT/'experiments/2026-10-16-warp7/prior-rejection-table.json'),
        render_gate=str(RUN/'colour-r3-summary.json'),diagnostic_only=True,warp5_native_visual_v2=True,
        measured_storage_budget_v1=True,storage_budget=json.loads((RUN/'storage-measured.json').read_text()),
        environment=env,runs=runs,pool_conditions=False,independent_initial_cases=11,
        interpretation='N16 simultaneous DEV:11 baseline initial cases +5 paired removal diagnostics; no full visual/ACT/E2E qualification')
    path=RUN/(name+'-queue.json')
    if path.exists() or (RUN/name).exists():raise ValueError('new attempt paths required')
    path.write_text(json.dumps(q,indent=2)+'\n')
    process_env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',
        PYTHONPATH=str(BASE/'runs/warp5/python-deps')+':'+str(ROOT/'scripts')+':'+str(ROOT),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    command=['timeout','--signal=INT','--kill-after=60','1500',sys.executable,'-m','scripts.sim_cli','workflow','run','warp5-batch','--',
        '--execute','--queue',str(path),'--output',str(RUN/name)]
    with (RUN/(name+'.log')).open('wb') as log:
        p=subprocess.Popen(command,cwd=ROOT,env=process_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    lease=BASE/'leases/warp7.json';value=json.loads(lease.read_text());value.update(pid=p.pid,source_sha=sha,concurrency=16,stage='N16 transport DEV',
        expected_end=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=1500)).isoformat())
    lease.write_text(json.dumps(value,indent=2)+'\n')
    (RUN/(name+'-dispatch.json')).write_text(json.dumps(dict(pid=p.pid,command=command,source_sha=sha,
        dispatcher_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2)+'\n')
    print(json.dumps(dict(pid=p.pid,source_sha=sha,queue=str(path),runs=16,initial_cases=11)))


if __name__=='__main__':main()
