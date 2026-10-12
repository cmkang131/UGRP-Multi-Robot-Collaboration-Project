"""Two preregistered own-RGB strafe recordings; no detector or GT feedback."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/2026-10-07-wall-parallax-strafe'
RAW = Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-strafe-v1')
CASES = {'strafe-north': dict(seed=15101, spawn=[3.25,.75,3.141592653589793], sign=1),
         'strafe-south': dict(seed=15102, spawn=[3.25,-.70,3.141592653589793], sign=-1)}
PULSES = {1:2000,3:740,4:2320,5:1320,6:1500}
USER_FILES = {'analyze_wall_detection.py':'26c818f1cd4673c7f4a1b6ab535b4e70ac68167f1f56989f10c8c6bebe0c3dd0',
    'create_wall_visualizations.py':'e2b77c1f678d1ba27658dffecf99bcf7bfd7c12c056d41869a7a38cc482f8efa',
    'create_wall_visualizations_v2.py':'8e6fa7f6598336bc6f7c61ad956d1902be9925443d7656cea2801362195d83c8',
    'parameter_probe.py':'43f91584406ba91a73032514b8409357fc9c7ac2c3cbc3e72d26bce5257e103b'}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,r):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def verify_source(expected):
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
    assert git('branch','--show-current')=='claude/ego-wall-map'
    assert git('rev-parse','HEAD')==git('rev-parse','origin/claude/ego-wall-map')==expected
    assert not git('diff','HEAD','--name-only')
    untracked=git('ls-files','--others','--exclude-standard').splitlines()
    assert set(untracked)==set(USER_FILES)
    assert all(sha(ROOT/p)==h for p,h in USER_FILES.items())
    frozen=json.loads((ROOT/'experiments/2026-10-07-wall-parallax/freeze.json').read_text())
    assert all(sha(ROOT/p)==h for p,h in frozen['hashes'].items())
    copy=json.loads((EXP/'copied-sources.json').read_text())
    assert all(sha(ROOT/p)==v['sha256'] for p,v in copy['files'].items())
    return {'frozen_hashes':frozen['hashes'],'copied_sources':copy,'preserved_untracked':USER_FILES}

def actions(case,tick):
    if tick==0:
        return [dict(kind='arm',servo_id=k,pulse=v) if k!=6 else dict(kind='look',pan_pulse=v)
                for k,v in PULSES.items()]
    if tick in (50,60,70,80,110,120,130,140):
        sign=CASES[case]['sign']*(1 if tick<100 else -1)
        return [dict(kind='mecanum',forward=0.,left=sign*.65,turn=0.,duration_s=.65)]
    return []

def acquire_case(case,out,source,backend_factory):
    """The loop uses time and its own command table only; eval return is ignored."""
    from time import monotonic
    spec=CASES[case]
    bundle=dict(source_sha=source,execution_bundle_id='egomap15-strafe-v1',check='parallax-strafe',
        map_id='zone_wide_two_doors_final_v3',contact_profile='cargo_noslip_v1',case=case,
        task=dict(robot_id='r3',seed=spec['seed'],destination='B',pickup_slot='P1-2'),
        options=dict(drive_profile='masterpi_drive_friction_v7',camera_profile='camera_v3',
            roller_collision='mesh',idle_robot_contacts='off',min_wheel_cmd='real_v1'),
        spawn=spec['spawn'],case_cap_s=18.,capture_s=.1,initial_servo=PULSES)
    out.mkdir(parents=True,exist_ok=False)
    write(out/'bundle.json',bundle)
    result=dict(status='HOST_ERROR',source_sha=source,case=case,model_calls=0,
        loadavg_start=list(os.getloadavg()),qualification='authored data acquisition; not navigation or physical hardware success')
    backend=None
    started=monotonic()
    try:
        backend=backend_factory(bundle,out,seed=spec['seed'])
        backend.reset(5.)
        start=backend.now
        backend.set_deadline(start+18.)
        for i in range(181):
            for action in actions(case,i):backend.issue('r3',action)
            backend.capture()
            backend.eval_sample()  # private write-only except abort-only physical safety
            if i%20==0:
                write(out/'progress.json',dict(sim_s=i/10,frames=i+1))
                print(case,'SIM',i/10,'frames',i+1,flush=True)
            if i<180:backend.advance_to(round(start+(i+1)/10,9))
        result.update(status='RECORDED',frames=181,total_sim_s=backend.now)
    except Exception as e:
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__=='PhysicalStop' else 'HOST_ERROR',
            failure=dict(type=type(e).__name__,message=str(e)),enospc=getattr(e,'errno',None)==28)
    finally:
        if backend is not None:backend.close()
        result['wall_s']=monotonic()-started
        result['loadavg_end']=list(os.getloadavg())
        write(out/'result.json',result)
        write(out/'artifacts.sha256.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*'))
                                          if p.is_file() and p.name!='artifacts.sha256.json'})
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=CASES,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    receipts=verify_source(a.expected_source_sha)
    assert not a.output.exists()
    if a.output.resolve()!=RAW/a.case:
        assert a.output.resolve()==RAW/(a.case+'-host-retry1')
        prior=json.loads((RAW/a.case/'result.json').read_text())
        assert prior['status']=='HOST_ERROR' and not (RAW/a.case/'robots').exists()
    if not a.execute:
        print(json.dumps(dict(case=a.case,admitted=True,execution_started=False)))
        return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',
        purpose='final frozen parallax strafe recording',pid=os.getpid(),expected_minutes=15)
    try:
        from sim.wall_parallax_strafe import PhysicsBackend
        result=acquire_case(a.case,a.output,a.expected_source_sha,PhysicsBackend)
        write(a.output/'source-admission.json',receipts)
        write(a.output/'lock.json',lock)
    finally:
        release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
