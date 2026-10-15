"""Bounded reloc16 DEV batch. Run only on gcp2, source committed and pinned."""
import argparse,datetime,hashlib,json,os,platform,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RUNS=Path('/home/ugrp/ugrp-sim/runs')
PYTHON='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python'
PROFILE='walls_floor_contrast_v5_indigo110_s80'


def main(round_no,launch):
    if not platform.node().startswith('ugrp-sim-gcp2'):raise RuntimeError('gcp2 only')
    from scripts.grasp_act_host import identity
    host=identity('gcp2');sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no']):raise RuntimeError('clean committed source required')
    rejection=RUNS/(f'reloc16-round{round_no-1}/rejection-table.json' if round_no>1 else 'reloc16-static-r3/rejection-table.json')
    assert rejection.is_file(),rejection
    if round_no>1:assert json.loads((RUNS/f'reloc16-round{round_no-1}/summary.json').read_text())['status']=='MEASURED','prior round incomplete'
    base=json.loads((ROOT/'experiments/2026-10-15-reloc15/gcp-commands-r1.json').read_text())
    oldcmd=next(r['command'] for r in base if r['kind']=='selfmap' and r['seed']==93584 and r['candidate'])
    selfcmd=oldcmd[oldcmd.index('--')+1:]
    selfcmd[0]=PYTHON
    selfcmd[selfcmd.index('--execution-host')+1]='gcp2';selfcmd[selfcmd.index('--project')+1]='ugrp-sim-b-1014'
    selfcmd+=['--reloc15-update-budget-v1','--review-playback']
    plan=json.loads((ROOT/'experiments/2026-10-15-reloc15/carry-dense-plan.json').read_text())
    queue=[]
    # Failed seeds first. Old/new selfmap share all control options, recorder fix
    # and GCP2 host. Carry's historical dense failure is read from Mac summaries;
    # the known defective old yaw is not resubmitted for a success denominator.
    items=[('selfmap',93584,True),('selfmap',93583,True),('carry',93266,True),('carry',93315,True)]
    if round_no==1:items += [('selfmap',93584,False),('selfmap',93583,False)]
    batch=RUNS/f'reloc16-round{round_no}'
    batch.mkdir(exist_ok=False)
    for kind,seed,on in items:
        name=f'reloc16-r{round_no}-{kind}-{seed}-'+('v5' if on else 'v1')+f'-{sha[:8]}'
        folder=RUNS/name;folder.mkdir(exist_ok=False);out=folder/'raw'
        env=dict(os.environ,MUJOCO_GL='osmesa',PYOPENGL_PLATFORM='osmesa',PYTHONPATH=str(ROOT),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        if on:
            cal=ROOT/'experiments/2026-10-16-reloc16/colour-calibration.json'
            env.update(UGRP_SCENE_COLOUR_BOUNDARY='scene_colour_transition_v2',UGRP_SCENE_RENDER_PROFILE=PROFILE,
                UGRP_SCENE_COLOUR_CALIBRATION=str(cal),UGRP_SCENE_COLOUR_CALIBRATION_SHA256=hashlib.sha256(cal.read_bytes()).hexdigest())
        else:env['UGRP_SCENE_COLOUR_BOUNDARY']='off'
        if round_no>=2 and on:env['UGRP_RELOC16_FLOOR_LANDMARK_MASK']='scene_floor_landmark_mask_v1'
        if round_no==3 and on:env['UGRP_RELOC16_CARRY_WALL_FIELD']='static_walls_v1'
        if kind=='selfmap':
            cmd=selfcmd.copy()
            if round_no==3:cmd+=['--reloc11-wall-field-v1']
            for flag,value in [('--output',out),('--seed',seed),('--expected-source-sha',sha),('--render-profile',PROFILE if on else 'floor_light_textured_v1')]:
                cmd[cmd.index(flag)+1]=str(value)
        else:
            episode=json.loads(json.dumps(next(e for e in plan['episodes'] if e['seed']==seed)))
            episode.update(batch=f'reloc16-r{round_no}',pr=532,reloc16_role='known_failure_regression',
                render_profile=PROFILE,scene_version=PROFILE+'/no_mip_v1',reloc16_wall_compass_v1=True,
                reloc16_active_view_v1=True,scene_wall_tracking_v1=True,reloc15_rgb_heading_v1=False,
                reloc15_dense_yaw_v1=False,reloc15_heading_quality_v1=False,reloc15_heading_10hz_v1=False)
            plan_path=folder/'input-plan.json';plan_path.write_text(json.dumps(dict(episodes=[episode]),indent=2)+'\n')
            cmd=[PYTHON,'-m','scripts.run_solo_grasp_act_teacher','--plan',str(plan_path),'--episode','0','--out',str(out),
                '--execution-host','gcp2','--teacher-profile','solo_visible_only_v1','--held-object-hidden-v1',
                '--setdown-lookaround-v1','--teacher-stability','align_relook_v1','--reach-mode','pad_window_v2',
                '--rgb-lift-mode','solo_lift_lookback_v1','--solo-lift-lookback-margin-v1','--solo-truth-free-lookaround-v1',
                '--solo-carry-to-zone-v1','--cap-s','150','--failure-rgb-buffer','--review-playback']
        queue.append(dict(name=name,kind=kind,seed=seed,scene='v5' if on else 'v1',source_sha=sha,command=cmd,
                          environment={k:env[k] for k in ('UGRP_SCENE_COLOUR_BOUNDARY','UGRP_SCENE_RENDER_PROFILE','UGRP_SCENE_COLOUR_CALIBRATION','UGRP_SCENE_COLOUR_CALIBRATION_SHA256','UGRP_RELOC16_FLOOR_LANDMARK_MASK','UGRP_RELOC16_BOUNDARY_PROPOSALS','UGRP_RELOC16_CARRY_WALL_FIELD') if k in env},raw=str(out),rejection_table=str(rejection),ready=False,dev_only=True))
        (folder/'RUN_META.json').write_text(json.dumps(dict(task='reloc16',pr=532,branch='claude/reloc16',sha=sha,**{'class':'dev'})))
        (folder/'launch-env.json').write_text(json.dumps(queue[-1]['environment'],indent=2))
        if launch:
            leases=[]
            for p in (RUNS.parent/'leases').glob('*.json'):
                row=json.loads(p.read_text());leases.append(dict(path=str(p),**row))
            # Own declared8 is already included; never remove another task lease.
            capacity=sum(r.get('concurrency',0) for r in leases)
            if capacity>40:raise RuntimeError(f'LEASE_CAPACITY_EXCEEDED:{capacity}')
            available=int(next(l for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')).split()[1])*1024
            if available<6*1024**3 or os.statvfs(RUNS).f_bavail*os.statvfs(RUNS).f_frsize<20*1024**3:raise RuntimeError('resource budget')
            with (folder/'run.log').open('wb') as log:
                process=subprocess.Popen(['timeout','--signal=INT','--kill-after=60','3600',*cmd],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            queue[-1].update(pid=process.pid,leases_at_admission=leases,declared_host_capacity=capacity,host=host)
        (batch/'queue.json').write_text(json.dumps(dict(source_sha=sha,rejection_table=str(rejection),runs=queue),indent=2)+'\n')
        print(json.dumps(dict(name=name,pid=queue[-1].get('pid'))),flush=True)
    if launch:
        lease=RUNS.parent/'leases/reloc16.json';record=json.loads(lease.read_text())
        record.update(pid=queue[0]['pid'],pids=[r['pid'] for r in queue],source_sha=sha,pr=532)
        lease.write_text(json.dumps(record,indent=2)+'\n')
    (batch/'submitted.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),runs=len(queue),host=host)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,choices=(1,2,3),required=True);p.add_argument('--launch',action='store_true');a=p.parse_args();main(a.round,a.launch)
