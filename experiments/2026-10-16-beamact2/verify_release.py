"""GCP2 public Release redownload, exact inventory verification and CPU load."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen


def main():
    root=Path('/home/ugrp/ugrp-sim/ops-reviews/beamact2')
    lease=Path('/home/ugrp/ugrp-sim/leases/beamact2-release.json')
    assert not lease.exists()
    lease.write_text(json.dumps(dict(task='beamact2-release',pid=os.getpid(),start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='finite public download and fresh-clone load check')))
    try:
        base='https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project'
        metadata=urlopen(base+'/releases/download/models-20261016-beamact2-v1/model-entry.json',timeout=60).read()
        expected=(root/'release-v1/model-entry.json').read_bytes()
        assert metadata==expected
        row=json.loads(metadata)
        fresh=Path('/home/ugrp/ugrp-sim/src/beamact2-release-fresh-24222c51')
        assert not fresh.exists()
        subprocess.run(['git','clone','--reference','/home/ugrp/ugrp-sim/git-shared.git','--filter=blob:none','--no-checkout',base+'.git',str(fresh)],check=True)
        subprocess.run(['git','checkout','--detach',row['evaluation_source_sha']],cwd=fresh,check=True)
        assert not subprocess.check_output(['git','status','--porcelain'],cwd=fresh).strip()
        sys.path.insert(0,str(fresh))
        from scripts.beamact1_runtime import require_gcp2
        from scripts.model_artifacts import fetch,verify_directory
        require_gcp2(training=False)
        destination=root/'redownload-v1'
        result=fetch(row,destination)
        checked=verify_directory(row,destination)
        env=dict(os.environ,PYTHONPATH=str(fresh),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
        command=['/home/ugrp/ugrp-act-cpu-env/bin/python','-m','scripts.beamact2_worker','--model',str(destination/'actor')]
        loaded=subprocess.run(command,cwd=fresh,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=180)
        (root/'redownload-load.stderr').write_text(loaded.stderr)
        assert loaded.returncode==0,loaded.stderr[-2000:]
        ready=json.loads(loaded.stdout.strip());assert ready['ready'] is True
        receipt=dict(complete=True,public_redownload=True,metadata_sha256=hashlib.sha256(metadata).hexdigest(),archive=row['archive'],release=row['release'],fetch=result,all_files_verified=checked,model_load=ready,load_exit=loaded.returncode,load_command=command,fresh_clone=str(fresh),source_sha=row['evaluation_source_sha'],credentials_on_vm=False,physical_inference_repeated=False)
        (root/'release-verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt),flush=True)
    finally:
        lease.unlink()


if __name__=='__main__':main()
