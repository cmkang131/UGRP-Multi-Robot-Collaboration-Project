"""Explicit one-group submission; prior native gates need raw-audited admission.

No background queue, cloud access, wall deadline, or automatic retry.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time

ROOT=Path('/home/ugrp/ugrp-sim')
OPS=ROOT/'ops-reviews/warp8'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);a=p.parse_args()
    assert socket.gethostname().split('.')[0]=='ugrp-act-l4-gcp3'
    plan=json.loads((OPS/'native-gate-plan.json').read_text())
    session=json.loads((OPS/'native-host-start.json').read_text())
    assert session['status']=='RUNNING' and session['clear_verified'] and session['started_without_cap_flags']
    assert session['max_run_duration_s'] is None and session['supervisor_wall_deadline'] is None
    assert session['budget_stop_verified'] and session['project']=='ugrp-sim-c-1016'
    assert session['account']=='changmin5781@gmail.com'
    assert plan['profile']=='warp_native_contact_v1'
    groups=plan['groups'];group=next(g for g in groups if g['tag']==a.tag)
    for previous in groups[:groups.index(group)]:
        run=ROOT/'runs/warp8'/previous['tag']
        check=json.loads((OPS/(previous['tag']+'-admission.json')).read_text())
        assert check['continue_authorized'] is True
        assert check['raw_summary_sha256']==sha(run/'summary.json')
    src=ROOT/'src'/plan['source_sha']
    assert subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()==plan['source_sha']
    assert not subprocess.check_output(['git','-C',str(src),'status','--porcelain','--untracked-files=no'])
    assert sha(src/'sim/warp_native_contact.py')=='a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a'
    assert Path(group['rejection_table']).is_absolute() and Path(group['rejection_table']).is_file()
    refs=Path(group['references']);assert sha(refs)==group['references_sha256']
    assert sha(Path(group['cases']))==group['cases_sha256']
    proof=json.loads(Path(group['reference_proof']).read_text())
    assert proof['physics_steps']==0 and all(x['actuator_material_arrays_exact'] and x['all_geometry_arrays_exact'] for x in proof['proof'])
    lock=(ROOT/'leases/.warp9-claim.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        assert not list((ROOT/'leases').glob('*.json'))
        assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
        assert subprocess.run(['pgrep','-f','[n]vidia-cuda-mps'],capture_output=True).returncode==1
        assert subprocess.check_output(['systemctl','is-active','ugrp-idle-guard.timer'],text=True).strip()=='active'
        assert __import__('shutil').disk_usage(ROOT).free>58*1024**3 # approved50GiB future raw + existing8GiB floor
        assert not (ROOT/'runs/warp8'/a.tag).exists()
        cmd=['python3',str(src/'experiments/2026-10-16-warp8/run_batch.py'),'--source-sha',plan['source_sha'],
            '--tag',a.tag,'--flow',group['flow'],'--cases',group['cases'],'--indices',','.join(map(str,group['indices'])),
            '--references',str(refs),'--canonical-xml',group['canonical_xml'],'--rejection-table',group['rejection_table'],
            '--full-active-dof-workspace-v1','--warp-native-contact-v1']
        with (OPS/(a.tag+'.driver.log')).open('x') as log:
            child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        lease=ROOT/'leases'/('warp8-'+a.tag+'.json')
        until=time.monotonic()+10 # launch handshake only, never a task limit
        while not lease.exists() and child.poll() is None and time.monotonic()<until:time.sleep(.1)
        assert lease.exists() and child.poll() is None
        record=dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),group=group,source_sha=plan['source_sha'],
            driver_PID=child.pid,lease=json.loads(lease.read_text()),command=cmd,submitter_sha256=sha(Path(__file__)),
            session=session,GPU_before='none',MPS='off',profile=plan['profile'])
        (OPS/(a.tag+'-submit.json')).write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(record),flush=True)
    finally:fcntl.flock(lock,fcntl.LOCK_UN);lock.close()


if __name__=='__main__':main()
