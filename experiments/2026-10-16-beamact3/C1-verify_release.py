"""GCP2 public redownload, all-file SHA and fresh reference-clone CPU loading."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.request import urlopen


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--arm',choices=('C1','C2'),required=True)
    p.add_argument('--attempt',type=int,default=1);a=p.parse_args()
    base=Path('/home/ugrp/ugrp-sim');root=base/'ops-reviews/beamact3c'/a.arm
    lease=base/f'leases/beamact3c-{a.arm}-release.json'
    with lease.open('x') as f:json.dump(dict(task='beamact3c-'+a.arm+'-release',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end='finite public model download + CPU load',concurrency=0),f)
    try:
        from harness.grasp_act_data import read_json,write_json,sha256
        from scripts.beamact1_runtime import require_gcp2
        from scripts.model_artifacts import fetch,verify_directory
        require_gcp2(training=False)
        expected=(root/'release-v1/model-entry.json').read_bytes();row=json.loads(expected)
        tag=row['release']['tag'];repo='https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project'
        public=urlopen(repo+'/releases/download/'+tag+'/model-entry.json',timeout=60).read()
        if public!=expected:raise ValueError('public model entry differs')
        fresh=base/'src'/f'beamact3c-{a.arm}-release-fresh-{row["evaluation_source_sha"][:8]}-attempt{a.attempt}'
        if fresh.exists():raise ValueError('never overwrite fresh clone verification')
        shared=base/'git-shared.git'
        subprocess.run(['git','clone','--reference',str(shared),'--no-local','--no-checkout',str(shared),str(fresh)],check=True)
        subprocess.run(['git','-C',str(fresh),'config','gc.auto','0'],check=True)
        subprocess.run(['git','-C',str(fresh),'config','maintenance.auto','false'],check=True)
        subprocess.run(['git','checkout','--detach',row['evaluation_source_sha']],cwd=fresh,check=True)
        assert not subprocess.check_output(['git','status','--porcelain'],cwd=fresh).strip()
        assert (fresh/'.git/objects/info/alternates').read_text().strip()==str(shared/'objects')
        destination=root/f'redownload-attempt{a.attempt}'
        downloaded=fetch(row,destination);checked=verify_directory(row,destination)
        command=['/home/ugrp/ugrp-act-cpu-env/bin/python','-m','scripts.beamact2_worker','--model',str(destination/'actor')]
        env={**os.environ,'PYTHONPATH':str(fresh),'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
        loaded=subprocess.run(command,cwd=fresh,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=180)
        (root/f'redownload-attempt{a.attempt}-load.stderr').write_text(loaded.stderr)
        if loaded.returncode:raise RuntimeError('fresh clone CPU load failed: '+loaded.stderr[-2000:])
        ready=json.loads(loaded.stdout.strip());assert ready=={'ready':True}
        receipt=dict(complete=True,arm=a.arm,public_redownload=True,metadata_sha256=hashlib.sha256(public).hexdigest(),
            archive=row['archive'],release=row['release'],fetch=downloaded,all_files_verified=checked,model_load=ready,
            load_exit=loaded.returncode,load_command=command,fresh_clone=str(fresh),source_sha=row['evaluation_source_sha'],
            credentials_on_vm=False,new_physical_runs=0,scope='selected weights and inference assets; not raw data/video backup or additional physical success')
        write_json(root/'release-verification.json',receipt)
        print(json.dumps(receipt),flush=True)
    finally:lease.unlink()


if __name__=='__main__':main()
